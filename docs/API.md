# API Ringkas

Semua endpoint selain login/health membutuhkan session cookie.

## Login
`POST /api/auth/login`
```json
{"username":"dokter","password":"dokter123"}
```

## Analisa
`POST /api/analisa`
```json
{
  "age": 55,
  "sex": "Laki-laki",
  "alergi": "DM",
  "anamnese": "mata kiri merah dan kabur",
  "riwayat_sekarang": "",
  "periksa": "VOS 6/60 kornea infiltrat",
  "top_n": 5
}
```
Response berisi `results` dengan label, kode, skor kemiripan heuristik, jumlah kasus pendukung, dan contoh kasus anonim.

## Statistik
`GET /api/statistik`

## Kasus mirip
`GET /api/kasus-mirip?q=mata%20merah&limit=20`

## Riwayat
`GET /api/riwayat?diagnosis=H16.9&age_group=Dewasa&year=2020&q=merah`

## Kamus
`GET /api/kamus`

## Feedback dokter
`POST /api/feedback`
Role: `dokter` atau `admin`.

## Audit
`GET /api/audit`
Role: `admin`.

## Upload Foto Mata

### `POST /api/analisa-gambar`

Multipart form-data:

- `image`: JPG/JPEG, PNG, atau WEBP, maksimum 10 MB.

Response berisi resolusi, brightness, contrast, blur score, rasio highlight/shadow, observasi visual dasar, peringatan kualitas, dan disclaimer. Endpoint ini **tidak** menghasilkan diagnosis penyakit dari foto.
