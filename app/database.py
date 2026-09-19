import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./gestor_planos.db")

# Algunos proveedores (Neon, Render, Heroku) entregan "postgres://"; SQLAlchemy 2.x + psycopg3 requieren "postgresql+psycopg://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Neon/pgbouncer usan pooling en modo "transaction": no soportan prepared statements de sesión.
    connect_args = {"prepare_threshold": None}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
