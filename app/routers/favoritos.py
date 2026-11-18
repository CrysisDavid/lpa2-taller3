from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Cancion, Favorito, Usuario

router = APIRouter(prefix="/api", tags=["Favoritos"])


@router.get("/favoritos")
def listar_favoritos(session: Session = Depends(get_session)):
    return session.exec(select(Favorito)).all()


@router.post("/favoritos", status_code=status.HTTP_201_CREATED)
def crear_favorito(favorito: Favorito, session: Session = Depends(get_session)):
    favorito.id = None
    usuario = session.get(Usuario, favorito.id_usuario)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    cancion = session.get(Cancion, favorito.id_cancion)
    if not cancion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canción no encontrada")

    try:
        session.add(favorito)
        session.commit()
        session.refresh(favorito)
        return favorito
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La canción ya está marcada como favorita para este usuario",
        ) from None


@router.get("/favoritos/{favorito_id}")
def obtener_favorito(favorito_id: int, session: Session = Depends(get_session)):
    favorito = session.get(Favorito, favorito_id)
    if not favorito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorito no encontrado")
    return favorito


@router.delete("/favoritos/{favorito_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_favorito(favorito_id: int, session: Session = Depends(get_session)):
    favorito = session.get(Favorito, favorito_id)
    if not favorito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorito no encontrado")

    session.delete(favorito)
    session.commit()
    return None
