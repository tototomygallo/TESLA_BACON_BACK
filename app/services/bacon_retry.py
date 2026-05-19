"""
Servicio de reintento de notificaciones a BACON.
Busca muestras con bacon_recibido=False y reintenta la llamada.
"""
from sqlalchemy.orm import Session

from app.models import Muestra
from app.services.bacon import marcar_recibido_en_bacon


async def obtener_pendientes(db: Session) -> list[Muestra]:
    """Muestras que no pudimos notificar a BACON como recibidas."""
    return db.query(Muestra).filter_by(bacon_recibido=False).all()


async def reintentar_pendientes(db: Session) -> dict:
    """
    Reintenta notificar a BACON todas las muestras pendientes.
    Retorna {exitosos: int, fallidos: int, total: int}.
    """
    pendientes = await obtener_pendientes(db)
    exitosos = 0
    fallidos = 0

    for muestra in pendientes:
        resultado = await marcar_recibido_en_bacon(muestra.codigo_taukit)
        if resultado and resultado.get("success"):
            muestra.bacon_recibido = True
            exitosos += 1
        else:
            fallidos += 1

    db.commit()
    return {"exitosos": exitosos, "fallidos": fallidos, "total": len(pendientes)}
