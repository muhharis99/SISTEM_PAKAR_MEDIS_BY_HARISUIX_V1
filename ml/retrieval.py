from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.sparse import load_npz

from ml.preprocess import clean_text, age_group


class DiagnosisRetriever:
    def __init__(self, index_dir: str | Path):
        index_dir = Path(index_dir)
        self.index_dir = index_dir
        self.vectorizer = joblib.load(index_dir / "tfidf.joblib")
        self.matrix = load_npz(index_dir / "matrix.npz")
        with (index_dir / "metadata.json").open("r", encoding="utf-8") as f:
            self.metadata: list[dict[str, Any]] = json.load(f)
        with (index_dir / "diagnoses.json").open("r", encoding="utf-8") as f:
            self.label_counts: dict[str, int] = json.load(f)

    def _make_query(self, payload: dict[str, Any]) -> str:
        parts = [
            clean_text(payload.get("anamnese", "")),
            clean_text(payload.get("riwayat_sekarang", "")),
            clean_text(payload.get("periksa", "")),
            clean_text(payload.get("alergi", "")),
        ]
        age = payload.get("age")
        if age is not None:
            try:
                parts.append(age_group(int(age)).lower())
            except Exception:
                pass
        return " ".join(p for p in parts if p)

    def analyze(self, payload: dict[str, Any], top_n: int = 5, k_neighbors: int = 40) -> dict[str, Any]:
        query = self._make_query(payload)
        if not query:
            raise ValueError("Masukkan minimal anamnesa atau hasil pemeriksaan.")
        qvec = self.vectorizer.transform([query])
        sims = (self.matrix @ qvec.T).toarray().ravel()
        k = min(k_neighbors, len(sims))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]

        agg = defaultdict(lambda: {"weighted": 0.0, "max_similarity": 0.0, "support": 0, "best_idx": None})
        neighbors = []
        for pos in idx:
            sim = float(max(0.0, sims[pos]))
            if sim <= 0:
                continue
            case = self.metadata[int(pos)]
            labels = case.get("diagnosis_labels") or []
            share = sim / max(len(labels), 1)
            for label in labels:
                a = agg[label]
                a["weighted"] += share
                a["max_similarity"] = max(a["max_similarity"], sim)
                a["support"] += 1
                if a["best_idx"] is None or sim > float(self.metadata[a["best_idx"]].get("_similarity", 0.0)):
                    a["best_idx"] = int(pos)
            if len(neighbors) < min(k, 12):
                neighbors.append({"similarity": round(sim, 4), "case": self._public_case(case)})

        ranked = sorted(agg.items(), key=lambda kv: (kv[1]["weighted"], kv[1]["max_similarity"], kv[1]["support"]), reverse=True)
        if not ranked:
            return {"query": query, "results": [], "similar_cases": []}

        max_weight = ranked[0][1]["weighted"] or 1.0
        results = []
        for label, a in ranked[: max(1, top_n)]:
            confidence = min(100.0, (a["weighted"] / max_weight) * 100.0)
            best = self.metadata[a["best_idx"]] if a["best_idx"] is not None else None
            parsed = self._split_label(label)
            results.append({
                "label": label,
                "code": parsed[0],
                "name": parsed[1],
                "kind": "icd10" if parsed[0] else "free_text",
                "confidence": round(confidence, 2),
                "support_cases": a["support"],
                "max_similarity": round(a["max_similarity"], 4),
                "example": self._public_case(best) if best else None,
            })
        return {"query": query, "results": results, "similar_cases": neighbors}

    @staticmethod
    def _split_label(label: str) -> tuple[str | None, str]:
        if " - " in label and len(label.split(" - ", 1)[0]) >= 3:
            code, name = label.split(" - ", 1)
            if code[:1].isalpha() and code[1:3].isdigit():
                return code, name
        return None, label

    @staticmethod
    def _public_case(case: dict[str, Any] | None) -> dict[str, Any] | None:
        if not case:
            return None
        return {
            "age_group": case.get("age_group"),
            "visit_year": case.get("visit_year"),
            "kd_poli": case.get("kd_poli"),
            "anamnese": case.get("anamnese", "")[:360],
            "periksa": case.get("periksa", "")[:500],
            "diagnoses": case.get("diagnosis_labels", [])[:8],
        }

    def similar_cases(self, text: str, limit: int = 20, diagnosis: str | None = None) -> list[dict[str, Any]]:
        q = clean_text(text)
        if not q:
            return []
        qvec = self.vectorizer.transform([q])
        sims = (self.matrix @ qvec.T).toarray().ravel()
        idx = np.argsort(-sims)
        out = []
        for pos in idx:
            if sims[pos] <= 0:
                break
            case = self.metadata[int(pos)]
            if diagnosis and diagnosis.lower() not in " | ".join(case.get("diagnosis_labels", [])).lower():
                continue
            item = self._public_case(case)
            item["similarity"] = round(float(sims[pos]), 4)
            out.append(item)
            if len(out) >= limit:
                break
        return out
