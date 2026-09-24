from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data/app.db'}")
if DB_URL.startswith("sqlite"):
    Path(ROOT / "data").mkdir(exist_ok=True)
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(30), default="perawat")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class CaseRecord(Base):
    __tablename__ = "case_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(30), default="multimodal")
    title: Mapped[str] = mapped_column(String(180), default="Kasus Baru")
    status: Mapped[str] = mapped_column(String(30), default="review")
    image_sha256: Mapped[str] = mapped_column(String(64), default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    recommended: Mapped[str] = mapped_column(Text, default="")
    corrected_diagnosis: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000).hex()
        return secrets.compare_digest(expected, key_hex)
    except Exception:
        return False


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if not s.scalar(select(User).where(User.username == "admin")):
            s.add_all([
                User(username="admin", password_hash=hash_password("admin123"), role="admin"),
                User(username="dokter", password_hash=hash_password("dokter123"), role="dokter"),
                User(username="perawat", password_hash=hash_password("perawat123"), role="perawat"),
            ])
            s.commit()
