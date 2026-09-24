# CDSS Mata — Multimodal Vision + Clinical Retrieval

Versi ini menambahkan jalur multimodal: foto mata dianalisis oleh vision-language model (opsional, lokal), temuan visual diubah menjadi evidence terstruktur, lalu digabung dengan anamnesa/pemeriksaan dan retrieval histori.

## Vision provider lokal

Implementasi menggunakan endpoint kompatibel Ollama. Model default `qwen3-vl:4b` dipilih sebagai titik awal lokal yang lebih ringan; ukuran model resmi Ollama saat ini sekitar 3,3 GB untuk 4B. Model qwen3-vl juga tersedia dalam 2B, 8B, 30B, 32B, dan ukuran lebih besar. Model ini mendukung input teks + gambar. citeturn467190search0turn467190search6

Instal Ollama, lalu:

```bash
ollama pull qwen3-vl:4b
ollama run qwen3-vl:4b
```

Backend CDSS akan memanggil:

```text
http://127.0.0.1:11434/api/chat
```

Untuk Docker, `.env` menggunakan `host.docker.internal` agar container dapat mengakses Ollama di Windows host.

## Alur multimodal

1. Quality gate foto lokal.
2. Vision model menghasilkan `photo_type`, laterality, visible findings, red-flag visuals, limitations.
3. Clinical extractor mengambil parameter sederhana seperti VOD/VOS, TIO, CDR, laterality, dan tanda klinis dari teks.
4. Retrieval klinis mencari histori dari anamnesa + pemeriksaan.
5. Temuan visual dijadikan query retrieval terpisah.
6. Fusion engine menggabungkan dukungan klinis 70% + visual 30%.
7. UI menampilkan dukungan per sumber dan konsistensi, bukan probabilitas penyakit.

## Batasan

Model vision generik bukan model diagnosis oftalmologi tervalidasi. Karena itu prompt melarang diagnosis langsung dan sistem menampilkan temuan visual sebagai evidence pendukung. Validasi klinis, dataset foto berlabel dokter, external test set, calibration, dan prospective pilot tetap diperlukan sebelum penggunaan klinis.
