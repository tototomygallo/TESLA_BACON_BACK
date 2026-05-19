import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import SessionLocal
from app.models import Usuario
from app.routes import auth, bacon_proxy, muestras, resumen
from app.services.bacon_retry import reintentar_pendientes

RETRY_INTERVAL_SECONDS = 300  # 5 minutos


async def _bacon_retry_loop():
    """Tarea en segundo plano: cada 5 minutos reintenta notificar a BACON."""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
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
    #init_db()
    _seed_usuarios()
    # Lanzar tarea de reintento en segundo plano
    task = asyncio.create_task(_bacon_retry_loop())
    yield
    task.cancel()


app = FastAPI(
    title="TauKits API",
    description="Backend para el sistema de gestión de muestras TauKits — Tesla Diagnóstico / BACON",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(bacon_proxy.router, prefix="/api")
app.include_router(muestras.router, prefix="/api")
app.include_router(resumen.router, prefix="/api")


def _seed_usuarios():
    db = SessionLocal()
    try:
        if db.query(Usuario).count() > 0:
            return
        usuarios = [
            Usuario(id="tec1", nombre="María López", clave="tec1", rol="tecnico"),
            Usuario(id="tec2", nombre="Juan Pérez", clave="tec2", rol="tecnico"),
            Usuario(id="bio1", nombre="Dra. Ana García", clave="bio1", rol="bioquimico"),
            Usuario(id="bio2", nombre="Dr. Carlos Ruiz", clave="bio2", rol="bioquimico"),
            Usuario(id="adm1", nombre="Laura Martínez", clave="adm1", rol="admin"),
            Usuario(id="adm2", nombre="Roberto Silva", clave="adm2", rol="admin"),
        ]
        db.add_all(usuarios)
        db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "app": "TauKits API", "docs": "/docs"}
