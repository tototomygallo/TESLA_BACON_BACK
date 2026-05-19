from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.models import EstadoMuestra, Muestra
from app.schemas import ResumenDiarioSchema

router = APIRouter(prefix="/resumen", tags=["Resumen"])


@router.get("/historial", response_model=list[ResumenDiarioSchema])
def historial(db: Session = Depends(get_db)):
    """Devuelve resumen diario de los últimos 14 días."""
    hoy = datetime.now().date()
    resultados = []

    for i in range(14):
        fecha = hoy - timedelta(days=i)
        fecha_str = fecha.isoformat()

        muestras_dia = (
            db.query(
                func.count(Muestra.protocolo).label("total"),
                func.sum(
                    case(
                        (Muestra.estado.in_([EstadoMuestra.en_validacion, EstadoMuestra.completado]), 1),
                        else_=0,
                    )
                ).label("procesadas"),
                func.sum(
                    case(
                        (Muestra.estado == EstadoMuestra.completado, 1),
                        else_=0,
                    )
                ).label("finalizadas"),
                func.sum(
                    case(
                        (Muestra.estado != EstadoMuestra.completado, 1),
                        else_=0,
                    )
                ).label("pendientes"),
            )
            .filter(func.date(Muestra.fecha_ingreso) == fecha)
            .first()
        )

        total = muestras_dia.total or 0
        resultados.append(
            ResumenDiarioSchema(
                fecha=fecha_str,
                ingresadas=total,
                procesadas=int(muestras_dia.procesadas or 0),
                finalizadas=int(muestras_dia.finalizadas or 0),
                pendientes=int(muestras_dia.pendientes or 0),
                discrepancias=0,  # TODO: registrar discrepancias en una tabla aparte
            )
        )

    return resultados


@router.get("/{fecha}", response_model=ResumenDiarioSchema)
def resumen_fecha(fecha: str, db: Session = Depends(get_db)):
    """Devuelve el resumen de una fecha específica (YYYY-MM-DD)."""
    muestras_dia = (
        db.query(
            func.count(Muestra.protocolo).label("total"),
            func.sum(
                case(
                    (Muestra.estado.in_([EstadoMuestra.en_validacion, EstadoMuestra.completado]), 1),
                    else_=0,
                )
            ).label("procesadas"),
            func.sum(
                case(
                    (Muestra.estado == EstadoMuestra.completado, 1),
                    else_=0,
                )
            ).label("finalizadas"),
            func.sum(
                case(
                    (Muestra.estado != EstadoMuestra.completado, 1),
                    else_=0,
                )
            ).label("pendientes"),
        )
        .filter(func.date(Muestra.fecha_ingreso) == fecha)
        .first()
    )

    return ResumenDiarioSchema(
        fecha=fecha,
        ingresadas=muestras_dia.total or 0,
        procesadas=int(muestras_dia.procesadas or 0),
        finalizadas=int(muestras_dia.finalizadas or 0),
        pendientes=int(muestras_dia.pendientes or 0),
        discrepancias=0,
    )
