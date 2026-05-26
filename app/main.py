import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import SessionLocal
from app.models import Usuario
from app.routes import auth, bacon_proxy, configuracion, muestras, resumen
from app.services.bacon_retry import reintentar_pendientes
from app.services.discrepancias import eliminar_discrepancias_vencidas

RETRY_INTERVAL_SECONDS = 300  # 5 minutos


async def _bacon_retry_loop():
    """Tarea en segundo plano: reintentos BACON y limpieza de discrepancias."""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            eliminar_discrepancias_vencidas(db)
            resultado = await reintentar_pendientes(db)
            if resultado["total"] > 0:
                print(
                    f"[BACON Retry] {resultado['exitosos']} OK, "
                    f"{resultado['fallidos']} fallidos de {resultado['total']} pendientes"
                )
        except Exception as e:
            print(f"[BACON Retry] Error: {e}")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown de la app."""
    _seed_usuarios()
    _limpiar_discrepancias_vencidas()
    task = asyncio.create_task(_bacon_retry_loop())
    yield
    task.cancel()


app = FastAPI(
    title="TauKits API",
    description="Backend para el sistema de gestion de muestras TauKits - Tesla Diagnostico / BACON",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173","http://10.1.100.3:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(bacon_proxy.router, prefix="/api")
app.include_router(configuracion.router, prefix="/api")
app.include_router(muestras.router, prefix="/api")
app.include_router(resumen.router, prefix="/api")


def _seed_usuarios():
    db = SessionLocal()
    try:
        if db.query(Usuario).count() > 0:
            return

        ahora = datetime.now()
        usuarios = [
            Usuario(
                id="tec1",
                username="tec1",
                name="Maria Lopez",
                email="tec1@tesla.local",
                password_hash=auth.hash_password("tec1"),
                rol="tecnico",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
            Usuario(
                id="tec2",
                username="tec2",
                name="Juan Perez",
                email="tec2@tesla.local",
                password_hash=auth.hash_password("tec2"),
                rol="tecnico",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
            Usuario(
                id="bio1",
                username="bio1",
                name="Dra. Ana Garcia",
                email="bio1@tesla.local",
                password_hash=auth.hash_password("bio1"),
                rol="bioquimico",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
            Usuario(
                id="bio2",
                username="bio2",
                name="Dr. Carlos Ruiz",
                email="bio2@tesla.local",
                password_hash=auth.hash_password("bio2"),
                rol="bioquimico",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
            Usuario(
                id="adm1",
                username="adm1",
                name="Laura Martinez",
                email="adm1@tesla.local",
                password_hash=auth.hash_password("adm1"),
                rol="admin",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
            Usuario(
                id="adm2",
                username="adm2",
                name="Roberto Silva",
                email="adm2@tesla.local",
                password_hash=auth.hash_password("adm2"),
                rol="admin",
                active=True,
                password_changed_at=ahora,
                force_password_change=False,
                created_at=ahora,
                updated_at=ahora,
            ),
        ]
        db.add_all(usuarios)
        db.commit()
    finally:
        db.close()


def _limpiar_discrepancias_vencidas():
    db = SessionLocal()
    try:
        eliminar_discrepancias_vencidas(db)
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "app": "TauKits API", "docs": "/docs"}
