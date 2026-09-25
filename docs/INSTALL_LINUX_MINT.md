# Instalasi Lengkap — Linux Mint

Dokumentasi ini khusus untuk menjalankan **Sistem CDSS Mata / Multimodal Clinical Decision Support** pada Linux Mint.

Panduan mencakup: Ollama, Qwen3-VL, Python virtual environment, dependency, dataset index, konfigurasi Vision AI, menjalankan FastAPI, verifikasi, Case Workspace, dan troubleshooting.

## 0. Arsitektur lokal

```text
Linux Mint
│
├── Ollama service : 127.0.0.1:11434
│     └── qwen3-vl:2b / qwen3-vl:4b
│
└── CDSS Mata : 0.0.0.0:8000
      ├── FastAPI
      ├── SQLite (development)
      ├── TF-IDF retrieval
      └── Multimodal evidence
```

Ollama berjalan sebagai service lokal. Pada instalasi Linux resmi, Ollama menyediakan API lokal pada `127.0.0.1:11434`.

## 1. Persyaratan

Disarankan:
- Linux Mint 21/22 atau turunan Ubuntu yang kompatibel;
- Python 3.10+;
- Git;
- curl;
- RAM yang cukup untuk index TF-IDF dan model vision;
- ruang disk beberapa GB untuk model vision.

Verifikasi:

```bash
python3 --version
git --version
curl --version
```

Contoh environment yang sudah diuji pada mesin pengembang:

```text
Python 3.12.3
Git 2.43.0
Ollama 0.34.4
```

## 2. Install paket sistem

```bash
sudo apt update
sudo apt install -y git curl python3 python3-pip python3-venv build-essential
```

Jika `python3 -m venv` gagal karena modul venv tidak tersedia, pastikan paket `python3-venv` sudah terpasang.

## 3. Install Ollama

Gunakan installer Linux resmi Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Referensi resmi: https://ollama.com/download/linux

Verifikasi:

```bash
ollama --version
```

### 3.1 Pastikan service Ollama aktif

Installer Linux membuat service systemd. Cek:

```bash
sudo systemctl status ollama
```

Jika belum aktif:

```bash
sudo systemctl start ollama
sudo systemctl enable ollama
```

Tes API:

```bash
curl http://127.0.0.1:11434/api/tags
```

### 3.2 Jangan menjalankan `ollama serve` jika service sudah aktif

Jika API sudah berjalan pada port `11434`, menjalankan:

```bash
ollama serve
```

akan menghasilkan:

```text
bind: address already in use
```

Itu bukan error aplikasi; artinya port Ollama sudah dipakai oleh service yang berjalan.

## 4. Install model Vision

Project mendukung Qwen3-VL melalui API Ollama. Registry resmi Ollama mencantumkan ukuran 2B, 4B, 8B, 30B, 32B, dan 235B. Qwen3-VL membutuhkan Ollama 0.12.7 atau lebih baru.

Untuk komputer CPU-only atau RAM lebih terbatas, gunakan 2B:

```bash
ollama pull qwen3-vl:2b
```

Untuk komputer yang lebih kuat:

```bash
ollama pull qwen3-vl:4b
```

Verifikasi:

```bash
ollama list
```

Tes manual:

```bash
ollama run qwen3-vl:2b
```

atau:

```bash
ollama run qwen3-vl:4b
```

Model Ollama bukan command Linux. Jadi jangan menjalankan `qwen3-vl:2b` langsung; gunakan `ollama run qwen3-vl:2b`.

Keluar dari sesi model dengan `Ctrl+C` atau `/bye`.

## 5. Clone repository

```bash
cd ~/Downloads
git clone https://github.com/muhharis99/SISTEM_PAKAR_MEDIS_BY_HARISUIX_V1.git diagnosa_mata_system
cd ~/Downloads/diagnosa_mata_system
```

Jika project sudah pernah di-clone:

```bash
cd ~/Downloads/diagnosa_mata_system
git pull origin main
```

Cek commit:

```bash
git rev-parse --short HEAD
```

