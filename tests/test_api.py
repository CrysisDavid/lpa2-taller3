"""Tests para la API de Música."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Cancion, Favorito, Usuario

# Las fixtures session, client y como están en tests/conftest.py.


@pytest.fixture(name="usuario_test")
def usuario_test_fixture(session: Session, como):
    """Usuario guardado en la base de datos y autenticado en la prueba."""
    usuario = Usuario(nombre="Ana García", correo="ana@test.com")
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    como(usuario)
    return usuario


@pytest.fixture(name="cancion_test")
def cancion_test_fixture(session: Session):
    cancion = Cancion(
        titulo="Luna",
        artista="Sol",
        album="Nocturno",
        duracion=180,
        anio=2024,
        genero="Rock",
    )
    session.add(cancion)
    session.commit()
    session.refresh(cancion)
    return cancion


class TestUsuarios:
    def test_listar_usuarios_solo_el_propio(self, client: TestClient, usuario_test: Usuario):
        response = client.get("/api/usuarios")
        assert response.status_code == 200
        assert [u["id"] for u in response.json()] == [usuario_test.id]

    def test_crear_usuario_por_registro(self, client: TestClient):
        payload = {"nombre": "Carlos", "correo": "carlos@test.com", "password": "secreta123"}
        response = client.post("/api/auth/registro", json=payload)
        assert response.status_code == 201
        data = response.json()["usuario"]
        assert data["nombre"] == "Carlos"
        assert data["correo"] == "carlos@test.com"
        assert isinstance(data["fecha_registro"], str)

    def test_crear_usuario_por_crud_prohibido(self, client: TestClient, usuario_test: Usuario):
        payload = {"nombre": "Carlos", "correo": "carlos@test.com", "fecha_registro": "2026-11-17T21:18:00.119Z"}
        response = client.post("/api/usuarios", json=payload)
        assert response.status_code == 403

    def test_crear_usuario_correo_duplicado(self, client: TestClient, usuario_test: Usuario):
        payload = {"nombre": "Ana Duplicada", "correo": usuario_test.correo, "password": "secreta123"}
        response = client.post("/api/auth/registro", json=payload)
        assert response.status_code == 400

    def test_obtener_usuario(self, client: TestClient, usuario_test: Usuario):
        response = client.get(f"/api/usuarios/{usuario_test.id}")
        assert response.status_code == 200
        assert response.json()["nombre"] == usuario_test.nombre

    def test_obtener_otro_usuario_prohibido(self, client: TestClient, usuario_test: Usuario):
        response = client.get("/api/usuarios/999")
        assert response.status_code == 403

    def test_actualizar_usuario(self, client: TestClient, usuario_test: Usuario):
        payload = {"nombre": "Ana Actualizada", "correo": "ana_nueva@test.com"}
        response = client.put(f"/api/usuarios/{usuario_test.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["nombre"] == "Ana Actualizada"
        assert data["correo"] == "ana_nueva@test.com"

    def test_eliminar_usuario(self, client: TestClient, session: Session, usuario_test: Usuario):
        usuario_id = usuario_test.id
        response = client.delete(f"/api/usuarios/{usuario_id}")
        assert response.status_code == 204
        assert session.get(Usuario, usuario_id) is None
        # la sesión del usuario eliminado deja de ser válida
        assert client.get(f"/api/usuarios/{usuario_id}").status_code == 401


class TestCanciones:
    def test_listar_canciones(self, client: TestClient):
        response = client.get("/api/canciones")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_crear_cancion(self, client: TestClient):
        payload = {
            "titulo": "Estrella",
            "artista": "Grupo A",
            "album": "Noche",
            "duracion": 220,
            "anio": 2023,
            "genero": "Pop",
        }
        response = client.post("/api/canciones", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["titulo"] == payload["titulo"]
        assert data["artista"] == payload["artista"]

    def test_obtener_cancion(self, client: TestClient, cancion_test: Cancion):
        response = client.get(f"/api/canciones/{cancion_test.id}")
        assert response.status_code == 200
        assert response.json()["titulo"] == cancion_test.titulo

    def test_actualizar_cancion(self, client: TestClient, cancion_test: Cancion):
        payload = {
            "titulo": "Luna nueva",
            "artista": "Sol modificado",
            "album": "Nocturno 2",
            "duracion": 210,
            "anio": 2025,
            "genero": "Indie",
        }
        response = client.put(f"/api/canciones/{cancion_test.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["titulo"] == payload["titulo"]
        assert data["genero"] == "Indie"

    def test_eliminar_cancion(self, client: TestClient, cancion_test: Cancion):
        response = client.delete(f"/api/canciones/{cancion_test.id}")
        assert response.status_code == 204
        assert client.get(f"/api/canciones/{cancion_test.id}").status_code == 404

    def test_buscar_canciones(self, client: TestClient, cancion_test: Cancion):
        response = client.get("/api/canciones/buscar", params={"titulo": "Luna"})
        assert response.status_code == 200
        data = response.json()
        assert any(item["titulo"] == cancion_test.titulo for item in data)

    def test_buscar_canciones_multiples_filtros(self, client: TestClient, cancion_test: Cancion):
        response = client.get(
            "/api/canciones/buscar",
            params={"artista": "Sol", "genero": "Rock"},
        )
        assert response.status_code == 200
        data = response.json()
        assert any(item["titulo"] == cancion_test.titulo for item in data)


class TestFavoritos:
    def test_listar_favoritos(self, client: TestClient, usuario_test: Usuario):
        response = client.get("/api/favoritos")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_crear_favorito(self, client: TestClient, usuario_test: Usuario, cancion_test: Cancion):
        payload = {"id_usuario": usuario_test.id, "id_cancion": cancion_test.id}
        response = client.post("/api/favoritos", json=payload)
        assert response.status_code == 201
        assert response.json()["id_usuario"] == usuario_test.id

    def test_crear_favorito_duplicado(self, client: TestClient, usuario_test: Usuario, cancion_test: Cancion):
        client.post("/api/favoritos", json={"id_usuario": usuario_test.id, "id_cancion": cancion_test.id})
        response = client.post("/api/favoritos", json={"id_usuario": usuario_test.id, "id_cancion": cancion_test.id})
        assert response.status_code == 400

    def test_eliminar_favorito(self, client: TestClient, session: Session, usuario_test: Usuario, cancion_test: Cancion):
        favorito = Favorito(id_usuario=usuario_test.id, id_cancion=cancion_test.id)
        session.add(favorito)
        session.commit()
        session.refresh(favorito)

        response = client.delete(f"/api/favoritos/{favorito.id}")
        assert response.status_code == 204

    def test_marcar_favorito_usuario(self, client: TestClient, usuario_test: Usuario, cancion_test: Cancion):
        response = client.post(f"/api/usuarios/{usuario_test.id}/favoritos/{cancion_test.id}")
        assert response.status_code == 201
        assert response.json()["id_usuario"] == usuario_test.id

    def test_listar_favoritos_usuario(self, client: TestClient, session: Session, usuario_test: Usuario, cancion_test: Cancion):
        session.add(Favorito(id_usuario=usuario_test.id, id_cancion=cancion_test.id))
        session.commit()

        response = client.get(f"/api/usuarios/{usuario_test.id}/favoritos")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_validar_email_invalido():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Usuario(nombre="Pedro", correo="correo-invalido")


def test_validar_anio_invalido():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Cancion(
            titulo="Canción futura",
            artista="Artista",
            album="Album",
            duracion=120,
            anio=3000,
            genero="Jazz",
        )

# TESTS DE INTEGRACIÓN
# =============================================================================

class TestIntegracion:
    """Tests de integración que prueban flujos completos."""
    
    # TODO: Test de flujo completo: crear usuario, canción y marcar favorito
    def test_flujo_completo(self, client: TestClient):
        """Test que verifica el flujo completo de la aplicación"""
        # 1. Crear usuario

        # 2. Crear canción

        # 3. Marcar como favorito

        # 4. Verificar que aparece en favoritos del usuario

        pass


# =============================================================================
# TESTS DE VALIDACIÓN
# =============================================================================

class TestValidacion:
    """Tests para validaciones de datos."""
    
    # TODO: Test para validar email inválido
    def test_email_invalido(self, client: TestClient):
        """Test para verificar validación de email"""

        pass
    
    # TODO: Test para validar año de canción
    def test_año_cancion_invalido(self, client: TestClient):
        """Test para verificar validación de año"""

        pass
    
    # TODO: Test para validar campos requeridos
    def test_campos_requeridos(self, client: TestClient):
        """Test para verificar que los campos requeridos son obligatorios"""

        pass


