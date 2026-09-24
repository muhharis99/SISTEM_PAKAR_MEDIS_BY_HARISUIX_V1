from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
import sys

import joblib
import numpy as np
from scipy.sparse import save_npz
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.preprocess import write_clean_jsonl
RAW = Path(os.getenv("RAW_CSV", ROOT / "data/raw/MATA_DIAGNOSA_2.csv"))
PROCESSED = Path(os.getenv("PROCESSED_DIR", ROOT / "data/processed"))
INDEX = Path(os.getenv("INDEX_DIR", ROOT / "data/index"))
CASES = PROCESSED / "cases.jsonl"
VECTORIZER = INDEX / "tfidf.joblib"
MATRIX = INDEX / "matrix.npz"
META = INDEX / "metadata.json"
DIAG = INDEX / "diagnoses.json"


def main() -> None:
    INDEX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    rebuild = not CASES.exists()
    if CASES.exists():
        try:
            rebuild = sum(1 for _ in CASES.open("r", encoding="utf-8")) < 90000
        except Exception:
            rebuild = True
    if rebuild:
        tmp = CASES.with_suffix(".tmp")
        if tmp.exists():
            tmp.unlink()
        summary = write_clean_jsonl(RAW, tmp)
        tmp.replace(CASES)
        print("Preprocess:", summary)

    texts = []
    meta = []
    label_counts = Counter()
    with CASES.open("r", encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            texts.append(case["text"])
            meta.append(case)
            label_counts.update(case["diagnosis_labels"])

    print(f"Indexing {len(texts):,} cases...")
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=2,
        max_features=40000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)
    joblib.dump(vectorizer, VECTORIZER, compress=3)
    save_npz(MATRIX, matrix, compressed=True)

    # Metadatas are stored separately so retrieval never needs the raw patient fields.
    with META.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    with DIAG.open("w", encoding="utf-8") as f:
        json.dump(label_counts, f, ensure_ascii=False, indent=2)

    info = {
        "cases": len(texts),
        "features": int(matrix.shape[1]),
        "matrix_shape": [int(x) for x in matrix.shape],
        "vectorizer": "TF-IDF word unigrams+bigrams",
        "max_features": 40000,
        "min_df": 2,
    }
    (INDEX / "index_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
