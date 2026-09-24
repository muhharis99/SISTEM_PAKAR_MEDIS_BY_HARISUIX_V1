# Update V2.1 - Perbaikan Error Analisa Multimodal

Perbaikan utama:
- API frontend sekarang menampilkan HTTP status + detail server jika respons gagal.
- Penanganan network error diperjelas.
- Render hasil foto lebih defensif terhadap bentuk response.
- Render clinical/fusion dibuat aman ketika field numerik kosong/null/string.
- Error pada tombol Analisa Multimodal sekarang ditampilkan detailnya dan dicetak ke Console.

Endpoint backend multimodal sudah diuji secara langsung dan mengembalikan HTTP 200 pada environment build.
