# Etika, Keamanan, dan Batasan Klinis

## Fungsi sistem
Sistem ini hanya membantu menemukan kasus historis yang mirip dan menyusun rekomendasi berdasarkan histori. Diagnosis final tetap ditetapkan oleh tenaga medis.

## PII dan anonimisasi
Kolom `nama`, `no_reg`, dan `tgl_lahir` tidak dimasukkan ke index retrieval. `no_reg` hanya dipakai secara internal saat preprocessing untuk membuat pseudonymous patient group dan tidak dikirim ke frontend.

## Keamanan
- Gunakan HTTPS/TLS pada deployment.
- Ganti akun demo dan `APP_SECRET` sebelum produksi.
- Batasi file `data/raw` dan database ke operator yang berwenang.
- Gunakan PostgreSQL dan secret manager pada produksi.
- Audit log menyimpan aksi dan metadata minimal; teks klinis mentah tidak disalin ke audit log.

## Validasi klinis
Metrik recall@K pada data historis tidak sama dengan validasi klinis prospektif. Sebelum dipakai sebagai CDSS nyata, lakukan review dataset, uji eksternal/holdout, penilaian dokter spesialis mata, pilot terbatas, dan proses incident reporting.
