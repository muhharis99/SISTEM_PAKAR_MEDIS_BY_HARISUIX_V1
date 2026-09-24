from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ICD_RE = re.compile(r"^([A-Z]\d{2}(?:\.\d{1,4})?)\s*(?:[-:]\s*)?(.*)$", re.I)
DIAG_SPLIT_RE = re.compile(r"@@,|@@|\n")
NONWORD_RE = re.compile(r"[^\w\s./()+-]", re.UNICODE)
SPACE_RE = re.compile(r"\s+")

AGE_BANDS = (
    (0, 0, "Neonatus"),
    (1, 14, "Anak"),
    (15, 64, "Dewasa"),
    (65, 200, "Geriatri"),
)


def clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).lower()
    text = text.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    text = NONWORD_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def parse_diagnoses(value: object) -> list[dict]:
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    out: list[dict] = []
    seen = set()
    for item in DIAG_SPLIT_RE.split(raw):
        item = SPACE_RE.sub(" ", item.strip())
        if not item:
            continue
        m = ICD_RE.match(item)
        if m:
            code = m.group(1).upper()
            name = m.group(2).strip().upper()
            key = (code, name)
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": code, "name": name, "label": f"{code} - {name}", "kind": "icd10"})
        else:
            name = item.upper()
            key = (None, name)
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": None, "name": name, "label": name, "kind": "free_text"})
    return out


def age_at_visit(birth: object, visit: object) -> int | None:
    try:
        b = pd.to_datetime(birth, errors="coerce")
        v = pd.to_datetime(visit, errors="coerce")
        if pd.isna(b) or pd.isna(v):
            return None
        age = int(v.year - b.year - ((v.month, v.day) < (b.month, b.day)))
        return max(0, age)
    except Exception:
        return None


def age_group(age: int | None) -> str:
    if age is None:
        return "Tidak diketahui"
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "Tidak diketahui"


def pseudonymize(record_id: object) -> str:
    raw = str(record_id).strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_case_text(row: pd.Series) -> str:
    parts = [
        clean_text(row.get("anamnese", "")),
        clean_text(row.get("riwayat_sekarang", "")),
        clean_text(row.get("periksa", "")),
        clean_text(row.get("alergi", "")),
    ]
    return " ".join(p for p in parts if p)


def transform_chunk(df: pd.DataFrame) -> Iterable[dict]:
    df = df.copy()
    visit = pd.to_datetime(df["tgl_masuk"], errors="coerce")
    birth = pd.to_datetime(df["tgl_lahir"], errors="coerce")
    age = (visit.dt.year - birth.dt.year - ((visit.dt.month < birth.dt.month) | ((visit.dt.month == birth.dt.month) & (visit.dt.day < birth.dt.day))))
    age = age.where(~visit.isna() & ~birth.isna(), None)
    age = age.clip(lower=0)
    df["_visit_year"] = visit.dt.year.astype("Int64")
    df["_visit_date"] = visit.dt.strftime("%Y-%m-%d").fillna("")
    df["_age"] = age.astype("Int64")
    cols = list(df.columns)
    for values in df.itertuples(index=False, name=None):
        row = dict(zip(cols, values))
        dx = parse_diagnoses(row.get("diagnosa", ""))
        if not dx:
            continue
        text = " ".join(p for p in [clean_text(row.get("anamnese", "")), clean_text(row.get("riwayat_sekarang", "")), clean_text(row.get("periksa", "")), clean_text(row.get("alergi", ""))] if p)
        if not text:
            continue
        av = row.get("_age")
        age_val = int(av) if av is not None and str(av) != "<NA>" else None
        clean_dx = [d["label"] for d in dx]
        yield {
            "case_id": pseudonymize(row.get("id", "")),
            "patient_id": pseudonymize(row.get("no_reg", "")),
            "visit_year": int(row["_visit_year"]) if row.get("_visit_year") is not None and str(row.get("_visit_year")) != "<NA>" else None,
            "visit_date": (str(row.get("_visit_date")) if row.get("_visit_date") not in (None, "", "nan", "NaT") else None),
            "age": age_val,
            "age_group": age_group(age_val),
            "kd_dr": str(row.get("kd_dr", "") or ""),
            "kd_poli": str(row.get("kd_poli", "") or ""),
            "anamnese": clean_text(row.get("anamnese", "")),
            "periksa": clean_text(row.get("periksa", "")),
            "riwayat_sekarang": clean_text(row.get("riwayat_sekarang", "")),
            "alergi": clean_text(row.get("alergi", "")),
            "text": text,
            "diagnoses": dx,
            "diagnosis_labels": clean_dx,
        }


def write_clean_jsonl(csv_path: str | Path, out_path: str | Path, chunksize: int = 20000) -> dict:
    csv_path = Path(csv_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    cases = 0
    unique_patients: set[str] = set()
    labels: dict[str, int] = {}

    with out_path.open("w", encoding="utf-8") as f:
        for df in pd.read_csv(csv_path, chunksize=chunksize, dtype=str, keep_default_na=False):
            total += len(df)
            for case in transform_chunk(df):
                cases += 1
                unique_patients.add(case["patient_id"])
                for label in case["diagnosis_labels"]:
                    labels[label] = labels.get(label, 0) + 1
                f.write(json.dumps(case, ensure_ascii=False) + "\n")
    return {"source_rows": total, "indexed_cases": cases, "unique_pseudonymous_patients": len(unique_patients), "unique_diagnosis_labels": len(labels)}
