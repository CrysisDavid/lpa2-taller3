import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError, field_validator
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint


def _raise_validation_error(field_name: str, message: str, value):
    raise ValidationError.from_exception_data(
        "ValidationError",
        [
            {
                "type": "value_error",
                "loc": (field_name,),
                "msg": message,
                "input": value,
                "ctx": {"error": ValueError(message)},
            }
        ],
    )


def _parse_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            _raise_validation_error("fecha", "Fecha inválida", value)
    return value


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)
    correo: str = Field(index=True, unique=True)
    fecha_registro: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    favoritos: list["Favorito"] = Relationship(back_populates="usuario")

    def __init__(self, **kwargs):
        nombre = kwargs.get("nombre")
        if nombre is not None and not str(nombre).strip():
            _raise_validation_error("nombre", "El nombre no puede estar vacío", nombre)

        correo = kwargs.get("correo")
        if correo is not None and not re.fullmatch(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", str(correo).strip()):
            _raise_validation_error("correo", "Correo inválido", correo)

        kwargs["fecha_registro"] = _parse_datetime(kwargs.get("fecha_registro")) or datetime.now(timezone.utc)
        super().__init__(**kwargs)

    @field_validator("fecha_registro", mode="before")
    @classmethod
    def validar_fecha_registro(cls, value):
        return _parse_datetime(value)


class Cancion(SQLModel, table=True):
    __tablename__ = "canciones"

    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str = Field(index=True)
    artista: str = Field(index=True)
    album: str
    duracion: int = Field(ge=1)
    anio: int = Field(index=True, ge=1900)
    genero: str = Field(index=True)
    fecha_creacion: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    favoritos: list["Favorito"] = Relationship(back_populates="cancion")

    def __init__(self, **kwargs):
        for field_name in ("titulo", "artista", "album", "genero"):
            value = kwargs.get(field_name)
            if value is not None and not str(value).strip():
                _raise_validation_error(field_name, f"{field_name} no puede estar vacío", value)

        anio = kwargs.get("anio")
        if anio is not None and int(anio) > datetime.now(timezone.utc).year:
            _raise_validation_error("anio", "El año no puede ser mayor al año actual", anio)

        kwargs["fecha_creacion"] = _parse_datetime(kwargs.get("fecha_creacion")) or datetime.now(timezone.utc)
        super().__init__(**kwargs)

    @field_validator("fecha_creacion", mode="before")
    @classmethod
    def validar_fecha_creacion(cls, value):
        return _parse_datetime(value)


class Favorito(SQLModel, table=True):
    __tablename__ = "favoritos"
    __table_args__ = (UniqueConstraint("id_usuario", "id_cancion", name="uq_favorito_usuario_cancion"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuarios.id", index=True)
    id_cancion: int = Field(foreign_key="canciones.id", index=True)
    fecha_marcado: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    usuario: Optional[Usuario] = Relationship(back_populates="favoritos")
    cancion: Optional[Cancion] = Relationship(back_populates="favoritos")

    def __init__(self, **kwargs):
        kwargs["fecha_marcado"] = _parse_datetime(kwargs.get("fecha_marcado")) or datetime.now(timezone.utc)
        super().__init__(**kwargs)

    @field_validator("fecha_marcado", mode="before")
    @classmethod
    def validar_fecha_marcado(cls, value):
        return _parse_datetime(value)
