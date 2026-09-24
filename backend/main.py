from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from backend.db import AuditLog, CaseRecord, Feedback, SessionLocal, User, init_db, verify_password
from ml.retrieval import DiagnosisRetriever
from ml.image_analysis import analyze_image_bytes
from ml.clinical_extractor import extract_clinical_features
from ml.vision_provider import analyze_with_vision, VISION_ENABLED, VISION_MODEL, OLLAMA_URL
from ml.multimodal import fuse_results
from ml.clinical_checklist import build_clinical_checklist

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = Path(os.getenv("INDEX_DIR", ROOT / "data/index"))
SECRET = os.getenv("APP_SECRET", "dev-only-change-me")
SESSION_COOKIE = "cdss_session"


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

APP_MODES = {"multimodal", "photo", "clinical"}

def _vision_runtime_status() -> dict[str, Any]:
    if not VISION_ENABLED:
        return {
            "enabled": False,
            "reachable": False,
            "model": VISION_MODEL,
            "model_available": False,
            "status": "disabled",
            "message": "Vision AI dinonaktifkan oleh konfigurasi.",
        }
    try:
        tags_url = OLLAMA_URL.replace("/api/chat", "/api/tags")
        req = urllib.request.Request(tags_url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        names = [str(x.get("name", "")) for x in (payload.get("models") or [])]
        available = any(
            name == VISION_MODEL or name.startswith(VISION_MODEL.split(":")[0] + ":")
            for name in names
        )
        return {
            "enabled": True,
            "reachable": True,
            "model": VISION_MODEL,
            "model_available": available,
            "models": names[:30],
            "status": "ready" if available else "model_missing",
            "message": "Vision AI siap digunakan." if available else f"Provider aktif tetapi model {VISION_MODEL} belum tersedia.",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "reachable": False,
            "model": VISION_MODEL,
            "model_available": False,
            "status": "offline",
            "message": "Vision provider tidak terhubung.",
            "error_type": type(exc).__name__,
        }

def _new_case_uid() -> str:
    return "CASE-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()

def _save_case(
    user_id: int,
    mode: str,
    title: str,
    payload: dict[str, Any],
    result: dict[str, Any],
    image_sha256: str = "",
) -> str:
    uid = _new_case_uid()
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.add(CaseRecord(
            case_uid=uid,
            user_id=user_id,
            mode=mode,
            title=(title or "Kasus Baru")[:180],
            status="review",
            image_sha256=image_sha256[:64],
            input_json=json.dumps(payload, ensure_ascii=False, default=str),
            result_json=json.dumps(result, ensure_ascii=False, default=str),
            created_at=now,
            updated_at=now,
        ))
        s.commit()
    return uid

def _safe_json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

app = FastAPI(title="CDSS Mata - Sistem Bantu Analisa Diagnosa", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever: DiagnosisRetriever | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AnalyzeRequest(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = None
    alergi: str = ""
    anamnese: str = ""
    riwayat_sekarang: str = ""
    periksa: str = ""
    top_n: int = Field(default=5, ge=1, le=10)


class FeedbackRequest(BaseModel):
    recommended: list[str] = []
    corrected_diagnosis: str
    case_uid: str | None = None
    note: str = ""
    anamnese_length: int = 0
    periksa_length: int = 0


def _sign(value: str) -> str:
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_token(user: User) -> str:
    exp = int(time.time()) + 8 * 3600
    payload = f"{user.id}.{user.username}.{user.role}.{exp}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return encoded + "." + _sign(encoded)


def read_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    encoded, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(encoded)):
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode((encoded + padding).encode()).decode()
        uid, username, role, exp = payload.split(".", 3)
        if int(exp) < int(time.time()):
            return None
        return {"id": int(uid), "username": username, "role": role}
    except Exception:
        return None


def get_current_user(cdss_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    user = read_token(cdss_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sesi tidak valid atau sudah berakhir.")
    with SessionLocal() as s:
        db_user = s.get(User, user["id"])
        if not db_user or not db_user.active:
            raise HTTPException(status_code=401, detail="Akun tidak aktif.")
    return user


def require_roles(*roles: str):
    def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Role tidak memiliki akses ke aksi ini.")
        return user
    return checker


def audit(user_id: int | None, action: str, detail: dict[str, Any] | None = None) -> None:
    with SessionLocal() as s:
        s.add(AuditLog(user_id=user_id, action=action, detail=json.dumps(detail or {}, ensure_ascii=False)))
        s.commit()


def ensure_index() -> None:
    global retriever
    if (INDEX_DIR / "tfidf.joblib").exists():
        retriever = DiagnosisRetriever(INDEX_DIR)
        return
    script = ROOT / "scripts/build_index.py"
    subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=True)
    retriever = DiagnosisRetriever(INDEX_DIR)


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_index()


@app.get("/health")
def health() -> dict[str, Any]:
    vision = _vision_runtime_status()
    return {
        "ok": True,
        "index_loaded": retriever is not None,
        "vision_enabled": VISION_ENABLED,
        "vision_model": VISION_MODEL,
        "vision_provider_url": OLLAMA_URL,
        "vision": vision,
    }

@app.get("/api/system/status")
def system_status(user=Depends(get_current_user)) -> dict[str, Any]:
    return {
        "app": {"name": "CDSS Mata", "version": "3.0.0"},
        "index": {
            "loaded": retriever is not None,
            "cases": len(retriever.metadata) if retriever else 0,
            "diagnoses": len(retriever.label_counts) if retriever else 0,
        },
        "vision": _vision_runtime_status(),
        "analysis_modes": sorted(APP_MODES),
    }


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response) -> dict[str, Any]:
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Username atau password salah.")
        token = create_token(user)
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=8 * 3600)
        audit(user.id, "login", {"role": user.role})
        return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response, user=Depends(get_current_user)) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    audit(user["id"], "logout")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(get_current_user)) -> dict[str, Any]:
    return user


