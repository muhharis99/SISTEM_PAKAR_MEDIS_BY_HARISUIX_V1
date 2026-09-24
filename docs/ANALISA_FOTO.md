# Analisa Foto Mata

Versi ini menambahkan endpoint `POST /api/analisa-gambar` dan UI upload foto JPG/JPEG, PNG, atau WEBP hingga 10 MB.

## Yang dianalisis

Analisa lokal menghitung metrik teknis/visual dasar:
- resolusi gambar;
- brightness/pencahayaan;
- contrast;
- indikator blur berbasis variasi Laplacian-like;
- rasio highlight/shadow;
- indikator dominansi rona merah/hangat.

## Yang TIDAK dilakukan

Baseline ini **tidak** menyatakan bahwa foto menunjukkan katarak, konjungtivitis, glaukoma, keratitis, retinopati, atau penyakit spesifik lain. Tidak ada probabilitas penyakit palsu yang dibuat dari ciri piksel umum.

Untuk klasifikasi penyakit dari foto, diperlukan model computer vision oftalmologi yang:
1. dilatih pada dataset gambar mata yang relevan;
2. memiliki ground truth oleh dokter;
3. diuji pada data eksternal/pasien baru;
4. mempunyai sensitivitas/spesifisitas dan kalibrasi yang diketahui;
5. divalidasi dalam workflow klinis setempat.

## Privasi

Gambar diproses in-memory pada endpoint dan tidak disimpan sebagai file permanen oleh baseline ini. Audit hanya mencatat hash SHA-256, tipe file, dan status kualitas.
