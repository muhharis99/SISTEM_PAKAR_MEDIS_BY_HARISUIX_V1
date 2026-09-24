from __future__ import annotations

import json
import random
import re
from pathlib import Path
import sys

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupShuffleSplit

from sklearn.metrics.pairwise import linear_kernel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.preprocess import build_case_text, parse_diagnoses, pseudonymize
CSV = ROOT / "data/raw/MATA_DIAGNOSA_2.csv"
OUT = ROOT / "docs/evaluation.json"


def main() -> None:
    df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    df["text"] = df.apply(build_case_text, axis=1)
    df["labels"] = df["diagnosa"].map(lambda x: [d["label"] for d in parse_diagnoses(x)])
    df = df[(df.text.str.len() > 0) & (df.labels.str.len() > 0)].copy()
    df["group"] = df["no_reg"].map(pseudonymize)

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(splitter.split(df, groups=df["group"]))
    train = df.iloc[train_idx].reset_index(drop=True)
    test = df.iloc[test_idx].reset_index(drop=True)

    # Evaluasi praktis: 3.000 kasus uji dipilih deterministik agar script tetap ringan.
    sample_n = min(500, len(test))
    test = test.sample(sample_n, random_state=42).reset_index(drop=True)

    vec = TfidfVectorizer(lowercase=True, strip_accents="unicode", ngram_range=(1, 2), min_df=2, max_features=40000, sublinear_tf=True, norm="l2")
    X_train = vec.fit_transform(train.text.tolist())
    X_test = vec.transform(test.text.tolist())
    scores = linear_kernel(X_test, X_train, dense_output=False)

    recall3 = recall5 = 0.0
    mrr = 0.0
    for i in range(X_test.shape[0]):
        row = scores.getrow(i)
        if row.nnz == 0:
            continue
        k = min(40, row.nnz)
        # sparse row -> top-k train indices
        order = row.data.argsort()[-k:][::-1]
        idx = row.indices[order]
        sims = row.data[order]
        agg = {}
        for j, sim in zip(idx, sims):
            labels = train.iloc[int(j)].labels
            share = float(sim) / max(len(labels), 1)
            for lab in labels:
                agg[lab] = agg.get(lab, 0.0) + share
        ranked = [x[0] for x in sorted(agg.items(), key=lambda x: x[1], reverse=True)]
        actual = set(test.iloc[i].labels)
        if actual.intersection(ranked[:3]): recall3 += 1
        if actual.intersection(ranked[:5]): recall5 += 1
        for rank, lab in enumerate(ranked, start=1):
            if lab in actual:
                mrr += 1.0 / rank
                break

    metrics = {
        "recall_at_3": round(recall3 / len(test), 4),
        "recall_at_5": round(recall5 / len(test), 4),
        "mrr": round(mrr / len(test), 4),
        "test_cases": int(len(test)),
        "train_cases": int(len(train)),
        "split": "GroupShuffleSplit 80/20 by pseudonymous no_reg, sample 500 test cases",
        "note": "Retrospective retrieval metric only; does not constitute clinical validation or calibrated diagnostic probability.",
    }
    OUT.write_text(json.dumps({"metrics": metrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
