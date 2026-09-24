-- Skema konseptual; implementasi runtime menggunakan SQLAlchemy.
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(80) UNIQUE NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  role VARCHAR(30) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NULL,
  action VARCHAR(80) NOT NULL,
  detail TEXT NOT NULL DEFAULT '{}',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE feedback (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NULL,
  input_summary TEXT NOT NULL DEFAULT '{}',
  recommended TEXT NOT NULL DEFAULT '[]',
  corrected_diagnosis TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Kasus klinis teranonim disimpan pada artefak indeks file untuk baseline TF-IDF.
-- Jika PostgreSQL + pgvector dipakai saat upgrade semantic-search, tabel berikut dapat ditambahkan:
-- clinical_cases(id, patient_group_hash, visit_year, age_group, anamnese, periksa, embedding vector(...)).
