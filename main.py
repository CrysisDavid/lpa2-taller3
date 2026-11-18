from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routers import canciones_router, favoritos_router, peliculas_router, usuarios_router
from musica_api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crea tablas al iniciar y limpia al terminar."""
    create_db_and_tables()
    yield
    print("cerrando aplicación...")


app = FastAPI(
    title=settings.app_name,
    description="API RESTful para gestionar usuarios, canciones y favoritos",
    version=settings.app_version,
    lifespan=lifespan,
    contact={"name": "Equipo de desarrollo", "email": "soporte@ejemplo.com"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios_router)
app.include_router(canciones_router)
app.include_router(peliculas_router)
app.include_router(favoritos_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "documentacion": "/docs",
        "redoc": "/redoc",
        "usuarios": "/api/usuarios",
        "canciones": "/api/canciones",
        "favoritos": "/api/favoritos",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "database": "ok",
        "environment": settings.environment,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


