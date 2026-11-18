"""Autenticación: hash de contraseñas, tokens JWT y dependencia de usuario actual."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.database import get_session
from app.models import Usuario
from musica_api.config import settings

_ALGORITMO_HASH = "pbkdf2_sha256"
_ITERACIONES = 600_000  # recomendación OWASP para PBKDF2-HMAC-SHA256

_bearer = HTTPBearer(auto_error=False, description="Token JWT obtenido en /api/auth/login")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    """Devuelve el hash en formato ``pbkdf2_sha256$iteraciones$sal$hash``."""
    sal = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), sal, _ITERACIONES)
    return f"{_ALGORITMO_HASH}${_ITERACIONES}${_b64(sal)}${_b64(digest)}"


def verificar_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algoritmo, iteraciones, sal, esperado = password_hash.split("$")
        if algoritmo != _ALGORITMO_HASH:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(sal), int(iteraciones))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, _unb64(esperado))


def crear_token(usuario_id: int) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Usuario:
    """Dependencia: exige un token Bearer válido y devuelve el usuario autenticado."""
    if credenciales is None:
        raise _no_autorizado("No autenticado")
    try:
        payload = jwt.decode(
            credenciales.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require": ["sub", "iat", "exp"]},
        )
        usuario_id = int(payload["sub"])
        emitido = int(payload["iat"])
    except jwt.ExpiredSignatureError:
        raise _no_autorizado("La sesión expiró, inicia sesión de nuevo") from None
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise _no_autorizado("Token inválido") from None

    usuario = session.get(Usuario, usuario_id)
    # SQLite reutiliza los id de filas borradas: un token emitido antes de que se
    # creara esta cuenta pertenece a otro usuario (ya eliminado) y se rechaza.
    if not usuario or emitido < _segundos(usuario.fecha_registro):
        raise _no_autorizado("Token inválido")
    return usuario


def _segundos(fecha: datetime) -> int:
    if fecha.tzinfo is None:  # SQLite devuelve fechas sin zona horaria (guardadas en UTC)
        fecha = fecha.replace(tzinfo=timezone.utc)
    return int(fecha.timestamp())


def exigir_mismo_usuario(usuario_id: int, actual: Usuario) -> None:
    """Autorización: cada usuario solo puede leer y modificar sus propios datos.

    El administrador puede acceder a los datos de cualquier usuario.
    """
    if usuario_id != actual.id and not actual.es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a los datos de otro usuario",
        )
