"""Fixtures compartidas por las pruebas de la API."""

import atexit
import os
import shutil
import tempfile

# Antes de importar la app: el arranque (lifespan) crea tablas y la cuenta de admin
# en DATABASE_URL. Con una base temporal, las pruebas nunca tocan musica.db.
_tmp = tempfile.mkdtemp(prefix="musica-tests-")
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi import HTTPException, status  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402
from sqlmodel.pool import StaticPool  # noqa: E402

import app.auth as auth  # noqa: E402
from app.auth import get_usuario_actual  # noqa: E402
from app.database import get_session  # noqa: E402
from app.models import Usuario  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def hash_rapido(monkeypatch):
    # Menos iteraciones de PBKDF2 solo para que las pruebas sean rápidas.
    monkeypatch.setattr(auth, "_ITERACIONES", 1_000)


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="estado_auth")
def estado_auth_fixture() -> dict:
    """id del usuario autenticado en la prueba (None = usuario genérico sin registro)."""
    return {"id": None}


@pytest.fixture(name="como")
def como_fixture(estado_auth: dict):
    """``como(usuario)`` hace que las siguientes peticiones se autentiquen como ese usuario.

    Acepta un dict de la API, un ``Usuario`` o un id. La autenticación JWT real
    (tokens, expiración, 401) se prueba en test_auth.py.
    """

    def cambiar(usuario):
        if isinstance(usuario, dict):
            usuario = usuario["id"]
        elif isinstance(usuario, Usuario):
            usuario = usuario.id
        estado_auth["id"] = usuario

    return cambiar


@pytest.fixture(name="client")
def client_fixture(session: Session, estado_auth: dict):
    def override_get_session():
        yield session

    def override_usuario_actual():
        if estado_auth["id"] is None:
            # Usuario genérico para pruebas que no dependen de un usuario concreto (p. ej. canciones).
            return Usuario(id=0, nombre="Tester", correo="tester@test.com")
        usuario = session.get(Usuario, estado_auth["id"])
        if usuario is None:  # igual que un token de un usuario eliminado
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        return usuario

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_usuario_actual] = override_usuario_actual
    # raise_server_exceptions=False: un error 500 se devuelve como respuesta
    # en lugar de propagarse, para poder afirmar sobre el código de estado.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def registrar(client: TestClient, nombre: str, correo: str, password: str = "secreta123") -> dict:
    """Registra un usuario por la API y devuelve sus datos públicos."""
    r = client.post("/api/auth/registro", json={"nombre": nombre, "correo": correo, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["usuario"]
