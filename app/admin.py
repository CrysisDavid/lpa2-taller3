"""Cuenta de administrador: se crea (o se repara) al arrancar la API."""

from sqlalchemy import func
from sqlmodel import Session, select

from app.auth import hash_password
from app.models import Usuario
from musica_api.config import settings

ADMIN_PASSWORD_POR_DEFECTO = "admin@2026.musica"


def asegurar_admin(session: Session) -> Usuario:
    """Garantiza que exista la cuenta de administrador configurada en settings.

    - Si no existe un usuario con ``settings.admin_correo``, lo crea con rol de admin.
    - Si existe, le asigna el rol de admin y, si no tiene contraseña (por ejemplo,
      un usuario creado a mano en la base de datos), le pone la configurada.
    No cambia una contraseña que ya exista.
    """
    correo = settings.admin_correo.strip().lower()
    admin = session.exec(select(Usuario).where(func.lower(Usuario.correo) == correo)).first()
    if admin is None:
        admin = Usuario(nombre=settings.admin_nombre, correo=correo)
        admin.password_hash = hash_password(settings.admin_password)
        admin.es_admin = True
    else:
        if not admin.es_admin:
            admin.es_admin = True
        if not admin.password_hash:
            admin.password_hash = hash_password(settings.admin_password)
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin
