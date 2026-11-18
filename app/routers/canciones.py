from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Cancion

router = APIRouter(prefix="/api/canciones", tags=["Canciones"])


@router.get("")
def listar_canciones(session: Session = Depends(get_session)):
    return session.exec(select(Cancion)).all()


@router.post("", status_code=status.HTTP_201_CREATED)
def crear_cancion(cancion: Cancion, session: Session = Depends(get_session)):
    cancion.id = None
    cancion.fecha_creacion = datetime.now(timezone.utc)
    try:
        session.add(cancion)
        session.commit()
        session.refresh(cancion)
        return cancion
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo crear la canción") from None


@router.get("/buscar")
def buscar_canciones(
    titulo: str | None = Query(default=None),
    artista: str | None = Query(default=None),
    genero: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    query = select(Cancion)

    if titulo:
        query = query.where(Cancion.titulo.ilike(f"%{titulo}%"))
    if artista:
        query = query.where(Cancion.artista.ilike(f"%{artista}%"))
    if genero:
        query = query.where(Cancion.genero.ilike(f"%{genero}%"))

    return session.exec(query).all()


@router.get("/{cancion_id}")
def obtener_cancion(cancion_id: int, session: Session = Depends(get_session)):
    cancion = session.get(Cancion, cancion_id)
    if not cancion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")
    return cancion


@router.put("/{cancion_id}")
def actualizar_cancion(cancion_id: int, cancion: Cancion, session: Session = Depends(get_session)):
    db_cancion = session.get(Cancion, cancion_id)
    if not db_cancion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")

    data = cancion.model_dump(exclude_unset=True)
    for campo, valor in data.items():
        if campo == "id":
            continue
        setattr(db_cancion, campo, valor)

    try:
        session.add(db_cancion)
        session.commit()
        session.refresh(db_cancion)
        return db_cancion
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo actualizar la canción") from None


@router.delete("/{cancion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cancion(cancion_id: int, session: Session = Depends(get_session)):
    cancion = session.get(Cancion, cancion_id)
    if not cancion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")

    session.delete(cancion)
    session.commit()
    return None

