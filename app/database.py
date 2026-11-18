import os
from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.models import Cancion, Favorito, Usuario  # noqa: F401

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./musica.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def _migrar_columnas() -> None:
    """Agrega columnas nuevas a tablas existentes (create_all no altera tablas ya creadas)."""
    columnas = {c["name"] for c in inspect(engine).get_columns("usuarios")}
    if "password_hash" not in columnas:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN password_hash VARCHAR"))


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrar_columnas()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
