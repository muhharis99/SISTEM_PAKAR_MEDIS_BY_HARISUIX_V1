# Menjalankan di Windows 10 + Git Bash

Versi ini sengaja menyediakan launcher yang **tidak membutuhkan aktivasi** virtual environment.

```bash
cd ~/Downloads/diagnosa_mata_system
bash start_windows_gitbash.sh
```

Jadi tidak perlu memakai:

```bash
.venv\Scripts\activate
```

Untuk Git Bash, environment dapat dipakai langsung melalui `.venv/Scripts/python.exe`.

## Vision AI lokal (opsional)

Install Ollama pada Windows, lalu:

```bash
ollama pull qwen3-vl:4b
ollama run qwen3-vl:4b
```

Kemudian jalankan CDSS Mata. Backend otomatis mencoba `http://127.0.0.1:11434/api/chat`.

Untuk Docker Desktop Windows, compose diarahkan ke `host.docker.internal:11434`.

## Bila komputer lebih terbatas

Gunakan model vision yang lebih kecil:

```bash
ollama pull qwen3-vl:2b
```

Lalu ubah `.env`/environment:

```text
VISION_MODEL=qwen3-vl:2b
```

Ollama saat ini menyediakan qwen3-vl 2B, 4B, 8B, 30B, 32B, dan ukuran lebih besar; 4B sekitar 3,3 GB dan 8B sekitar 6,1 GB pada registry resmi. citeturn467190search0turn467190search6turn467190search3
