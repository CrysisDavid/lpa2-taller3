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
    if "es_admin" not in columnas:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN es_admin BOOLEAN NOT NULL DEFAULT 0"))


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrar_columnas()
    # Importación diferida: app.admin usa app.auth, que a su vez importa este módulo.
    from app.admin import asegurar_admin

    with Session(engine) as session:
        asegurar_admin(session)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
