from __future__ import annotations

import hashlib
import io
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def _blur_score(gray: np.ndarray) -> float:
    """Laplacian-like variance using only NumPy, so tidak perlu OpenCV."""
    gray = gray.astype(np.float32)
    d2x = gray[:, 2:] - 2.0 * gray[:, 1:-1] + gray[:, :-2]
    d2y = gray[2:, :] - 2.0 * gray[1:-1, :] + gray[:-2, :]
    return float((np.var(d2x) + np.var(d2y)) / 2.0)


def _pct(v: float) -> float:
    return round(float(v) * 100.0, 2)


def analyze_image_bytes(raw: bytes, mime: str) -> dict[str, Any]:
    if mime.lower() not in ALLOWED_MIME:
        raise ValueError("Format gambar tidak didukung.")
    if len(raw) > MAX_BYTES:
        raise ValueError("Ukuran gambar melebihi batas 10 MB.")

    digest = hashlib.sha256(raw).hexdigest()
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
    except UnidentifiedImageError as exc:
        raise ValueError("File bukan gambar yang valid.") from exc
    except Exception as exc:
        raise ValueError("Gambar rusak atau tidak dapat dibaca.") from exc

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")
    width, height = img.size
    if width < 160 or height < 160:
        size_flag = "Terlalu kecil"
    elif width < 640 or height < 480:
        size_flag = "Cukup"
    else:
        size_flag = "Baik"

    # Downsample agar analisa cepat dan konsisten.
    sample = img.copy()
    sample.thumbnail((1024, 1024))
    arr = np.asarray(sample, dtype=np.float32) / 255.0
    gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])
    brightness = float(gray.mean())
    contrast = float(gray.std())
    blur = _blur_score(gray)

    red = arr[:, :, 0]
    green = arr[:, :, 1]
    blue = arr[:, :, 2]
    redness = float(np.mean(np.maximum(red - (green + blue) / 2.0, 0.0)))
    warm_ratio = float(np.mean((red > blue * 1.12) & (red > green * 1.04)))
    highlight_ratio = float(np.mean(gray > 0.97))
    shadow_ratio = float(np.mean(gray < 0.06))

    warnings: list[str] = []
    observations: list[str] = []

    if brightness < 0.22:
        warnings.append("Foto terlalu gelap.")
    elif brightness > 0.88:
        warnings.append("Foto terlalu terang/berpotensi overexposure.")
    else:
        observations.append("Pencahayaan global cukup untuk screening dasar.")

    if contrast < 0.10:
        warnings.append("Kontras rendah sehingga detail halus mungkin sulit dinilai.")
    if blur < 18:
        warnings.append("Indikator blur cukup tinggi; pertimbangkan foto ulang dengan fokus lebih baik.")
    elif blur > 55:
        observations.append("Detail tepi relatif tajam pada resolusi sampel.")

    if size_flag != "Baik":
        warnings.append(f"Resolusi {width}×{height} {size_flag.lower()} untuk analisa visual.")
    if highlight_ratio > 0.15:
        warnings.append("Sebagian area gambar sangat terang; refleks cahaya dapat mengganggu penilaian.")
    if shadow_ratio > 0.25:
        warnings.append("Sebagian area gambar sangat gelap; detail mungkin hilang.")

    if redness > 0.08 or warm_ratio > 0.20:
        observations.append("Terdapat dominansi rona merah/hangat pada sebagian area gambar.")

    quality_status = "baik"
    if len(warnings) >= 3:
        quality_status = "perlu_foto_ulang"
    elif warnings:
        quality_status = "cukup_dengan_catatan"

    return {
        "sha256": digest,
        "filename_safe": "uploaded-image",
        "image": {
            "width": width,
            "height": height,
            "mime": mime,
            "bytes": len(raw),
        },
        "quality": {
            "status": quality_status,
            "brightness": round(brightness, 4),
            "contrast": round(contrast, 4),
            "blur_score": round(blur, 2),
            "redness_index": round(redness, 4),
            "warm_ratio": round(warm_ratio, 4),
            "highlight_ratio": _pct(highlight_ratio),
            "shadow_ratio": _pct(shadow_ratio),
        },
        "observations": observations,
        "warnings": warnings,
        "clinical_use": [
            "Gunakan foto sebagai informasi pendukung dan cocokkan dengan anamnesa serta pemeriksaan langsung.",
            "Jangan gunakan hasil analisa visual dasar ini sebagai diagnosis final.",
            "Untuk klasifikasi penyakit berbasis foto, pasang model oftalmologi yang tervalidasi dan lakukan validasi klinis setempat.",
        ],
    }
