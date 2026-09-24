# Arsitektur

```text
CSV rekam medis
      |
      v
preprocess.py ----> cases.jsonl (pseudonim + umur_group + teks klinis)
      |
      v
TF-IDF word 1-2 gram
      |
      v
sparse matrix.npz + metadata.json + tfidf.joblib
      |
      v
FastAPI ---- REST ---- Frontend HTML/JS
      |
      +---- SQLite/PostgreSQL (users, audit, feedback)
```

## Kenapa TF-IDF dulu?
- mudah diaudit karena fitur token dapat ditelusuri,
- tidak memerlukan GPU/model transformer,
- cocok sebagai baseline dan cepat untuk 100 ribuan kasus,
- biaya operasional rendah.

## Jalur upgrade
Ganti modul `ml/retrieval.py` dengan sentence embedding (mis. multilingual-e5/IndoBERT) dan vector store (pgvector/FAISS). Evaluasi ulang recall@3, recall@5, precision@K dan performa per subkelompok klinis.
