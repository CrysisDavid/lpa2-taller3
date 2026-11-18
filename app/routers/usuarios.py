from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Cancion, Favorito, Usuario

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"])


@router.get("")
def listar_usuarios(session: Session = Depends(get_session)):
    return session.exec(select(Usuario)).all()


@router.post("", status_code=status.HTTP_201_CREATED)
def crear_usuario(usuario: Usuario, session: Session = Depends(get_session)):
    usuario.id = None
    usuario.fecha_registro = usuario.fecha_registro or datetime.now(timezone.utc)
    try:
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
        return usuario
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese correo",
        ) from None


@router.get("/{usuario_id}")
def obtener_usuario(usuario_id: int, session: Session = Depends(get_session)):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


@router.put("/{usuario_id}")
def actualizar_usuario(usuario_id: int, usuario: Usuario, session: Session = Depends(get_session)):
    db_usuario = session.get(Usuario, usuario_id)
    if not db_usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    data = usuario.model_dump(exclude_unset=True)
    for campo, valor in data.items():
        if campo == "id":
            continue
        setattr(db_usuario, campo, valor)

    try:
        session.add(db_usuario)
        session.commit()
        session.refresh(db_usuario)
        return db_usuario
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese correo",
        ) from None


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(usuario_id: int, session: Session = Depends(get_session)):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    session.delete(usuario)
    session.commit()
    return None


@router.get("/{usuario_id}/favoritos")
def listar_favoritos_usuario(usuario_id: int, session: Session = Depends(get_session)):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    favoritos = session.exec(select(Favorito).where(Favorito.id_usuario == usuario_id)).all()
    return favoritos


@router.post("/{usuario_id}/favoritos/{cancion_id}", status_code=status.HTTP_201_CREATED)
def marcar_favorito_usuario(usuario_id: int, cancion_id: int, session: Session = Depends(get_session)):
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    cancion = session.get(Cancion, cancion_id)
    if not cancion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")

    favorito = session.exec(
        select(Favorito).where(Favorito.id_usuario == usuario_id, Favorito.id_cancion == cancion_id)
    ).first()
    if favorito:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La canción ya está marcada como favorita")

    nuevo_favorito = Favorito(id_usuario=usuario_id, id_cancion=cancion_id)
    try:
        session.add(nuevo_favorito)
        session.commit()
        session.refresh(nuevo_favorito)
        return nuevo_favorito
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La canción ya está marcada como favorita") from None


@router.delete("/{usuario_id}/favoritos/{cancion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_favorito_usuario(usuario_id: int, cancion_id: int, session: Session = Depends(get_session)):
    favorito = session.exec(
        select(Favorito).where(Favorito.id_usuario == usuario_id, Favorito.id_cancion == cancion_id)
    ).first()
    if not favorito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorito no encontrado")

    session.delete(favorito)
    session.commit()
    return None
