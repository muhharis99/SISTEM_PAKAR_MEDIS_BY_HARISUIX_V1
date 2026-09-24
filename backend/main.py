from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from backend.db import AuditLog, Feedback, SessionLocal, User, init_db, verify_password
from ml.retrieval import DiagnosisRetriever
from ml.image_analysis import analyze_image_bytes
from ml.clinical_extractor import extract_clinical_features
from ml.vision_provider import analyze_with_vision, VISION_ENABLED, VISION_MODEL, OLLAMA_URL
from ml.multimodal import fuse_results

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = Path(os.getenv("INDEX_DIR", ROOT / "data/index"))
SECRET = os.getenv("APP_SECRET", "dev-only-change-me")
SESSION_COOKIE = "cdss_session"


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

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
    return {"ok": True, "index_loaded": retriever is not None, "vision_enabled": VISION_ENABLED, "vision_model": VISION_MODEL, "vision_provider_url": OLLAMA_URL}


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
    audit(user["id"], "analisa", {"query_hash": query_hash, "result_count": len(result["results"])})
    result["disclaimer"] = "Hasil ini adalah rekomendasi berbasis kemiripan histori, bukan diagnosis final dan bukan probabilitas klinis terkalibrasi. Keputusan akhir tetap pada tenaga medis berwenang."
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
    user=Depends(get_current_user),
) -> dict[str, Any]:
    if retriever is None:
        raise HTTPException(status_code=503, detail="Index belum tersedia.")
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
    try:
        clinical_result = retriever.analyze(clinical, top_n=min(max(top_n, 1), 10))
    except ValueError as exc:
        # Foto dapat dianalisis meskipun operator belum mengisi anamnesa/periksa.
        clinical_result = {"query": "", "results": [], "similar_cases": [], "skipped": True, "reason": str(exc)}
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
    return {
        "image": image_baseline,
        "clinical_features": clinical_features,
        "vision": vision,
        "clinical_analysis": clinical_result,
        "visual_retrieval": visual_result,
        "fused_results": fused,
        "fusion_policy": {"clinical_weight": 0.70, "visual_weight": 0.30, "interpretation": "Skor fusion adalah heuristic antar sumber evidence, bukan probabilitas penyakit terkalibrasi."},
        "disclaimer": "Analisa multimodal adalah decision-support. Temuan visual belum merupakan diagnosis dan hasil fusion belum tervalidasi klinis. Keputusan akhir tetap pada dokter.",
    }

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
    with SessionLocal() as s:
        s.add(Feedback(
            user_id=user["id"],
            input_summary=json.dumps({"anamnese_length": body.anamnese_length, "periksa_length": body.periksa_length}),
            recommended=json.dumps(body.recommended, ensure_ascii=False),
            corrected_diagnosis=body.corrected_diagnosis[:500],
            note=body.note[:1000],
        ))
        s.commit()
    audit(user["id"], "feedback_koreksi", {"recommended_count": len(body.recommended), "corrected": body.corrected_diagnosis[:120]})
    return {"ok": True}


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