@app.post("/api/analisa")
def analyze(body: AnalyzeRequest, user=Depends(get_current_user)) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    try:
        result = retriever.analyze(body.model_dump(), top_n=body.top_n)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    query_hash = hashlib.sha256(result["query"].encode("utf-8")).hexdigest()[:16]
    checklist = build_clinical_checklist(
        " ".join([body.anamnese, body.riwayat_sekarang, body.periksa, body.alergi]),
        body.age,
    )
    result["clinical_checklist"] = checklist
    result["evidence_type"] = "historical_text_retrieval"
    result["score_semantics"] = "relative_support"
    result["disclaimer"] = "Hasil ini adalah decision-support berbasis kemiripan histori, bukan diagnosis final dan bukan probabilitas klinis terkalibrasi."
    case_uid = _save_case(
        user["id"],
        "clinical",
        "Analisa Klinis",
        body.model_dump(),
        result,
    )
    result["case_uid"] = case_uid
    audit(user["id"], "analisa", {"query_hash": query_hash, "result_count": len(result["results"]), "case_uid": case_uid})
    return result


@app.get("/api/kasus-mirip")
def similar_cases(
    q: str = Query(..., min_length=2),
    diagnosis: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    return {"items": retriever.similar_cases(q, limit, diagnosis)}


@app.post("/api/analisa-gambar")
async def analyze_image(
    image: UploadFile = File(...),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    Analisa foto secara lokal sebagai screening kualitas/fitur visual dasar.
    Endpoint ini sengaja tidak mengklaim diagnosis penyakit dari gambar karena
    model oftalmologi tervalidasi belum menjadi bagian dari baseline project.
    """
    if (image.content_type or "").lower() not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Format foto harus JPG/JPEG, PNG, atau WEBP.")
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File foto kosong.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Ukuran foto maksimal 10 MB.")
    try:
        result = analyze_image_bytes(raw, image.content_type or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Foto tidak dapat dianalisis: {e}")
    audit(user["id"], "analisa_gambar", {
        "filename": (image.filename or "foto").split("/")[-1][-80:],
        "content_type": image.content_type,
        "sha256": result["sha256"],
        "quality": result["quality"]["status"],
    })
    result["disclaimer"] = (
        "Analisa foto saat ini adalah screening kualitas dan ciri visual dasar, "
        "bukan diagnosis penyakit mata dan bukan probabilitas klinis. Temuan harus "
        "diverifikasi oleh dokter. Model diagnosis berbasis foto yang tervalidasi "
        "belum terpasang pada versi ini."
    )
    return result



@app.post("/api/analisa-multimodal")
async def analyze_multimodal(
    image: UploadFile = File(...),
    age: int | None = Form(default=None),
    sex: str = Form(default=""),
    alergi: str = Form(default=""),
    anamnese: str = Form(default=""),
    riwayat_sekarang: str = Form(default=""),
    periksa: str = Form(default=""),
    top_n: int = Form(default=5),
    mode: str = Form(default="multimodal"),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    if mode not in {"multimodal", "photo"}:
        raise HTTPException(status_code=400, detail="Mode foto harus multimodal atau photo.")
    if (image.content_type or "").lower() not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Format foto harus JPG/JPEG, PNG, atau WEBP.")
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File foto kosong.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Ukuran foto maksimal 10 MB.")
    clinical = {
        "age": age, "sex": sex, "alergi": alergi,
        "anamnese": anamnese, "riwayat_sekarang": riwayat_sekarang,
        "periksa": periksa,
    }
    try:
        image_baseline = analyze_image_bytes(raw, image.content_type or "")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Foto tidak dapat dianalisis: {exc}")
    clinical_features = extract_clinical_features(f"{anamnese} {riwayat_sekarang} {periksa} {alergi}")
    vision = analyze_with_vision(raw, image.content_type or "", clinical_context=f"Anamnesa: {anamnese}\nPemeriksaan: {periksa}")

    has_clinical_input = any(
        str(clinical.get(key) or "").strip()
        for key in ("anamnese", "riwayat_sekarang", "periksa", "alergi")
    )
    if has_clinical_input:
        try:
            clinical_result = retriever.analyze(clinical, top_n=min(max(top_n, 1), 10))
        except ValueError as exc:
            clinical_result = {
                "query": "",
                "results": [],
                "similar_cases": [],
                "skipped": True,
                "reason": str(exc),
            }
    else:
        clinical_result = {
            "query": "",
            "results": [],
            "similar_cases": [],
            "skipped": True,
            "reason": "Tidak ada input klinis; analisa visual-only.",
        }


    visual_result = {"results": [], "similar_cases": []}
    visual_query = ""
    if vision.get("available"):
        va = vision.get("analysis") or {}
        finding_text = " ".join(str(x.get("finding", "")) for x in va.get("visible_findings", []))
        visual_query = f"{va.get('photo_type','')} {va.get('laterality','')} {finding_text}".strip()
        if visual_query:
            visual_result = retriever.analyze({"periksa": visual_query}, top_n=min(max(top_n, 1), 10))
    fused = fuse_results(clinical_result.get("results", []), visual_result.get("results", []), clinical_weight=0.70)
    audit(user["id"], "analisa_multimodal", {
        "sha256": image_baseline["sha256"],
        "vision_available": vision.get("available", False),
        "quality": image_baseline["quality"]["status"],
        "clinical_result_count": len(clinical_result.get("results", [])),
        "fused_result_count": len(fused),
    })
    checklist = build_clinical_checklist(
        " ".join([anamnese, riwayat_sekarang, periksa, alergi]),
        age,
    )
    evidence_completeness = {
        "clinical_input": has_clinical_input,
        "image_quality": image_baseline["quality"]["status"],
        "vision": vision.get("available", False),
        "visual_retrieval": bool(visual_result.get("results")),
    }
    result_payload = {
        "image": image_baseline,
        "clinical_features": clinical_features,
        "clinical_checklist": checklist,
        "vision": vision,
        "clinical_analysis": clinical_result,
        "visual_retrieval": visual_result,
        "fused_results": fused,
        "evidence_completeness": {**evidence_completeness, "mode": mode},
        "fusion_policy": {
            "clinical_weight": 0.70,
            "visual_weight": 0.30,
            "interpretation": "Skor fusion adalah relative evidence score antar sumber, bukan probabilitas penyakit terkalibrasi.",
        },
        "disclaimer": "Analisa multimodal adalah decision-support. Temuan visual belum merupakan diagnosis dan hasil fusion belum tervalidasi klinis.",
    }
    case_uid = _save_case(
        user["id"],
        mode,
        "Analisa Foto" if mode == "photo" else "Analisa Multimodal",
        clinical,
        result_payload,
        image_baseline["sha256"],
    )
    result_payload["case_uid"] = case_uid
    return result_payload

@app.get("/api/cases")
def list_cases(limit: int = Query(default=30, ge=1, le=100), user=Depends(get_current_user)) -> dict[str, Any]:
    with SessionLocal() as s:
        rows = s.scalars(
            select(CaseRecord)
            .where(CaseRecord.user_id == user["id"])
            .order_by(desc(CaseRecord.updated_at))
            .limit(limit)
        ).all()
        return {
            "items": [
                {
                    "case_uid": r.case_uid,
                    "title": r.title,
                    "mode": r.mode,
                    "status": r.status,
                    "image_sha256": r.image_sha256,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in rows
            ]
        }

@app.get("/api/cases/{case_uid}")
def get_case(case_uid: str, user=Depends(get_current_user)) -> dict[str, Any]:
    with SessionLocal() as s:
        row = s.scalar(select(CaseRecord).where(CaseRecord.case_uid == case_uid, CaseRecord.user_id == user["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Kasus tidak ditemukan.")
        return {
            "case_uid": row.case_uid,
            "title": row.title,
            "mode": row.mode,
            "status": row.status,
            "input": _safe_json(row.input_json),
            "result": _safe_json(row.result_json),
            "image_sha256": row.image_sha256,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

@app.post("/api/cases/{case_uid}/status")
def update_case_status(case_uid: str, status: str = Form(...), user=Depends(get_current_user)) -> dict[str, Any]:
    allowed = {"review", "reviewed", "corrected", "archived"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status harus salah satu dari: {', '.join(sorted(allowed))}.")
    with SessionLocal() as s:
        row = s.scalar(select(CaseRecord).where(CaseRecord.case_uid == case_uid, CaseRecord.user_id == user["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Kasus tidak ditemukan.")
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        s.commit()
    audit(user["id"], "case_status", {"case_uid": case_uid, "status": status})
    return {"ok": True, "case_uid": case_uid, "status": status}

@app.get("/api/cases/{case_uid}/report", response_class=HTMLResponse)
def case_report(case_uid: str, user=Depends(get_current_user)) -> HTMLResponse:
    with SessionLocal() as s:
        row = s.scalar(select(CaseRecord).where(CaseRecord.case_uid == case_uid, CaseRecord.user_id == user["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Kasus tidak ditemukan.")
    inp = _safe_json(row.input_json)
    res = _safe_json(row.result_json)
    clinical = (res.get("clinical_analysis") or {}).get("results", []) or res.get("results", [])
    fused = res.get("fused_results", []) or res.get("results", [])
    vis = (res.get("vision") or {}).get("analysis") or {}
    checklist = res.get("clinical_checklist") or {}
    def esc_html(v: Any) -> str:
        return (
            str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
        )
    clinical_html = "".join(
        f"<li><b>{esc_html(x.get('name') or x.get('label'))}</b> — relative support {esc_html(x.get('confidence', 0))}% · support {esc_html(x.get('support_cases', 0))} kasus</li>"
        for x in clinical[:8]
    ) or "<li>Tidak ada hasil clinical retrieval.</li>"
    fused_html = "".join(
        f"<li><b>{esc_html(x.get('name') or x.get('label'))}</b> — fusion {esc_html(x.get('fusion_score', 0))} · {esc_html(x.get('consistency'))}</li>"
        for x in fused[:8]
    ) or "<li>Tidak ada hasil fusion.</li>"
    findings_html = "".join(
        f"<li>{esc_html(x.get('finding'))} — evidence {esc_html(x.get('evidence'))}</li>"
        for x in vis.get("visible_findings", [])[:12]
    ) or "<li>Tidak ada temuan visual terstruktur.</li>"
    missing_html = "".join(f"<li>{esc_html(x.get('label'))}</li>" for x in checklist.get("missing", [])[:8]) or "<li>Tidak ada.</li>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Report {esc_html(row.case_uid)}</title>
    <style>body{{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;color:#1d2939;line-height:1.5}}h1,h2{{color:#173b73}}.meta{{background:#f3f6fa;padding:15px;border-radius:10px}}.box{{border:1px solid #dbe3ec;border-radius:10px;padding:15px;margin:15px 0}}small{{color:#667085}}@media print{{body{{margin:12mm}}}}</style></head>
    <body><h1>CDSS Mata — Laporan Evidence</h1>
    <div class="meta"><b>Case:</b> {esc_html(row.case_uid)}<br><b>Mode:</b> {esc_html(row.mode)}<br><b>Status:</b> {esc_html(row.status)}<br><b>Dibuat:</b> {esc_html(row.created_at.isoformat())}</div>
    <div class="box"><h2>Input Klinis</h2><b>Anamnesa</b><p>{esc_html(inp.get("anamnese",""))}</p><b>Pemeriksaan</b><p>{esc_html(inp.get("periksa",""))}</p></div>
    <div class="box"><h2>Clinical Evidence</h2><ul>{clinical_html}</ul></div>
    <div class="box"><h2>Visual Evidence</h2><p>{esc_html(vis.get("summary",""))}</p><ul>{findings_html}</ul></div>
    <div class="box"><h2>Fusion Evidence</h2><ul>{fused_html}</ul></div>
    <div class="box"><h2>Kelengkapan Dokumentasi</h2><p>Score: {esc_html(checklist.get("completeness","-"))}%</p><ul>{missing_html}</ul></div>
    <p><small>Ini adalah laporan decision-support berbasis evidence dan histori. Bukan diagnosis final dan bukan pengganti pemeriksaan dokter.</small></p>
    <script>window.onload=()=>setTimeout(()=>window.print(),300)</script></body></html>"""
    audit(user["id"], "case_report", {"case_uid": case_uid})
    return HTMLResponse(html)

@app.get("/api/statistik")
def statistics(user=Depends(get_current_user)) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    diag_counts = retriever.label_counts
    top = [{"label": k, "count": v} for k, v in sorted(diag_counts.items(), key=lambda x: x[1], reverse=True)[:15]]
    age_counts: dict[str, int] = {}
    month_counts: dict[str, int] = {}
    for c in retriever.metadata:
        age = c.get("age_group") or "Tidak diketahui"
        age_counts[age] = age_counts.get(age, 0) + 1
        d = c.get("visit_date") or ""
        if len(d) >= 7:
            month = d[:7]
            month_counts[month] = month_counts.get(month, 0) + 1
    return {
        "total_cases": len(retriever.metadata),
        "unique_diagnoses": len(diag_counts),
        "top_diagnoses": top,
        "age_groups": [{"label": k, "count": v} for k, v in age_counts.items()],
        "monthly": [{"month": k, "count": v} for k, v in sorted(month_counts.items())],
    }


@app.get("/api/riwayat")
def history(
    diagnosis: str | None = None,
    age_group: str | None = None,
    year: int | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    out = []
    for c in retriever.metadata:
        if diagnosis and diagnosis.lower() not in " | ".join(c.get("diagnosis_labels", [])).lower():
            continue
        if age_group and c.get("age_group") != age_group:
            continue
        if year and c.get("visit_year") != year:
            continue
        if q:
            hay = f"{c.get('anamnese','')} {c.get('periksa','')} {' '.join(c.get('diagnosis_labels',[]))}".lower()
            if q.lower() not in hay:
                continue
        out.append({
            "visit_date": c.get("visit_date"),
            "visit_year": c.get("visit_year"),
            "age_group": c.get("age_group"),
            "kd_poli": c.get("kd_poli"),
            "anamnese": c.get("anamnese", "")[:300],
            "periksa": c.get("periksa", "")[:450],
            "diagnoses": c.get("diagnosis_labels", [])[:8],
        })
        if len(out) >= limit:
            break
    return {"items": out, "count": len(out)}


@app.get("/api/kamus")
def dictionary(user=Depends(get_current_user)) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
    terms = []
    for code_name, count in sorted(retriever.label_counts.items(), key=lambda x: x[1], reverse=True)[:300]:
        if " - " in code_name:
            code, name = code_name.split(" - ", 1)
        else:
            code, name = None, code_name
        terms.append({"code": code, "name": name, "label": code_name, "count": count})
    return {"items": terms}


@app.post("/api/feedback")
def feedback(body: FeedbackRequest, user=Depends(require_roles("dokter", "admin"))) -> dict[str, Any]:
    case_uid = body.case_uid
    with SessionLocal() as s:
        s.add(Feedback(
            user_id=user["id"],
            input_summary=json.dumps({
                "anamnese_length": body.anamnese_length,
                "periksa_length": body.periksa_length,
                "case_uid": case_uid,
            }),
            recommended=json.dumps(body.recommended, ensure_ascii=False),
            corrected_diagnosis=body.corrected_diagnosis[:500],
            note=body.note[:1000],
        ))
        if case_uid:
            row = s.scalar(select(CaseRecord).where(CaseRecord.case_uid == case_uid, CaseRecord.user_id == user["id"]))
            if row:
                result = _safe_json(row.result_json)
                result["doctor_correction"] = {
                    "corrected_diagnosis": body.corrected_diagnosis[:500],
                    "note": body.note[:1000],
                    "reviewed_by": user["username"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                row.result_json = json.dumps(result, ensure_ascii=False, default=str)
                row.status = "corrected"
                row.updated_at = datetime.now(timezone.utc)
        s.commit()
    audit(user["id"], "feedback_koreksi", {
        "recommended_count": len(body.recommended),
        "corrected": body.corrected_diagnosis[:120],
        "case_uid": case_uid,
    })
    return {"ok": True, "case_uid": case_uid}


@app.get("/api/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=500), user=Depends(require_roles("admin"))) -> dict[str, Any]:
    with SessionLocal() as s:
        rows = s.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)).all()
        return {"items": [{"action": r.action, "detail": json.loads(r.detail or "{}"), "created_at": r.created_at.isoformat()} for r in rows]}


@app.get("/api/evaluasi")
def evaluation(user=Depends(get_current_user)) -> dict[str, Any]:
    p = ROOT / "docs/evaluation.json"
    if not p.exists():
        return {"available": False, "message": "Jalankan scripts/evaluate_model.py untuk membuat evaluasi retrospektif."}
    return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}


frontend_dir = ROOT / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")
