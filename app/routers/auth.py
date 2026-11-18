from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import crear_token, get_usuario_actual, hash_password, verificar_password
from app.database import get_session
from app.models import Usuario
from musica_api.config import settings

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

_PATRON_CORREO = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


def _normalizar_correo(valor: str) -> str:
    valor = valor.strip().lower()
    if not re.fullmatch(_PATRON_CORREO, valor):
        raise ValueError("Correo inválido")
    return valor


class Registro(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    correo: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        return _normalizar_correo(v)


class Login(BaseModel):
    correo: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        return v.strip().lower()


class UsuarioPublico(BaseModel):
    id: int
    nombre: str
    correo: str
    fecha_registro: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioPublico


def _token_para(usuario: Usuario) -> Token:
    return Token(
        access_token=crear_token(usuario.id),
        expires_in=settings.access_token_expire_minutes * 60,
        usuario=UsuarioPublico.model_validate(usuario, from_attributes=True),
    )


@router.post("/registro", response_model=Token, status_code=status.HTTP_201_CREATED)
def registrar(datos: Registro, session: Session = Depends(get_session)):
    """Crea un usuario con contraseña y devuelve un token (inicia sesión directamente)."""
    usuario = Usuario(nombre=datos.nombre, correo=datos.correo)
    usuario.password_hash = hash_password(datos.password)
    try:
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese correo",
        ) from None
    return _token_para(usuario)


@router.post("/login", response_model=Token)
def login(datos: Login, session: Session = Depends(get_session)):
    usuario = session.exec(select(Usuario).where(func.lower(Usuario.correo) == datos.correo)).first()
    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_para(usuario)


@router.get("/me", response_model=UsuarioPublico)
def perfil(usuario: Usuario = Depends(get_usuario_actual)):
    return usuario
