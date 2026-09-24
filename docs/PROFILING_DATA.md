# Profiling Data — MATA_DIAGNOSA_2.csv

Sumber: dataset yang diberikan bersama project.

## Ringkasan
- Baris sumber: **107.020**
- Baris dengan teks klinis + diagnosis: **106.726**
- Kasus yang masuk index setelah preprocessing: **106.726**
- Pasien pseudonim unik: **31.965**
- Label diagnosis unik: **6.108**
- Fitur TF-IDF: **40.000**

## Kelengkapan kolom relevan
| Kolom | Kosong |
|---|---:|
| no_reg | 0,00% |
| nama | 0,00% |
| tgl_lahir | 0,00% |
| tgl_masuk | 0,00% |
| jam_masuk | 0,00% |
| alergi | 37,12% |
| anamnese | 0,00% |
| riwayat_sekarang | 34,15% |
| periksa | 0,36% |
| diagnosa | 0,27% |
| diagnosa_fungsional | 99,90% |
| tindakan | 23,38% |
| kontrol | 28,32% |
| tgl_kontrol | 58,09% |
| kd_dr | 0,00% |
| kd_poli | 0,00% |

## Panjang teks
### Anamnesa
P25 16 karakter · P50 26 · P75 45 · P90 91 · P95 118 · P99 196.

### Pemeriksaan
P25 70 karakter · P50 106 · P75 173 · P90 268 · P95 323 · P99 ≈442.

## Label terbanyak
1. H25.1 — SENILE NUCLEAR CATARACT: 23.883
2. H52.1 — MYOPIA: 9.338
3. Z96.1 — PRESENCE OF INTRAOCULAR LENS: 6.593
4. H40.1 — PRIMARY OPEN-ANGLE GLAUCOMA: 6.015
5. H20.9 — IRIDOCYCLITIS, UNSPECIFIED: 5.924
6. pseudofaki: 4.435
7. H16.9 — KERATITIS, UNSPECIFIED: 4.171
8. H25.2 — SENILE CATARACT, MORGAGNIAN TYPE: 3.546
9. H52.4 — PRESBYOPIA: 3.343
10. H36.0 — DIABETIC RETINOPATHY: 3.170

## Catatan pembersihan
- `diagnosa` dipisahkan berdasarkan token `@@,`/`@@`/baris baru.
- Kode ICD-10 diekstrak bila memenuhi pola kode.
- Diagnosis teks bebas tidak dipaksa menjadi ICD-10; dipertahankan sebagai `free_text`.
- `nama`, `no_reg`, `tgl_lahir` tidak dikirim ke retrieval/frontend.
- Umur dihitung saat kunjungan lalu diturunkan menjadi kelompok Neonatus/Anak/Dewasa/Geriatri.
- Data raw tetap berada di `data/raw` dan harus diproteksi di deployment nyata.
