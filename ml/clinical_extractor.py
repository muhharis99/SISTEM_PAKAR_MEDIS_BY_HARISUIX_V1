from __future__ import annotations

import re
from typing import Any

PATTERNS = {
    "vod": r"\b(?:vod|visus\s*od)\s*[:=]?\s*([0-9]+\s*/\s*[0-9]+|fc\s*[^,; ]+|1/300|1/60)\b",
    "vos": r"\b(?:vos|visus\s*os)\s*[:=]?\s*([0-9]+\s*/\s*[0-9]+|fc\s*[^,; ]+|1/300|1/60)\b",
    "tio_od": r"\b(?:tio\s*od|od\s*tio)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)",
    "tio_os": r"\b(?:tio\s*os|os\s*tio)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)",
    "cdr_od": r"\b(?:cdr\s*od|od\s*cdr)\s*[:=]?\s*(0(?:[.,][0-9]+)?|1(?:[.,]0+)?)",
    "cdr_os": r"\b(?:cdr\s*os|os\s*cdr)\s*[:=]?\s*(0(?:[.,][0-9]+)?|1(?:[.,]0+)?)",
}

LATERALITY = {
    "od": [" od ", " mata kanan", "kanan"],
    "os": [" os ", " mata kiri", "kiri"],
    "ou": [" ou ", " kedua mata", "bilateral"],
}

SIGNS = [
    ("merah/hiperemis", ["mata merah", "hiperemis", "injeksi", "redness"]),
    ("nyeri", ["nyeri", "sakit", "pain"]),
    ("fotofobia", ["fotofobia", "photophobia"]),
    ("gatal", ["gatal", "itch"]),
    ("air mata berlebih", ["lakrimasi", "berair", "air mata berlebih"]),
    ("sekret", ["sekret", "belekan", "discharge"]),
    ("edema", ["edem", "edema", "bengkak"]),
    ("infiltrat kornea", ["infiltrat kornea", "infiltrat cornea", "corneal infiltrate"]),
    ("ulcus/ulkus kornea", ["ulkus kornea", "ulcus kornea", "ulcus cornea"]),
    ("opasitas kornea", ["opasitas kornea", "cornea opaque", "keruh kornea"]),
    ("pupil abnormal", ["anisokor", "pupil", "midriasis", "miosis"]),
    ("trauma/benda asing", ["corpal", "benda asing", "trauma", "kelilipan"]),
]


def extract_clinical_features(text: str) -> dict[str, Any]:
    t = f" {str(text or '').lower()} "
    out: dict[str, Any] = {"laterality": "unknown", "measurements": {}, "signs": []}
    hits = []
    for side, terms in LATERALITY.items():
        if any(term in t for term in terms):
            hits.append(side)
    if "od" in hits and "os" in hits:
        out["laterality"] = "OU"
    elif hits:
        out["laterality"] = hits[0].upper()

    for name, pat in PATTERNS.items():
        m = re.search(pat, t, flags=re.I)
        if m:
            out["measurements"][name] = m.group(1).replace(" ", "")

    for label, terms in SIGNS:
        if any(term in t for term in terms):
            out["signs"].append(label)
    return out
