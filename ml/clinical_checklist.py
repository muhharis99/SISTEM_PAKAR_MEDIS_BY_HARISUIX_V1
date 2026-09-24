from __future__ import annotations

import re
from typing import Any

# Checklist ini bersifat kelengkapan data, bukan aturan diagnosis.
PATTERNS = {
    "visual_acuity": re.compile(r"\b(vod|vos|vou|visus|6/\d+|fc|cc)\b", re.I),
    "iop": re.compile(r"\b(tio|iop|tonometri|mmhg)\b", re.I),
    "laterality": re.compile(r"\b(od|os|ou|kanan|kiri|bilateral)\b", re.I),
    "cornea": re.compile(r"\b(cornea|kornea|infiltrat|ulkus|ulcer|edema cornea|fluorescein)\b", re.I),
    "conjunctiva": re.compile(r"\b(konjungtiva|conjunctiva|injeksi|hiperemis)\b", re.I),
    "pupil": re.compile(r"\b(pupil|anisokor|refleks cahaya|rapd)\b", re.I),
    "fundus": re.compile(r"\b(fundus|retina|papil|diskus|makula|cup.?disk|cdr|vitreus)\b", re.I),
    "symptoms": re.compile(r"\b(nyeri|pain|merah|red|fotofobia|silau|gatal|berair|sekret|kabur|blur|penurunan penglihatan)\b", re.I),
}

LABELS = {
    "visual_acuity": "Visus / VOD-VOS",
    "iop": "TIO / IOP",
    "laterality": "Laterality OD/OS/OU",
    "cornea": "Kornea",
    "conjunctiva": "Konjungtiva",
    "pupil": "Pupil",
    "fundus": "Fundus / retina",
    "symptoms": "Gejala utama",
}


def build_clinical_checklist(text: str, age: int | None = None) -> dict[str, Any]:
    text = text or ""
    present: list[str] = []
    missing: list[str] = []

    for key, pattern in PATTERNS.items():
        if pattern.search(text):
            present.append(key)
        else:
            missing.append(key)

    core = [k for k in ("visual_acuity", "laterality", "cornea", "conjunctiva", "symptoms")]
    present_core = sum(1 for k in core if k in present)
    completeness = round((present_core / len(core)) * 100.0, 1)

    suggestions: list[str] = []
    if "laterality" not in present:
        suggestions.append("Lengkapi mata yang terkena: OD/OS/OU.")
    if "visual_acuity" not in present:
        suggestions.append("Pertimbangkan dokumentasi visus/VOD-VOS.")
    if "iop" not in present:
        suggestions.append("Pertimbangkan TIO bila relevan dengan pemeriksaan klinis.")
    if "pupil" not in present:
        suggestions.append("Dokumentasikan pupil/refleks bila relevan.")
    if "fundus" not in present:
        suggestions.append("Dokumentasikan fundus/retina bila indikasi klinis memerlukannya.")

    return {
        "completeness": completeness,
        "present": [{"key": k, "label": LABELS[k]} for k in present],
        "missing": [{"key": k, "label": LABELS[k]} for k in missing],
        "suggestions": suggestions,
        "age_available": age is not None,
        "disclaimer": "Checklist ini hanya membantu kelengkapan dokumentasi dan tidak menentukan diagnosis atau keputusan terapi.",
    }
