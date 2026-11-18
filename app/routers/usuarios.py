from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import exigir_mismo_usuario, get_usuario_actual
from app.database import get_session
from app.models import Cancion, Favorito, Usuario

# Todas las rutas exigen un token JWT válido (Authorization: Bearer <token>) y cada
# usuario solo puede leer y modificar su propio registro y sus propios favoritos.
# El administrador (es_admin) puede ver y gestionar a todos los usuarios.
router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"], dependencies=[Depends(get_usuario_actual)])


@router.get("")
def listar_usuarios(
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    """El administrador ve a todos los usuarios; los demás, solo a sí mismos."""
    if actual.es_admin:
        return session.exec(select(Usuario).order_by(Usuario.id)).all()
    return [actual]


@router.post("", status_code=status.HTTP_403_FORBIDDEN)
def crear_usuario():
    """Las cuentas se crean con POST /api/auth/registro (cada usuario crea la suya)."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Los usuarios se crean registrándose en /api/auth/registro",
    )


@router.get("/{usuario_id}")
def obtener_usuario(
    usuario_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


@router.put("/{usuario_id}")
def actualizar_usuario(
    usuario_id: int,
    usuario: Usuario,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
    db_usuario = session.get(Usuario, usuario_id)
    if not db_usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    data = usuario.model_dump(exclude_unset=True)
    for campo, valor in data.items():
        # El id no se cambia y el rol de administrador nunca se acepta del cliente.
        if campo in ("id", "es_admin"):
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
def eliminar_usuario(
    usuario_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if usuario.es_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta de administrador no se puede eliminar",
        )

    # Al eliminar la cuenta se eliminan también sus favoritos (si no, SQLAlchemy
    # intentaría poner id_usuario=NULL en ellos y la base de datos lo rechaza).
    for favorito in session.exec(select(Favorito).where(Favorito.id_usuario == usuario_id)).all():
        session.delete(favorito)
    session.delete(usuario)
    session.commit()
    return None


@router.get("/{usuario_id}/favoritos")
def listar_favoritos_usuario(
    usuario_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    favoritos = session.exec(select(Favorito).where(Favorito.id_usuario == usuario_id)).all()
    return favoritos


@router.post("/{usuario_id}/favoritos/{cancion_id}", status_code=status.HTTP_201_CREATED)
def marcar_favorito_usuario(
    usuario_id: int,
    cancion_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
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
def eliminar_favorito_usuario(
    usuario_id: int,
    cancion_id: int,
    session: Session = Depends(get_session),
    actual: Usuario = Depends(get_usuario_actual),
):
    exigir_mismo_usuario(usuario_id, actual)
    favorito = session.exec(
        select(Favorito).where(Favorito.id_usuario == usuario_id, Favorito.id_cancion == cancion_id)
    ).first()
    if not favorito:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorito no encontrado")

    session.delete(favorito)
    session.commit()
    return None
