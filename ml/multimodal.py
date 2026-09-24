from __future__ import annotations

from typing import Any


def _map_results(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(x.get("label")): x for x in items}


def fuse_results(clinical: list[dict[str, Any]], visual: list[dict[str, Any]], clinical_weight: float = 0.70) -> list[dict[str, Any]]:
    image_weight = 1.0 - clinical_weight
    c = _map_results(clinical)
    v = _map_results(visual)
    labels = list(dict.fromkeys([x.get("label") for x in clinical] + [x.get("label") for x in visual]))
    out = []
    for label in labels:
        if not label:
            continue
        cr = c.get(label)
        vr = v.get(label)
        cs = float(cr.get("confidence", 0) or 0) / 100.0 if cr else 0.0
        vs = float(vr.get("confidence", 0) or 0) / 100.0 if vr else 0.0
        score = (clinical_weight * cs + image_weight * vs) * 100.0
        if cr and vr:
            consistency = "tinggi"
        elif cr:
            consistency = "klinis"
        else:
            consistency = "visual"
        base = cr or vr
        out.append({
            "label": label,
            "code": base.get("code"),
            "name": base.get("name"),
            "kind": base.get("kind"),
            "fusion_score": round(score, 2),
            "clinical_support": round(cs * 100.0, 2),
            "visual_support": round(vs * 100.0, 2),
            "consistency": consistency,
            "support_cases": max(int((cr or {}).get("support_cases", 0) or 0), 0),
            "clinical_example": (cr or {}).get("example"),
        })
    out.sort(key=lambda x: x["fusion_score"], reverse=True)
    return out[:10]
