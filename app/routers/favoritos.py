from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import exigir_mismo_usuario, get_usuario_actual
from app.database import get_session
from app.models import Cancion, Favorito, Usuario

# Todas las rutas exigen un token JWT válido (Authorization: Bearer <token>) y cada
# usuario solo ve y gestiona sus propios favoritos. El administrador ve y gestiona todos.
router = APIRouter(prefix="/api", tags=["Favoritos"], dependencies=[Depends(get_usuario_actual)])


def _favorito_propio(favorito_id: int, actual: Usuario, session: Session) -> Favorito:
    favorito = session.get(Favorito, favorito_id)
    # Un favorito de otro usuario responde igual que uno inexistente: no se revela que existe.
    if not favorito or (favorito.id_usuario != actual.id and not actual.es_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorito no encontrado")
    return favorito


@router.get("/favoritos")
def listar_favoritos(
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    consulta = select(Favorito)
    if not actual.es_admin:
        consulta = consulta.where(Favorito.id_usuario == actual.id)
    return session.exec(consulta).all()


@router.post("/favoritos", status_code=status.HTTP_201_CREATED)
def crear_favorito(
    favorito: Favorito,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    favorito.id = None
    exigir_mismo_usuario(favorito.id_usuario, actual)
    # El administrador puede marcar favoritos para otro usuario: debe existir.
    if favorito.id_usuario != actual.id and not session.get(Usuario, favorito.id_usuario):
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
def obtener_favorito(
    favorito_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    return _favorito_propio(favorito_id, actual, session)


@router.delete("/favoritos/{favorito_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_favorito(
    favorito_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    session.delete(_favorito_propio(favorito_id, actual, session))
    session.commit()
    return None
