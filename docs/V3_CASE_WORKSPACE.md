# CDSS Mata V3 — Case Workspace

Versi V3 menambahkan workflow kasus yang persisten di samping analisa klinis, foto, dan multimodal.

## Mode analisa

- **Klinis saja**: anamnesa, riwayat, pemeriksaan → retrieval histori.
- **Foto saja**: quality gate + Vision AI + visual retrieval bila provider tersedia.
- **Multimodal**: clinical evidence + visual evidence + fusion heuristic.

## Case Workspace

Setiap analisa menghasilkan `case_uid` anonim, misalnya `CASE-20260924-AB12CD34`.

Kasus menyimpan:
- mode analisa;
- input klinis;
- ringkasan hasil;
- hash SHA-256 foto, bukan file foto;
- status `review`, `reviewed`, `corrected`, atau `archived`.

Foto tidak disimpan oleh endpoint analisa sebagai file permanen.

## Review dokter

Dokter/admin dapat menyimpan koreksi melalui panel **Doctor Review**. Koreksi dicatat sebagai feedback dan menandai kasus menjadi `corrected`.

## Laporan

Tombol **Cetak Laporan** membuka evidence report yang dapat dicetak / disimpan sebagai PDF dari browser.

## Vision health

Endpoint `/health` dan `/api/system/status` membedakan:
- provider disabled;
- provider offline;
- provider aktif tetapi model belum ada;
- provider + model siap.

Konfigurasi default:
- provider: Ollama local API;
- model: `qwen3-vl:4b`;
- URL: `http://127.0.0.1:11434/api/chat`.

## Keamanan dan batasan

Case Workspace tidak memiliki field khusus untuk nama pasien, nomor rekam medis, atau tanggal lahir. Hindari memasukkan PII ke kolom teks.

Skor retrieval/fusion adalah **relative evidence score**, bukan probabilitas klinis terkalibrasi. Temuan visual dari model vision generik harus diverifikasi dokter dan tidak boleh diperlakukan sebagai diagnosis final.

## Menjalankan Windows + Git Bash

```bash
cd ~/Downloads/diagnosa_mata_system
git pull origin main
bash start_windows_gitbash.sh
```

Launcher sekarang:
1. memastikan `.venv`;
2. memasang dependency;
3. melewati rebuild index jika file index sudah tersedia;
4. menjalankan Python `compileall` untuk mendeteksi syntax error;
5. menjalankan Uvicorn.