from .canciones import router as canciones_router
from .favoritos import router as favoritos_router
from .peliculas import router as peliculas_router
from .usuarios import router as usuarios_router

__all__ = [
    "canciones_router",
    "favoritos_router",
    "peliculas_router",
    "usuarios_router",
]
