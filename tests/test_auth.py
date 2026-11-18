"""Pruebas de autenticación JWT: registro, login, /me y protección de rutas."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

import app.auth as auth
from app.database import get_session
from app.models import Usuario
from main import app
from musica_api.config import settings

REGISTRO = {"nombre": "Ana García", "correo": "Ana@Test.com", "password": "secreta123"}


@pytest.fixture(autouse=True)
def hash_rapido(monkeypatch):
    # Menos iteraciones solo para que las pruebas sean rápidas.
    monkeypatch.setattr(auth, "_ITERACIONES", 1_000)


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def override_get_session():
        yield session

    # Sin override de get_usuario_actual: aquí se prueba la autenticación real.
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="token")
def token_fixture(client: TestClient) -> str:
    r = client.post("/api/auth/registro", json=REGISTRO)
    assert r.status_code == 201
    return r.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Hash de contraseñas -----------------------------------------------------


def test_hash_y_verificacion():
    h = auth.hash_password("secreta123")
    assert h.startswith("pbkdf2_sha256$")
    assert "secreta123" not in h
    assert auth.verificar_password("secreta123", h)
    assert not auth.verificar_password("otra", h)


def test_hash_usa_sal_distinta():
    assert auth.hash_password("x" * 8) != auth.hash_password("x" * 8)


@pytest.mark.parametrize("hash_guardado", [None, "", "basura", "md5$1$a$b"])
def test_verificar_hash_invalido(hash_guardado):
    assert not auth.verificar_password("secreta123", hash_guardado)


# --- Registro ----------------------------------------------------------------


def test_registro_devuelve_token_y_usuario(client: TestClient, session: Session):
    r = client.post("/api/auth/registro", json=REGISTRO)
    assert r.status_code == 201
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["usuario"]["correo"] == "ana@test.com"  # normalizado
    assert "password" not in str(data)
    guardado = session.exec(select(Usuario)).one()
    assert guardado.password_hash.startswith("pbkdf2_sha256$")


def test_registro_correo_duplicado_400(client: TestClient, token):
    r = client.post("/api/auth/registro", json=REGISTRO)
    assert r.status_code == 400


@pytest.mark.parametrize(
    "cambios",
    [{"password": "corta"}, {"correo": "no-es-correo"}, {"nombre": "   "}, {"password": None}],
)
def test_registro_datos_invalidos_422(client: TestClient, cambios):
    r = client.post("/api/auth/registro", json={**REGISTRO, **cambios})
    assert r.status_code == 422


# --- Login -------------------------------------------------------------------


def test_login_correcto(client: TestClient, token):
    r = client.post("/api/auth/login", json={"correo": "ana@test.com", "password": "secreta123"})
    assert r.status_code == 200
    assert r.json()["usuario"]["nombre"] == "Ana García"


def test_login_ignora_mayusculas_del_correo(client: TestClient, token):
    r = client.post("/api/auth/login", json={"correo": " ANA@test.COM ", "password": "secreta123"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "credenciales",
    [
        {"correo": "ana@test.com", "password": "incorrecta"},
        {"correo": "nadie@test.com", "password": "secreta123"},
    ],
)
def test_login_incorrecto_401(client: TestClient, token, credenciales):
    r = client.post("/api/auth/login", json=credenciales)
    assert r.status_code == 401
    assert r.json()["detail"] == "Correo o contraseña incorrectos"


def test_usuario_sin_password_no_puede_iniciar_sesion(client: TestClient, session: Session):
    session.add(Usuario(nombre="Viejo", correo="viejo@test.com"))
    session.commit()
    r = client.post("/api/auth/login", json={"correo": "viejo@test.com", "password": "loquesea1"})
    assert r.status_code == 401


# --- /me y protección de rutas ----------------------------------------------


def test_me_con_token(client: TestClient, token):
    r = client.get("/api/auth/me", headers=auth_header(token))
    assert r.status_code == 200
    assert set(r.json()) == {"id", "nombre", "correo", "fecha_registro"}


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", "/api/auth/me"),
        ("get", "/api/canciones"),
        ("get", "/api/canciones/buscar"),
        ("post", "/api/canciones"),
        ("get", "/api/usuarios"),
        ("delete", "/api/usuarios/1"),
        ("get", "/api/favoritos"),
        ("post", "/api/usuarios/1/favoritos/1"),
    ],
)
def test_rutas_protegidas_sin_token_401(client: TestClient, metodo, ruta):
    r = getattr(client, metodo)(ruta)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_rutas_publicas_sin_token(client: TestClient):
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200


def test_ruta_protegida_con_token(client: TestClient, token):
    r = client.get("/api/usuarios", headers=auth_header(token))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_respuestas_no_exponen_password_hash(client: TestClient, token):
    usuarios = client.get("/api/usuarios", headers=auth_header(token)).json()
    assert all("password_hash" not in u for u in usuarios)
    uno = client.get(f"/api/usuarios/{usuarios[0]['id']}", headers=auth_header(token)).json()
    assert "password_hash" not in uno


def test_crud_no_permite_fijar_password_hash(client: TestClient, session: Session, token):
    r = client.post(
        "/api/usuarios",
        headers=auth_header(token),
        json={"nombre": "Intruso", "correo": "intruso@test.com", "password_hash": "pbkdf2_sha256$1$a$b"},
    )
    assert r.status_code == 201
    assert session.get(Usuario, r.json()["id"]).password_hash is None


def test_token_invalido_401(client: TestClient):
    r = client.get("/api/canciones", headers=auth_header("no.es.un.jwt"))
    assert r.status_code == 401
    assert r.json()["detail"] == "Token inválido"


def test_token_firmado_con_otra_clave_401(client: TestClient, token):
    falso = jwt.encode({"sub": "1"}, "otra-clave-distinta-de-al-menos-32-bytes", algorithm="HS256")
    assert client.get("/api/canciones", headers=auth_header(falso)).status_code == 401


def test_token_expirado_401(client: TestClient, token):
    pasado = datetime.now(timezone.utc) - timedelta(minutes=5)
    expirado = jwt.encode({"sub": "1", "exp": pasado}, settings.secret_key, algorithm=settings.algorithm)
    r = client.get("/api/canciones", headers=auth_header(expirado))
    assert r.status_code == 401
    assert "expiró" in r.json()["detail"]


def test_token_de_usuario_eliminado_401(client: TestClient, token):
    me = client.get("/api/auth/me", headers=auth_header(token)).json()
    assert client.delete(f"/api/usuarios/{me['id']}", headers=auth_header(token)).status_code == 204
    assert client.get("/api/canciones", headers=auth_header(token)).status_code == 401
