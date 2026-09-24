from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

OLLAMA_URL = os.getenv("VISION_PROVIDER_URL", "http://127.0.0.1:11434/api/chat")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen3-vl:4b")
VISION_ENABLED = os.getenv("VISION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

SYSTEM_PROMPT = """Kamu adalah modul computer vision pendamping untuk sistem CDSS mata.
Tugasmu BUKAN menegakkan diagnosis. Analisis hanya apa yang terlihat pada foto dan nyatakan keterbatasan.
Jangan mengarang temuan yang tidak terlihat. Jangan menyimpulkan penyakit, obat, atau tindakan terapi.
Gunakan istilah visual/oftalmologi yang bersifat deskriptif. Bila foto tidak cukup jelas, katakan tidak dapat dinilai.
Output HARUS JSON valid tanpa markdown, dengan schema:
{
  "photo_type":"anterior_eye|fundus|eyelid_periocular|unknown",
  "laterality":"OD|OS|OU|unknown",
  "quality":"good|fair|poor",
  "visible_findings":[{"finding":"...","confidence":0.0,"evidence":"..."}],
  "red_flag_visuals":[{"finding":"...","confidence":0.0,"evidence":"..."}],
  "limitations":["..."],
  "summary":"..."
}
confidence adalah keyakinan visual terhadap keberadaan TEMUAN, bukan probabilitas penyakit."""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("Respons vision bukan object JSON.")
    return obj


def _normalise(obj: dict[str, Any]) -> dict[str, Any]:
    obj.setdefault("photo_type", "unknown")
    obj.setdefault("laterality", "unknown")
    obj.setdefault("quality", "fair")
    obj.setdefault("visible_findings", [])
    obj.setdefault("red_flag_visuals", [])
    obj.setdefault("limitations", [])
    obj.setdefault("summary", "")
    for key in ("visible_findings", "red_flag_visuals"):
        arr = obj.get(key)
        if not isinstance(arr, list):
            obj[key] = []
            continue
        cleaned = []
        for item in arr[:12]:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "finding": str(item.get("finding", ""))[:240],
                "confidence": max(0.0, min(1.0, float(item.get("confidence", 0) or 0))),
                "evidence": str(item.get("evidence", ""))[:320],
            })
        obj[key] = cleaned
    obj["limitations"] = [str(x)[:240] for x in (obj.get("limitations") or [])[:10]]
    obj["summary"] = str(obj.get("summary", ""))[:600]
    return obj


def analyze_with_vision(raw: bytes, mime: str, clinical_context: str = "") -> dict[str, Any]:
    if not VISION_ENABLED:
        return {"enabled": False, "available": False, "reason": "VISION_ENABLED=false"}

    encoded = base64.b64encode(raw).decode("ascii")
    context = clinical_context.strip()
    user_prompt = (
        "Analisis foto berikut secara deskriptif. Prioritaskan struktur yang tampak, laterality, "
        "kualitas foto, dan temuan visual yang benar-benar terlihat."
    )
    if context:
        user_prompt += "\nKonteks klinis tersedia untuk membantu orientasi, tetapi jangan biarkan konteks membuatmu mengarang temuan gambar:\n" + context[:4000]

    payload = {
        "model": VISION_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt, "images": [encoded]},
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(os.getenv("VISION_TIMEOUT", "120"))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"enabled": True, "available": False, "reason": f"Vision provider tidak terhubung: {exc.reason}"}
    except Exception as exc:
        return {"enabled": True, "available": False, "reason": f"Vision provider gagal: {exc}"}

    content = (((body or {}).get("message") or {}).get("content")) or ""
    try:
        parsed = _normalise(_extract_json(content))
    except Exception as exc:
        return {"enabled": True, "available": False, "reason": f"Output vision bukan JSON yang valid: {exc}", "raw_preview": content[:1000]}
    return {
        "enabled": True,
        "available": True,
        "provider": "ollama",
        "model": VISION_MODEL,
        "analysis": parsed,
    }