## 6. Buat Python virtual environment

```bash
cd ~/Downloads/diagnosa_mata_system
python3 -m venv .venv
source .venv/bin/activate
```

Prompt terminal akan berubah menjadi `(.venv)`.

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install dependency:

```bash
python -m pip install -r requirements.txt
```

## 7. Konfigurasi Vision AI

Backend membaca konfigurasi melalui environment variable.

Untuk Qwen3-VL 2B:

```bash
export VISION_ENABLED=true
export VISION_PROVIDER_URL=http://127.0.0.1:11434/api/chat
export VISION_MODEL=qwen3-vl:2b
export VISION_TIMEOUT=180
```

Untuk 4B:

```bash
export VISION_MODEL=qwen3-vl:4b
```

Verifikasi:

```bash
echo "$VISION_MODEL"
echo "$VISION_PROVIDER_URL"
```

## 8. Build index dataset

Dataset berada pada:

```text
data/raw/MATA_DIAGNOSA_2.csv
```

Pada clone baru, build index:

```bash
python scripts/build_index.py
```

Proses ini membuat:

```text
data/processed/cases.jsonl
data/index/tfidf.joblib
data/index/matrix.npz
data/index/metadata.json
data/index/diagnoses.json
data/index/index_info.json
```

Index saat ini dibangun dengan TF-IDF word unigram + bigram, maksimum 40.000 fitur.

Build pertama dapat membutuhkan waktu dan RAM yang cukup besar karena dataset berisi lebih dari 100 ribu kasus.

Setelah index selesai, **jangan menjalankan build index setiap kali start aplikasi**. Gunakan launcher Linux yang disediakan repository.

## 9. Syntax check

Untuk memastikan Python backend dan modul ML dapat di-import oleh interpreter:

```bash
python -m compileall -q backend ml
```

Jika tidak ada output, syntax check berhasil.

## 10. Jalankan aplikasi secara manual

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Buka:

```text
http://localhost:8000
```

Akun development:

```text
admin   / admin123
dokter  / dokter123
perawat / perawat123
```

Jangan gunakan password demo dan `APP_SECRET` default untuk production.

## 11. Jalankan dengan launcher Linux

Repository menyediakan:

```text
start_linux.sh
```

Berikan permission:

```bash
chmod +x start_linux.sh
```

Lalu:

```bash
./start_linux.sh
```

Launcher melakukan:

1. cek API Ollama;
2. cek model vision;
3. membuat `.venv` jika belum ada;
4. install dependency;
5. melewati rebuild index jika index lokal sudah lengkap;
6. menjalankan `compileall`;
7. menjalankan Uvicorn pada port 8000.

### 11.1 Menggunakan model 4B

```bash
VISION_MODEL=qwen3-vl:4b ./start_linux.sh
```

### 11.2 Menggunakan port berbeda

```bash
PORT=9000 ./start_linux.sh
```

## 12. Verifikasi Ollama + CDSS

### API Ollama

```bash
curl http://127.0.0.1:11434/api/tags
```

Pastikan `qwen3-vl:2b` atau `qwen3-vl:4b` muncul.

### Health API CDSS

Setelah web berjalan:

```bash
curl http://127.0.0.1:8000/health
```

Health response membedakan status Vision:

```text
ready
model_missing
offline
disabled
```

### Dashboard

Login kemudian buka **Dashboard → System Health**.

Target kondisi:

```text
Backend          ONLINE
Index            <jumlah kasus> kasus / <label> label
Vision provider  TERHUBUNG
Model            qwen3-vl:2b atau qwen3-vl:4b
Model status     ready
```

## 13. Tes analisa foto

1. Buka **Analisa Multimodal**.
2. Pilih mode **Foto saja**.
3. Upload JPG/PNG/WEBP.
4. Jalankan **Quality Check**.
5. Jalankan **Analisa Foto**.
6. Periksa panel **Visual Evidence**.

Jika Vision AI aktif, panel akan menampilkan evidence visual terstruktur seperti photo type, laterality, quality, visible findings, summary, dan limitations.

