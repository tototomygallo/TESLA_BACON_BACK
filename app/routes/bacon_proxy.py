from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Usuario
from app.services.bacon import obtener_muestras_enviadas
from app.services.bacon_retry import obtener_pendientes, reintentar_pendientes
from app.schemas import BaconMuestraSchema

router = APIRouter(prefix="/bacon", tags=["BACON"])


@router.get("/muestras-enviadas", response_model=list[BaconMuestraSchema])
async def muestras_enviadas(usuario: Usuario = Depends(get_current_user)):
    try:
        datos = await obtener_muestras_enviadas()
        return datos
    except Exception as e:
        print(f"[BACON] Error al consultar: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con BACON: {e}",
        )


class PendientesResponse(BaseModel):
    cantidad: int
    codigos: list[str]


@router.get("/pendientes", response_model=PendientesResponse)
async def pendientes(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Muestras ingresadas que no pudimos notificar a BACON."""
    muestras = await obtener_pendientes(db)
    return PendientesResponse(
        cantidad=len(muestras),
        codigos=[m.codigo_taukit for m in muestras],
    )


class ReintentoResponse(BaseModel):
    exitosos: int
    fallidos: int
    total: int


@router.post("/reintentar", response_model=ReintentoResponse)
async def reintentar(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Reintenta notificar a BACON las muestras pendientes."""
    resultado = await reintentar_pendientes(db)
    return ReintentoResponse(**resultado)
