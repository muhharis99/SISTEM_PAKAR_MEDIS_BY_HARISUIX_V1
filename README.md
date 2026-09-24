# Sistem CDSS Mata — Multimodal Clinical Decision Support

Aplikasi web untuk membantu tenaga medis menganalisis kasus mata dengan menggabungkan:

1. **Clinical retrieval** dari histori rekam medis menggunakan TF-IDF + cosine similarity.
2. **Clinical feature extraction** untuk laterality, VOD/VOS, TIO, CDR, dan tanda klinis sederhana.
3. **Image quality gate** untuk memeriksa resolusi, exposure, contrast, blur, dan area terang/gelap.
4. **Vision-language analysis opsional** melalui Ollama + Qwen3-VL.
5. **Visual-to-history retrieval**: temuan visual terstruktur dijadikan query ke histori kasus.
6. **Heuristic evidence fusion**: clinical 70% + visual 30%, ditampilkan sebagai dukungan evidence, bukan probabilitas penyakit.
7. **Kasus historis anonim** sebagai explainability.
8. **Feedback koreksi dokter + audit log + RBAC**.

Sistem **bukan pengganti dokter**. Hasil visual maupun fusion harus diverifikasi oleh tenaga medis berwenang.

## Arsitektur

- Backend: FastAPI + SQLAlchemy
- DB lokal: SQLite; production dapat memakai PostgreSQL
- Retrieval: scikit-learn TF-IDF + cosine similarity
- Vision provider: HTTP API kompatibel Ollama
- Frontend: HTML/CSS/JavaScript tanpa build step
- Dataset: `data/raw/MATA_DIAGNOSA_2.csv`
- Index: `data/index/`

## Windows 10 + Git Bash

Cara termudah:

```bash
cd ~/Downloads/diagnosa_mata_system
bash start_windows_gitbash.sh
```

Script tersebut menggunakan `.venv/Scripts/python.exe` secara langsung sehingga tidak bergantung pada aktivasi shell.

Akun demo:

- `admin / admin123`
- `dokter / dokter123`
- `perawat / perawat123`

Ganti password dan `APP_SECRET` sebelum produksi.

## Vision AI lokal

Install Ollama di Windows lalu:

```bash
ollama pull qwen3-vl:4b
ollama run qwen3-vl:4b
```

Qwen3-VL tersedia dalam beberapa ukuran; registry Ollama mencantumkan 2B, 4B, 8B, 30B, 32B, dan ukuran lebih besar. Model 4B tercatat sekitar 3,3 GB dan model 8B sekitar 6,1 GB. citeturn467190search0turn467190search3turn467190search6

Default environment:

```text
VISION_ENABLED=true
VISION_PROVIDER_URL=http://127.0.0.1:11434/api/chat
VISION_MODEL=qwen3-vl:4b
VISION_TIMEOUT=120
```

Untuk Docker Desktop Windows, `docker-compose.yml` memakai `host.docker.internal` agar container dapat mengakses Ollama pada host.

## Alur multimodal

```text
Foto
  ↓
Quality Gate
  ↓
Vision-Language Model
  ↓
Visible findings / laterality / limitations
  ↓
Visual Retrieval ─────────┐
                          ├── Evidence Fusion ──> Review Dokter
Clinical Input → Retrieval┘
```

### Evidence Fusion

Bobot awal yang dipakai adalah:

- Clinical support: 70%
- Visual support: 30%

Bobot ini **heuristik**, bukan hasil training model klinis dan bukan probabilitas diagnosis.

## Endpoint penting

- `POST /api/auth/login`
- `POST /api/analisa`
- `POST /api/analisa-gambar`
- `POST /api/analisa-multimodal`
- `GET /api/kasus-mirip`
- `GET /api/statistik`
- `GET /api/riwayat`
- `POST /api/feedback`
- `GET /api/kamus`
- `GET /api/evaluasi`
- `GET /health`

## Pengujian baseline retrieval

- Recall@3: **83,40%**
- Recall@5: **87,20%**
- MRR: **77,12%**
- Test: 500 kasus holdout patient-group

Metrik tersebut hanya menunjukkan retrieval pada histori yang tersedia, bukan validasi klinis model foto maupun jaminan diagnosis.

## Batasan klinis

Vision-language model generik dapat mendeskripsikan konten gambar tetapi bukan model diagnosis oftalmologi tervalidasi. Sistem karena itu memisahkan `visible findings`, `clinical support`, dan `visual support`. Sebelum produksi diperlukan dataset foto berlabel dokter, external test set, calibration, subgroup analysis, review keselamatan, dan pilot prospektif.

## Go-live checklist

- [ ] Ganti akun/password demo dan secret aplikasi.
- [ ] Gunakan HTTPS/TLS.
- [ ] Gunakan PostgreSQL production.
- [ ] Batasi akses dataset mentah dan mapping PII.
- [ ] Validasi RBAC dan audit trail.
- [ ] Validasi model retrieval dan vision oleh dokter spesialis mata.
- [ ] Uji external test set dan subgroup.
- [ ] Pilot terbatas sebelum produksi.
- [ ] Tetapkan retensi/penghapusan data sesuai kebijakan dan UU PDP.
# SISTEM_PAKAR_MEDIS_BY_HARISUIX_V1
