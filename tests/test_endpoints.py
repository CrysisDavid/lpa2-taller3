"""Pruebas detalladas de todos los endpoints de la API de Música.

Cada endpoint se prueba en su camino feliz, en sus errores esperados
(404, 400, 422) y en casos límite. Los tests marcados con ``xfail(strict=True)``
documentan bugs conocidos: fallan hoy y, cuando el bug se corrija, pasarán
a XPASS y pytest avisará para quitar la marca.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.auth import get_usuario_actual
from app.database import get_session
from app.models import Cancion, Favorito, Usuario
from main import app

ANIO_ACTUAL = datetime.now(timezone.utc).year


def override_usuario_actual():
    """Simula un usuario autenticado: la autenticación se prueba en test_auth.py."""
    return Usuario(id=0, nombre="Tester", correo="tester@test.com")


# =============================================================================
# FIXTURES
# =============================================================================


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


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_usuario_actual] = override_usuario_actual
    # raise_server_exceptions=False: un error 500 se devuelve como respuesta
    # en lugar de propagarse, para poder afirmar sobre el código de estado.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def cancion_payload(**overrides):
    payload = {
        "titulo": "Bohemian Rhapsody",
        "artista": "Queen",
        "album": "A Night at the Opera",
        "duracion": 354,
        "anio": 1975,
        "genero": "Rock",
    }
    payload.update(overrides)
    return payload


@pytest.fixture(name="usuario")
def usuario_fixture(client: TestClient):
    r = client.post("/api/usuarios", json={"nombre": "Ana García", "correo": "ana@test.com"})
    assert r.status_code == 201
    return r.json()


@pytest.fixture(name="otro_usuario")
def otro_usuario_fixture(client: TestClient):
    r = client.post("/api/usuarios", json={"nombre": "Luis Pérez", "correo": "luis@test.com"})
    assert r.status_code == 201
    return r.json()


@pytest.fixture(name="cancion")
def cancion_fixture(client: TestClient):
    r = client.post("/api/canciones", json=cancion_payload())
    assert r.status_code == 201
    return r.json()


@pytest.fixture(name="catalogo")
def catalogo_fixture(client: TestClient):
    canciones = [
        cancion_payload(),
        cancion_payload(titulo="Imagine", artista="John Lennon", album="Imagine", anio=1971, genero="Pop"),
        cancion_payload(titulo="Hotel California", artista="Eagles", album="Hotel California", anio=1976, genero="Rock"),
        cancion_payload(titulo="Billie Jean", artista="Michael Jackson", album="Thriller", anio=1982, genero="Pop"),
    ]
    return [client.post("/api/canciones", json=c).json() for c in canciones]


# =============================================================================
# ROOT Y HEALTH
# =============================================================================


class TestRootYHealth:
    def test_root_devuelve_metadatos(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["app"] == "API de Música"
        assert data["version"] == "1.0.0"
        assert data["documentacion"] == "/docs"
        assert data["usuarios"] == "/api/usuarios"
        assert data["canciones"] == "/api/canciones"
        assert data["favoritos"] == "/api/favoritos"

    def test_health(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["database"] == "ok"
        assert "environment" in data

    def test_docs_disponibles(self, client: TestClient):
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200

    def test_openapi_expone_todos_los_endpoints(self, client: TestClient):
        paths = client.get("/openapi.json").json()["paths"]
        esperado = {
            "/": {"get"},
            "/health": {"get"},
            "/api/usuarios": {"get", "post"},
            "/api/usuarios/{usuario_id}": {"get", "put", "delete"},
            "/api/usuarios/{usuario_id}/favoritos": {"get"},
            "/api/usuarios/{usuario_id}/favoritos/{cancion_id}": {"post", "delete"},
            "/api/canciones": {"get", "post"},
            "/api/canciones/buscar": {"get"},
            "/api/canciones/{cancion_id}": {"get", "put", "delete"},
            "/api/favoritos": {"get", "post"},
            "/api/favoritos/{favorito_id}": {"get", "delete"},
        }
        for path, metodos in esperado.items():
            assert path in paths, path
            assert set(paths[path]) == metodos, path

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: app/routers/peliculas.py reexporta el router de canciones y main.py lo "
        "registra dos veces, generando operation IDs duplicados en OpenAPI",
    )
    def test_router_peliculas_no_duplica_canciones(self):
        from app.routers import canciones_router, peliculas_router

        assert peliculas_router is not canciones_router

    def test_cors_permite_origen(self, client: TestClient):
        r = client.options(
            "/api/usuarios",
            headers={"Origin": "http://ejemplo.com", "Access-Control-Request-Method": "GET"},
        )
        assert r.status_code == 200
        assert "access-control-allow-origin" in r.headers

    def test_ruta_inexistente_404(self, client: TestClient):
        assert client.get("/api/no-existe").status_code == 404

    def test_metodo_no_permitido_405(self, client: TestClient):
        assert client.patch("/api/usuarios").status_code == 405


# =============================================================================
# USUARIOS
# =============================================================================


class TestListarUsuarios:
    def test_lista_vacia(self, client: TestClient):
        r = client.get("/api/usuarios")
        assert r.status_code == 200
        assert r.json() == []

    def test_lista_con_usuarios(self, client: TestClient, usuario, otro_usuario):
        data = client.get("/api/usuarios").json()
        assert len(data) == 2
        assert {u["correo"] for u in data} == {"ana@test.com", "luis@test.com"}

    def test_estructura_de_cada_usuario(self, client: TestClient, usuario):
        item = client.get("/api/usuarios").json()[0]
        assert set(item) == {"id", "nombre", "correo", "fecha_registro"}


class TestCrearUsuario:
    def test_crear_usuario(self, client: TestClient):
        r = client.post("/api/usuarios", json={"nombre": "Carlos", "correo": "carlos@test.com"})
        assert r.status_code == 201
        data = r.json()
        assert isinstance(data["id"], int)
        assert data["nombre"] == "Carlos"
        assert data["correo"] == "carlos@test.com"
        # fecha_registro se genera automáticamente y es ISO 8601
        datetime.fromisoformat(data["fecha_registro"].replace("Z", "+00:00"))

    def test_crear_usuario_persiste(self, client: TestClient, session: Session):
        r = client.post("/api/usuarios", json={"nombre": "Carlos", "correo": "carlos@test.com"})
        en_db = session.get(Usuario, r.json()["id"])
        assert en_db is not None
        assert en_db.correo == "carlos@test.com"

    def test_ids_autoincrementales(self, client: TestClient):
        a = client.post("/api/usuarios", json={"nombre": "A", "correo": "a@test.com"}).json()
        b = client.post("/api/usuarios", json={"nombre": "B", "correo": "b@test.com"}).json()
        assert b["id"] > a["id"]

    def test_id_enviado_se_ignora(self, client: TestClient):
        r = client.post("/api/usuarios", json={"id": 999, "nombre": "X", "correo": "x@test.com"})
        assert r.status_code == 201
        assert r.json()["id"] != 999

    @pytest.mark.parametrize("fecha", ["2024-01-15T10:30:00Z", "2024-01-15T10:30:00+00:00", "2024-01-15T10:30:00"])
    def test_crear_con_fecha_iso(self, client: TestClient, fecha):
        r = client.post("/api/usuarios", json={"nombre": "F", "correo": "f@test.com", "fecha_registro": fecha})
        assert r.status_code == 201
        assert r.json()["fecha_registro"].startswith("2024-01-15T10:30:00")

    def test_fecha_invalida_422(self, client: TestClient):
        r = client.post("/api/usuarios", json={"nombre": "F", "correo": "f@test.com", "fecha_registro": "ayer"})
        assert r.status_code == 422

    def test_correo_duplicado_400(self, client: TestClient, usuario):
        r = client.post("/api/usuarios", json={"nombre": "Otra Ana", "correo": usuario["correo"]})
        assert r.status_code == 400
        assert r.json()["detail"] == "Ya existe un usuario con ese correo"

    @pytest.mark.parametrize(
        "correo",
        ["sin-arroba", "a@b", "@test.com", "a@.com", "a b@test.com", "a@test.c", ""],
    )
    def test_correo_invalido_422(self, client: TestClient, correo):
        r = client.post("/api/usuarios", json={"nombre": "X", "correo": correo})
        assert r.status_code == 422

    @pytest.mark.parametrize("correo", ["a.b@test.com", "a+tag@sub.test.co", "A_B-1%x@dominio.org"])
    def test_correo_valido_variantes(self, client: TestClient, correo):
        r = client.post("/api/usuarios", json={"nombre": "X", "correo": correo})
        assert r.status_code == 201

    @pytest.mark.parametrize("nombre", ["", "   "])
    def test_nombre_vacio_422(self, client: TestClient, nombre):
        r = client.post("/api/usuarios", json={"nombre": nombre, "correo": "x@test.com"})
        assert r.status_code == 422

    def test_nombre_con_acentos_y_unicode(self, client: TestClient):
        r = client.post("/api/usuarios", json={"nombre": "José Ñúñez 🎵", "correo": "jose@test.com"})
        assert r.status_code == 201
        assert r.json()["nombre"] == "José Ñúñez 🎵"

    def test_body_no_json_422(self, client: TestClient):
        r = client.post("/api/usuarios", content="no es json", headers={"Content-Type": "application/json"})
        assert r.status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: tipos no validados en modelos table=True; una lista como nombre provoca 500")
    def test_tipo_incorrecto_422(self, client: TestClient):
        r = client.post("/api/usuarios", json={"nombre": ["lista"], "correo": "x@test.com"})
        assert r.status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: Usuario es un modelo table=True; los campos requeridos no se validan "
        "y sin correo se responde 400 'Ya existe un usuario con ese correo'",
    )
    def test_falta_correo_422(self, client: TestClient):
        r = client.post("/api/usuarios", json={"nombre": "Sin correo"})
        assert r.status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: campos requeridos no validados en modelos table=True")
    def test_falta_nombre_422(self, client: TestClient):
        r = client.post("/api/usuarios", json={"correo": "x@test.com"})
        assert r.status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: campos requeridos no validados en modelos table=True")
    def test_body_vacio_422(self, client: TestClient):
        r = client.post("/api/usuarios", json={})
        assert r.status_code == 422


class TestObtenerUsuario:
    def test_obtener(self, client: TestClient, usuario):
        r = client.get(f"/api/usuarios/{usuario['id']}")
        assert r.status_code == 200
        assert r.json() == usuario

    def test_no_existe_404(self, client: TestClient):
        r = client.get("/api/usuarios/999")
        assert r.status_code == 404
        assert r.json()["detail"] == "Usuario no encontrado"

    @pytest.mark.parametrize("usuario_id", ["abc", "1.5"])
    def test_id_no_entero_422(self, client: TestClient, usuario_id):
        assert client.get(f"/api/usuarios/{usuario_id}").status_code == 422

    @pytest.mark.parametrize("usuario_id", [0, -1])
    def test_id_no_positivo_404(self, client: TestClient, usuario_id):
        assert client.get(f"/api/usuarios/{usuario_id}").status_code == 404


class TestActualizarUsuario:
    def test_actualizar_completo(self, client: TestClient, usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"nombre": "Ana Nueva", "correo": "nueva@test.com"})
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == usuario["id"]
        assert data["nombre"] == "Ana Nueva"
        assert data["correo"] == "nueva@test.com"
        # el cambio se ve en GET
        assert client.get(f"/api/usuarios/{usuario['id']}").json()["correo"] == "nueva@test.com"

    def test_actualizacion_parcial_conserva_otros_campos(self, client: TestClient, usuario):
        # PUT se comporta como PATCH: solo cambia los campos enviados
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"nombre": "Solo Nombre"})
        assert r.status_code == 200
        assert r.json()["nombre"] == "Solo Nombre"
        assert r.json()["correo"] == usuario["correo"]

    def test_id_en_body_no_cambia_id(self, client: TestClient, usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"id": 500, "nombre": "Ana"})
        assert r.status_code == 200
        assert r.json()["id"] == usuario["id"]

    def test_mismo_correo_propio_permitido(self, client: TestClient, usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"nombre": "Ana", "correo": usuario["correo"]})
        assert r.status_code == 200

    def test_correo_de_otro_usuario_400(self, client: TestClient, usuario, otro_usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"correo": otro_usuario["correo"]})
        assert r.status_code == 400
        # el usuario original no cambió
        assert client.get(f"/api/usuarios/{usuario['id']}").json()["correo"] == usuario["correo"]

    def test_correo_invalido_422(self, client: TestClient, usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"correo": "invalido"})
        assert r.status_code == 422

    def test_nombre_vacio_422(self, client: TestClient, usuario):
        r = client.put(f"/api/usuarios/{usuario['id']}", json={"nombre": "  "})
        assert r.status_code == 422

    def test_no_existe_404(self, client: TestClient):
        r = client.put("/api/usuarios/999", json={"nombre": "X", "correo": "x@test.com"})
        assert r.status_code == 404


class TestEliminarUsuario:
    def test_eliminar(self, client: TestClient, usuario):
        r = client.delete(f"/api/usuarios/{usuario['id']}")
        assert r.status_code == 204
        assert r.content == b""
        assert client.get(f"/api/usuarios/{usuario['id']}").status_code == 404

    def test_eliminar_dos_veces_404(self, client: TestClient, usuario):
        client.delete(f"/api/usuarios/{usuario['id']}")
        assert client.delete(f"/api/usuarios/{usuario['id']}").status_code == 404

    def test_no_existe_404(self, client: TestClient):
        assert client.delete("/api/usuarios/999").status_code == 404

    def test_no_afecta_a_otros(self, client: TestClient, usuario, otro_usuario):
        client.delete(f"/api/usuarios/{usuario['id']}")
        assert client.get(f"/api/usuarios/{otro_usuario['id']}").status_code == 200

    def test_correo_reutilizable_tras_eliminar(self, client: TestClient, usuario):
        client.delete(f"/api/usuarios/{usuario['id']}")
        r = client.post("/api/usuarios", json={"nombre": "Ana otra vez", "correo": usuario["correo"]})
        assert r.status_code == 201

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: al borrar un usuario con favoritos, SQLAlchemy pone id_usuario=NULL en "
        "sus favoritos, viola NOT NULL y la API responde 500",
    )
    def test_eliminar_usuario_con_favoritos(self, client: TestClient, usuario, cancion):
        client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        r = client.delete(f"/api/usuarios/{usuario['id']}")
        assert r.status_code in (204, 400, 409)


# =============================================================================
# CANCIONES
# =============================================================================


class TestListarCanciones:
    def test_lista_vacia(self, client: TestClient):
        r = client.get("/api/canciones")
        assert r.status_code == 200
        assert r.json() == []

    def test_lista_con_canciones(self, client: TestClient, catalogo):
        data = client.get("/api/canciones").json()
        assert len(data) == len(catalogo)

    def test_estructura(self, client: TestClient, cancion):
        item = client.get("/api/canciones").json()[0]
        assert set(item) == {"id", "titulo", "artista", "album", "duracion", "anio", "genero", "fecha_creacion"}


class TestCrearCancion:
    def test_crear(self, client: TestClient):
        payload = cancion_payload()
        r = client.post("/api/canciones", json=payload)
        assert r.status_code == 201
        data = r.json()
        for campo, valor in payload.items():
            assert data[campo] == valor
        assert isinstance(data["id"], int)
        assert "fecha_creacion" in data

    def test_fecha_creacion_la_pone_el_servidor(self, client: TestClient):
        r = client.post("/api/canciones", json=cancion_payload(fecha_creacion="2000-01-01T00:00:00Z"))
        assert r.status_code == 201
        assert not r.json()["fecha_creacion"].startswith("2000-01-01")

    def test_id_enviado_se_ignora(self, client: TestClient):
        r = client.post("/api/canciones", json=cancion_payload(id=777))
        assert r.status_code == 201
        assert r.json()["id"] != 777

    def test_anio_actual_permitido(self, client: TestClient):
        assert client.post("/api/canciones", json=cancion_payload(anio=ANIO_ACTUAL)).status_code == 201

    def test_anio_1900_permitido(self, client: TestClient):
        assert client.post("/api/canciones", json=cancion_payload(anio=1900)).status_code == 201

    def test_anio_futuro_422(self, client: TestClient):
        r = client.post("/api/canciones", json=cancion_payload(anio=ANIO_ACTUAL + 1))
        assert r.status_code == 422

    @pytest.mark.parametrize("campo", ["titulo", "artista", "album", "genero"])
    @pytest.mark.parametrize("valor", ["", "   "])
    def test_texto_vacio_422(self, client: TestClient, campo, valor):
        r = client.post("/api/canciones", json=cancion_payload(**{campo: valor}))
        assert r.status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: tipos no validados; duracion='largo' se guarda y responde 201")
    def test_duracion_texto_422(self, client: TestClient):
        assert client.post("/api/canciones", json=cancion_payload(duracion="largo")).status_code == 422

    def test_duplicados_permitidos(self, client: TestClient):
        # No hay restricción de unicidad en canciones
        assert client.post("/api/canciones", json=cancion_payload()).status_code == 201
        assert client.post("/api/canciones", json=cancion_payload()).status_code == 201

    @pytest.mark.xfail(strict=True, reason="BUG: Field(ge=1900) no se aplica en modelos table=True")
    def test_anio_menor_1900_422(self, client: TestClient):
        assert client.post("/api/canciones", json=cancion_payload(anio=1899)).status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: Field(ge=1) no se aplica en modelos table=True")
    @pytest.mark.parametrize("duracion", [0, -10])
    def test_duracion_no_positiva_422(self, client: TestClient, duracion):
        assert client.post("/api/canciones", json=cancion_payload(duracion=duracion)).status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: campos requeridos no validados; responde 400 en vez de 422",
    )
    @pytest.mark.parametrize("campo", ["titulo", "artista", "album", "duracion", "anio", "genero"])
    def test_campo_requerido_faltante_422(self, client: TestClient, campo):
        payload = cancion_payload()
        del payload[campo]
        assert client.post("/api/canciones", json=payload).status_code == 422


class TestBuscarCanciones:
    def test_sin_filtros_devuelve_todo(self, client: TestClient, catalogo):
        r = client.get("/api/canciones/buscar")
        assert r.status_code == 200
        assert len(r.json()) == len(catalogo)

    def test_por_titulo_parcial(self, client: TestClient, catalogo):
        data = client.get("/api/canciones/buscar", params={"titulo": "hotel"}).json()
        assert [c["titulo"] for c in data] == ["Hotel California"]

    def test_insensible_a_mayusculas(self, client: TestClient, catalogo):
        a = client.get("/api/canciones/buscar", params={"artista": "QUEEN"}).json()
        b = client.get("/api/canciones/buscar", params={"artista": "queen"}).json()
        assert a == b
        assert len(a) == 1

    def test_por_genero(self, client: TestClient, catalogo):
        data = client.get("/api/canciones/buscar", params={"genero": "Pop"}).json()
        assert {c["titulo"] for c in data} == {"Imagine", "Billie Jean"}

    def test_filtros_combinados_son_AND(self, client: TestClient, catalogo):
        data = client.get("/api/canciones/buscar", params={"genero": "Rock", "artista": "Eagles"}).json()
        assert [c["titulo"] for c in data] == ["Hotel California"]

    def test_combinacion_sin_resultados(self, client: TestClient, catalogo):
        data = client.get("/api/canciones/buscar", params={"genero": "Pop", "artista": "Queen"}).json()
        assert data == []

    def test_sin_coincidencias(self, client: TestClient, catalogo):
        r = client.get("/api/canciones/buscar", params={"titulo": "zzzz"})
        assert r.status_code == 200
        assert r.json() == []

    def test_filtro_vacio_se_ignora(self, client: TestClient, catalogo):
        data = client.get("/api/canciones/buscar", params={"titulo": ""}).json()
        assert len(data) == len(catalogo)

    def test_parametro_desconocido_se_ignora(self, client: TestClient, catalogo):
        r = client.get("/api/canciones/buscar", params={"album": "Thriller"})
        assert r.status_code == 200
        assert len(r.json()) == len(catalogo)

    def test_inyeccion_sql_no_afecta(self, client: TestClient, catalogo):
        r = client.get("/api/canciones/buscar", params={"titulo": "' OR 1=1 --"})
        assert r.status_code == 200
        assert r.json() == []
        assert len(client.get("/api/canciones").json()) == len(catalogo)

    @pytest.mark.xfail(
        strict=True,
        reason="Los comodines LIKE (% y _) del usuario no se escapan: '%' coincide con todo",
    )
    def test_comodin_porcentaje_literal(self, client: TestClient, catalogo):
        assert client.get("/api/canciones/buscar", params={"titulo": "%"}).json() == []

    def test_buscar_no_choca_con_id(self, client: TestClient):
        # /buscar se declara antes de /{cancion_id}, así que no da 422 por "buscar" no entero
        assert client.get("/api/canciones/buscar").status_code == 200


class TestObtenerCancion:
    def test_obtener(self, client: TestClient, cancion):
        r = client.get(f"/api/canciones/{cancion['id']}")
        assert r.status_code == 200
        assert r.json() == cancion

    def test_no_existe_404(self, client: TestClient):
        r = client.get("/api/canciones/999")
        assert r.status_code == 404
        assert r.json()["detail"] == "Canción no encontrada"

    def test_id_no_entero_422(self, client: TestClient):
        assert client.get("/api/canciones/abc").status_code == 422


class TestActualizarCancion:
    def test_actualizar_completo(self, client: TestClient, cancion):
        nuevo = cancion_payload(titulo="Nuevo", artista="Otro", album="Otro album", duracion=100, anio=2020, genero="Jazz")
        r = client.put(f"/api/canciones/{cancion['id']}", json=nuevo)
        assert r.status_code == 200
        data = r.json()
        for campo, valor in nuevo.items():
            assert data[campo] == valor
        assert client.get(f"/api/canciones/{cancion['id']}").json()["titulo"] == "Nuevo"

    def test_actualizacion_parcial(self, client: TestClient, cancion):
        r = client.put(f"/api/canciones/{cancion['id']}", json={"genero": "Clásico"})
        assert r.status_code == 200
        data = r.json()
        assert data["genero"] == "Clásico"
        assert data["titulo"] == cancion["titulo"]
        assert data["duracion"] == cancion["duracion"]

    def test_id_en_body_no_cambia_id(self, client: TestClient, cancion):
        r = client.put(f"/api/canciones/{cancion['id']}", json={"id": 999, "titulo": "X"})
        assert r.status_code == 200
        assert r.json()["id"] == cancion["id"]

    def test_anio_futuro_422(self, client: TestClient, cancion):
        r = client.put(f"/api/canciones/{cancion['id']}", json={"anio": ANIO_ACTUAL + 5})
        assert r.status_code == 422
        assert client.get(f"/api/canciones/{cancion['id']}").json()["anio"] == cancion["anio"]

    def test_titulo_vacio_422(self, client: TestClient, cancion):
        assert client.put(f"/api/canciones/{cancion['id']}", json={"titulo": ""}).status_code == 422

    def test_no_existe_404(self, client: TestClient):
        assert client.put("/api/canciones/999", json=cancion_payload()).status_code == 404

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: el PUT copia fecha_creacion del body (se genera por defecto en el modelo), "
        "así que la fecha original se sobrescribe",
    )
    def test_fecha_creacion_no_cambia(self, client: TestClient, cancion):
        r = client.put(f"/api/canciones/{cancion['id']}", json={"titulo": "Otro"})
        assert r.json()["fecha_creacion"] == cancion["fecha_creacion"]


class TestEliminarCancion:
    def test_eliminar(self, client: TestClient, cancion):
        r = client.delete(f"/api/canciones/{cancion['id']}")
        assert r.status_code == 204
        assert r.content == b""
        assert client.get(f"/api/canciones/{cancion['id']}").status_code == 404

    def test_no_existe_404(self, client: TestClient):
        assert client.delete("/api/canciones/999").status_code == 404

    def test_eliminar_dos_veces_404(self, client: TestClient, cancion):
        client.delete(f"/api/canciones/{cancion['id']}")
        assert client.delete(f"/api/canciones/{cancion['id']}").status_code == 404

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: borrar una canción marcada como favorita viola NOT NULL en "
        "favoritos.id_cancion y responde 500",
    )
    def test_eliminar_cancion_con_favoritos(self, client: TestClient, usuario, cancion):
        client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        r = client.delete(f"/api/canciones/{cancion['id']}")
        assert r.status_code in (204, 400, 409)


# =============================================================================
# FAVORITOS (/api/favoritos)
# =============================================================================


class TestListarFavoritos:
    def test_lista_vacia(self, client: TestClient):
        r = client.get("/api/favoritos")
        assert r.status_code == 200
        assert r.json() == []

    def test_lista_todos_los_usuarios(self, client: TestClient, usuario, otro_usuario, cancion):
        client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]})
        client.post("/api/favoritos", json={"id_usuario": otro_usuario["id"], "id_cancion": cancion["id"]})
        data = client.get("/api/favoritos").json()
        assert len(data) == 2
        assert set(data[0]) == {"id", "id_usuario", "id_cancion", "fecha_marcado"}


class TestCrearFavorito:
    def test_crear(self, client: TestClient, usuario, cancion):
        r = client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]})
        assert r.status_code == 201
        data = r.json()
        assert data["id_usuario"] == usuario["id"]
        assert data["id_cancion"] == cancion["id"]
        assert isinstance(data["id"], int)
        assert "fecha_marcado" in data

    def test_duplicado_400(self, client: TestClient, usuario, cancion):
        body = {"id_usuario": usuario["id"], "id_cancion": cancion["id"]}
        client.post("/api/favoritos", json=body)
        r = client.post("/api/favoritos", json=body)
        assert r.status_code == 400
        assert "favorita" in r.json()["detail"]

    def test_misma_cancion_distintos_usuarios(self, client: TestClient, usuario, otro_usuario, cancion):
        assert client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]}).status_code == 201
        assert client.post("/api/favoritos", json={"id_usuario": otro_usuario["id"], "id_cancion": cancion["id"]}).status_code == 201

    def test_usuario_inexistente_404(self, client: TestClient, cancion):
        r = client.post("/api/favoritos", json={"id_usuario": 999, "id_cancion": cancion["id"]})
        assert r.status_code == 404
        assert r.json()["detail"] == "Usuario no encontrado"

    def test_cancion_inexistente_404(self, client: TestClient, usuario):
        r = client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": 999})
        assert r.status_code == 404
        assert r.json()["detail"] == "Canción no encontrada"

    @pytest.mark.xfail(strict=True, reason="BUG: tipos no validados; id_usuario='uno' responde 404 en vez de 422")
    def test_tipo_incorrecto_422(self, client: TestClient):
        r = client.post("/api/favoritos", json={"id_usuario": "uno", "id_cancion": 1})
        assert r.status_code == 422

    @pytest.mark.xfail(strict=True, reason="BUG: campos requeridos no validados; responde 404 en vez de 422")
    def test_body_vacio_422(self, client: TestClient):
        assert client.post("/api/favoritos", json={}).status_code == 422


class TestObtenerFavorito:
    def test_obtener(self, client: TestClient, usuario, cancion):
        creado = client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]}).json()
        r = client.get(f"/api/favoritos/{creado['id']}")
        assert r.status_code == 200
        assert r.json() == creado

    def test_no_existe_404(self, client: TestClient):
        r = client.get("/api/favoritos/999")
        assert r.status_code == 404
        assert r.json()["detail"] == "Favorito no encontrado"

    def test_id_no_entero_422(self, client: TestClient):
        assert client.get("/api/favoritos/x").status_code == 422


class TestEliminarFavorito:
    def test_eliminar(self, client: TestClient, usuario, cancion):
        creado = client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]}).json()
        r = client.delete(f"/api/favoritos/{creado['id']}")
        assert r.status_code == 204
        assert client.get(f"/api/favoritos/{creado['id']}").status_code == 404
        # usuario y canción siguen existiendo
        assert client.get(f"/api/usuarios/{usuario['id']}").status_code == 200
        assert client.get(f"/api/canciones/{cancion['id']}").status_code == 200

    def test_no_existe_404(self, client: TestClient):
        assert client.delete("/api/favoritos/999").status_code == 404

    def test_se_puede_volver_a_marcar(self, client: TestClient, usuario, cancion):
        body = {"id_usuario": usuario["id"], "id_cancion": cancion["id"]}
        creado = client.post("/api/favoritos", json=body).json()
        client.delete(f"/api/favoritos/{creado['id']}")
        assert client.post("/api/favoritos", json=body).status_code == 201


# =============================================================================
# FAVORITOS POR USUARIO (/api/usuarios/{id}/favoritos)
# =============================================================================


class TestFavoritosDeUsuario:
    def test_listar_vacio(self, client: TestClient, usuario):
        r = client.get(f"/api/usuarios/{usuario['id']}/favoritos")
        assert r.status_code == 200
        assert r.json() == []

    def test_listar_solo_los_del_usuario(self, client: TestClient, usuario, otro_usuario, catalogo):
        for c in catalogo[:2]:
            client.post(f"/api/usuarios/{usuario['id']}/favoritos/{c['id']}")
        client.post(f"/api/usuarios/{otro_usuario['id']}/favoritos/{catalogo[3]['id']}")

        data = client.get(f"/api/usuarios/{usuario['id']}/favoritos").json()
        assert len(data) == 2
        assert all(f["id_usuario"] == usuario["id"] for f in data)
        assert {f["id_cancion"] for f in data} == {catalogo[0]["id"], catalogo[1]["id"]}

    def test_listar_usuario_inexistente_404(self, client: TestClient):
        assert client.get("/api/usuarios/999/favoritos").status_code == 404

    def test_marcar(self, client: TestClient, usuario, cancion):
        r = client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert r.status_code == 201
        data = r.json()
        assert data["id_usuario"] == usuario["id"]
        assert data["id_cancion"] == cancion["id"]
        # visible también en el endpoint global
        assert client.get(f"/api/favoritos/{data['id']}").status_code == 200

    def test_marcar_duplicado_400(self, client: TestClient, usuario, cancion):
        client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        r = client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert r.status_code == 400
        assert r.json()["detail"] == "La canción ya está marcada como favorita"

    def test_marcar_duplicado_entre_endpoints(self, client: TestClient, usuario, cancion):
        client.post("/api/favoritos", json={"id_usuario": usuario["id"], "id_cancion": cancion["id"]})
        r = client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert r.status_code == 400

    def test_marcar_usuario_inexistente_404(self, client: TestClient, cancion):
        r = client.post(f"/api/usuarios/999/favoritos/{cancion['id']}")
        assert r.status_code == 404
        assert r.json()["detail"] == "Usuario no encontrado"

    def test_marcar_cancion_inexistente_404(self, client: TestClient, usuario):
        r = client.post(f"/api/usuarios/{usuario['id']}/favoritos/999")
        assert r.status_code == 404
        assert r.json()["detail"] == "Canción no encontrada"

    def test_desmarcar(self, client: TestClient, usuario, cancion):
        client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        r = client.delete(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert r.status_code == 204
        assert client.get(f"/api/usuarios/{usuario['id']}/favoritos").json() == []

    def test_desmarcar_no_marcado_404(self, client: TestClient, usuario, cancion):
        r = client.delete(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert r.status_code == 404
        assert r.json()["detail"] == "Favorito no encontrado"

    def test_desmarcar_no_afecta_a_otro_usuario(self, client: TestClient, usuario, otro_usuario, cancion):
        client.post(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        client.post(f"/api/usuarios/{otro_usuario['id']}/favoritos/{cancion['id']}")
        client.delete(f"/api/usuarios/{usuario['id']}/favoritos/{cancion['id']}")
        assert len(client.get(f"/api/usuarios/{otro_usuario['id']}/favoritos").json()) == 1

    @pytest.mark.parametrize("ruta", ["/api/usuarios/x/favoritos/1", "/api/usuarios/1/favoritos/x"])
    def test_ids_no_enteros_422(self, client: TestClient, ruta):
        assert client.post(ruta).status_code == 422
        assert client.delete(ruta).status_code == 422


# =============================================================================
# INTEGRACIÓN
# =============================================================================


class TestFlujoCompleto:
    def test_flujo_crear_marcar_listar_desmarcar(self, client: TestClient, session: Session):
        u = client.post("/api/usuarios", json={"nombre": "Flujo", "correo": "flujo@test.com"}).json()
        c1 = client.post("/api/canciones", json=cancion_payload(titulo="Uno")).json()
        c2 = client.post("/api/canciones", json=cancion_payload(titulo="Dos")).json()

        assert client.post(f"/api/usuarios/{u['id']}/favoritos/{c1['id']}").status_code == 201
        assert client.post("/api/favoritos", json={"id_usuario": u["id"], "id_cancion": c2["id"]}).status_code == 201

        favs = client.get(f"/api/usuarios/{u['id']}/favoritos").json()
        assert {f["id_cancion"] for f in favs} == {c1["id"], c2["id"]}

        assert client.delete(f"/api/usuarios/{u['id']}/favoritos/{c1['id']}").status_code == 204
        favs = client.get(f"/api/usuarios/{u['id']}/favoritos").json()
        assert [f["id_cancion"] for f in favs] == [c2["id"]]

        en_db = session.exec(select(Favorito).where(Favorito.id_usuario == u["id"])).all()
        assert len(en_db) == 1