## 14. Tes multimodal

1. Pilih **Multimodal**.
2. Isi anamnesa.
3. Isi riwayat sekarang bila tersedia.
4. Isi pemeriksaan.
5. Upload foto.
6. Jalankan **Analisa Multimodal**.

Output dipisahkan menjadi:

```text
Clinical Evidence
Visual Evidence
Fusion Result
Documentation Checklist
Evidence Quality
Doctor Review
```

Fusion 70% clinical + 30% visual adalah heuristic relative evidence score, bukan probabilitas diagnosis terkalibrasi.

## 15. Case Workspace

Setiap analisa klinis dan multimodal dapat membuat `case_uid` anonim.

Menu:

```text
Case Workspace
```

Dari sana kasus dapat:

- dibuka kembali;
- ditinjau;
- diberi status `review`, `reviewed`, `corrected`, atau `archived`;
- diberi koreksi dokter;
- dicetak sebagai evidence report.

Foto tidak disimpan permanen sebagai file oleh endpoint analisa; hash SHA-256 foto digunakan untuk audit.

## 16. Menjalankan kembali setelah reboot

Karena Ollama dipasang sebagai service systemd, biasanya Anda hanya perlu:

```bash
sudo systemctl status ollama
cd ~/Downloads/diagnosa_mata_system
source .venv/bin/activate
VISION_MODEL=qwen3-vl:2b ./start_linux.sh
```

Jika service mati:

```bash
sudo systemctl start ollama
```

## 17. Troubleshooting

### `ollama: command not found`

Pastikan instalasi selesai dan buka terminal baru. Cek:

```bash
which ollama
ollama --version
```

### `bind: address already in use` saat `ollama serve`

Biasanya service Ollama sudah berjalan. Jangan menjalankan server kedua. Cek:

```bash
sudo systemctl status ollama
curl http://127.0.0.1:11434/api/tags
```

### `Vision provider tidak terhubung`

Cek:

```bash
curl http://127.0.0.1:11434/api/tags
```

Jika gagal:

```bash
sudo systemctl restart ollama
```

### `model_missing`

Pasang model:

```bash
ollama pull qwen3-vl:2b
```

atau:

```bash
ollama pull qwen3-vl:4b
```

### Index belum tersedia

Jalankan:

```bash
python scripts/build_index.py
```

### Uvicorn gagal dengan `IndentationError` atau `SyntaxError`

Jalankan sebelum server:

```bash
python -m compileall -q backend ml
```

Pastikan repository terbaru:

```bash
git pull origin main
```

### Port 8000 sudah digunakan

Gunakan port lain:

```bash
PORT=9000 ./start_linux.sh
```

Lalu buka `http://localhost:9000`.

## 18. Production checklist

- Ganti semua password demo.
- Ganti `APP_SECRET`.
- Gunakan HTTPS/TLS.
- Gunakan PostgreSQL production bila diperlukan.
- Batasi akses dataset mentah.
- Jangan memasukkan nama pasien, nomor RM, tanggal lahir, atau PII lain ke Case Workspace.
- Verifikasi audit trail dan RBAC.
- Validasi model retrieval dan vision dengan dokter spesialis mata.
- Gunakan external test set dan evaluasi subgroup.
- Tetapkan kebijakan retensi/penghapusan data sesuai regulasi.

## 19. Batasan klinis

Qwen3-VL adalah vision-language model umum. Kemampuan memahami gambar tidak sama dengan validasi sebagai model diagnosis oftalmologi. Sistem ini karena itu menampilkan evidence dan keterbatasan, bukan diagnosis final.

Model vision generik harus digunakan sebagai decision-support dan diverifikasi oleh tenaga medis yang berwenang.

## 20. Referensi resmi

- Ollama Linux: https://ollama.com/download/linux
- Ollama Qwen3-VL: https://ollama.com/library/qwen3-vl
- Repository CDSS Mata: https://github.com/muhharis99/SISTEM_PAKAR_MEDIS_BY_HARISUIX_V1