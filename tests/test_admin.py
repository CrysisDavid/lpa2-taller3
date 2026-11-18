"""Pruebas del rol de administrador."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.admin import asegurar_admin
from app.auth import hash_password, verificar_password
from app.database import get_session
from app.models import Favorito, Usuario
from main import app
from musica_api.config import settings
from tests.conftest import registrar

CANCION = {"titulo": "Imagine", "artista": "John Lennon", "album": "Imagine", "duracion": 183, "anio": 1971, "genero": "Pop"}


@pytest.fixture(name="admin")
def admin_fixture(session: Session, como) -> Usuario:
    admin = asegurar_admin(session)
    como(admin)
    return admin


@pytest.fixture(name="ana")
def ana_fixture(client: TestClient) -> dict:
    return registrar(client, "Ana", "ana@test.com")


@pytest.fixture(name="luis")
def luis_fixture(client: TestClient) -> dict:
    return registrar(client, "Luis", "luis@test.com")


@pytest.fixture(name="cancion")
def cancion_fixture(client: TestClient) -> dict:
    return client.post("/api/canciones", json=CANCION).json()


# --- Creación de la cuenta ---------------------------------------------------


def test_asegurar_admin_crea_la_cuenta(session: Session):
    admin = asegurar_admin(session)
    assert admin.nombre == "admin"
    assert admin.correo == "admin@musica.com"
    assert admin.es_admin
    assert verificar_password("admin@2026.musica", admin.password_hash)


def test_asegurar_admin_es_idempotente(session: Session):
    primero = asegurar_admin(session)
    segundo = asegurar_admin(session)
    assert primero.id == segundo.id
    assert len(session.exec(select(Usuario)).all()) == 1


def test_asegurar_admin_no_cambia_una_password_existente(session: Session):
    admin = asegurar_admin(session)
    admin.password_hash = hash_password("otra-clave-123")
    session.add(admin)
    session.commit()
    asegurar_admin(session)
    assert verificar_password("otra-clave-123", session.get(Usuario, admin.id).password_hash)


def test_asegurar_admin_promueve_usuario_existente_sin_password(session: Session):
    session.add(Usuario(nombre="Admin manual", correo="Admin@Musica.com"))
    session.commit()
    admin = asegurar_admin(session)
    assert admin.es_admin
    assert verificar_password("admin@2026.musica", admin.password_hash)
    assert len(session.exec(select(Usuario)).all()) == 1


def test_la_api_crea_el_admin_al_arrancar_y_permite_login(session: Session):
    # Autenticación real (sin override): login con las credenciales por defecto.
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as client:
            asegurar_admin(session)  # el arranque lo hace sobre la base configurada
            r = client.post(
                "/api/auth/login",
                json={"correo": settings.admin_correo, "password": settings.admin_password},
            )
            assert r.status_code == 200
            assert r.json()["usuario"]["es_admin"] is True
            token = r.json()["access_token"]
            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.json()["nombre"] == "admin"
    finally:
        app.dependency_overrides.clear()


# --- Nadie más puede volverse admin -----------------------------------------


def test_registro_no_acepta_es_admin(client: TestClient, session: Session):
    r = client.post(
        "/api/auth/registro",
        json={"nombre": "Pillo", "correo": "pillo@test.com", "password": "secreta123", "es_admin": True},
    )
    assert r.status_code == 201
    assert r.json()["usuario"]["es_admin"] is False
    assert not session.get(Usuario, r.json()["usuario"]["id"]).es_admin


def test_put_no_cambia_es_admin(client: TestClient, session: Session, ana, como):
    como(ana)
    r = client.put(f"/api/usuarios/{ana['id']}", json={"es_admin": True})
    assert r.status_code == 200
    assert r.json()["es_admin"] is False
    assert not session.get(Usuario, ana["id"]).es_admin


def test_admin_no_puede_quitarse_el_rol(client: TestClient, session: Session, admin):
    client.put(f"/api/usuarios/{admin.id}", json={"es_admin": False})
    assert session.get(Usuario, admin.id).es_admin


def test_usuario_normal_no_ve_a_los_demas(client: TestClient, admin, ana, como):
    como(ana)
    assert [u["correo"] for u in client.get("/api/usuarios").json()] == ["ana@test.com"]
    assert client.get(f"/api/usuarios/{admin.id}").status_code == 403


# --- Lo que puede hacer el admin --------------------------------------------


def test_admin_lista_todos_los_usuarios(client: TestClient, admin, ana, luis):
    data = client.get("/api/usuarios").json()
    assert [u["correo"] for u in data] == ["admin@musica.com", "ana@test.com", "luis@test.com"]
    assert [u["es_admin"] for u in data] == [True, False, False]


def test_admin_ve_y_edita_a_otro_usuario(client: TestClient, admin, ana):
    assert client.get(f"/api/usuarios/{ana['id']}").json()["correo"] == "ana@test.com"
    r = client.put(f"/api/usuarios/{ana['id']}", json={"nombre": "Ana Editada"})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Ana Editada"


def test_admin_elimina_a_otro_usuario_y_sus_favoritos(
    client: TestClient, session: Session, admin, ana, luis, cancion, como
):
    como(ana)
    client.post(f"/api/usuarios/{ana['id']}/favoritos/{cancion['id']}")
    como(luis)
    client.post(f"/api/usuarios/{luis['id']}/favoritos/{cancion['id']}")
    como(admin)
    assert client.delete(f"/api/usuarios/{ana['id']}").status_code == 204
    assert session.get(Usuario, ana["id"]) is None
    assert [f.id_usuario for f in session.exec(select(Favorito)).all()] == [luis["id"]]


def test_admin_eliminar_inexistente_404(client: TestClient, admin):
    assert client.delete("/api/usuarios/999").status_code == 404


def test_la_cuenta_admin_no_se_puede_eliminar(client: TestClient, session: Session, admin):
    r = client.delete(f"/api/usuarios/{admin.id}")
    assert r.status_code == 400
    assert r.json()["detail"] == "La cuenta de administrador no se puede eliminar"
    assert session.get(Usuario, admin.id) is not None


def test_admin_ve_los_favoritos_de_otro(client: TestClient, admin, ana, cancion, como):
    como(ana)
    creado = client.post(f"/api/usuarios/{ana['id']}/favoritos/{cancion['id']}").json()
    como(admin)
    favs = client.get(f"/api/usuarios/{ana['id']}/favoritos").json()
    assert [f["id_cancion"] for f in favs] == [cancion["id"]]
    assert client.get(f"/api/favoritos/{creado['id']}").status_code == 200
    assert len(client.get("/api/favoritos").json()) == 1  # ve los de todos


def test_admin_gestiona_favoritos_de_otro(client: TestClient, session: Session, admin, ana, cancion):
    r = client.post(f"/api/usuarios/{ana['id']}/favoritos/{cancion['id']}")
    assert r.status_code == 201
    assert client.delete(f"/api/favoritos/{r.json()['id']}").status_code == 204
    r = client.post("/api/favoritos", json={"id_usuario": ana["id"], "id_cancion": cancion["id"]})
    assert r.status_code == 201
    assert client.delete(f"/api/usuarios/{ana['id']}/favoritos/{cancion['id']}").status_code == 204
    assert session.exec(select(Favorito)).all() == []


def test_admin_favorito_para_usuario_inexistente_404(client: TestClient, admin, cancion):
    r = client.post("/api/favoritos", json={"id_usuario": 999, "id_cancion": cancion["id"]})
    assert r.status_code == 404
    assert client.post(f"/api/usuarios/999/favoritos/{cancion['id']}").status_code == 404


def test_admin_tampoco_crea_usuarios_por_crud(client: TestClient, admin):
    r = client.post("/api/usuarios", json={"nombre": "X", "correo": "x@test.com"})
    assert r.status_code == 403
