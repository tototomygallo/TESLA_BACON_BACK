from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Discrepancia, EstadoMuestra, Muestra, Usuario
from app.schemas import DiscrepanciaSchema, ResumenDiarioSchema

router = APIRouter(prefix="/resumen", tags=["Resumen"])


def _format_fecha(fecha: datetime | None) -> str:
    if not fecha:
        return ""
    return fecha.strftime("%Y-%m-%d %H:%M")


def _rango_dia(fecha: str) -> tuple[datetime, datetime]:
    try:
        inicio = datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="La fecha debe tener formato YYYY-MM-DD")
    return inicio, inicio + timedelta(days=1)


def _discrepancias_por_fecha(db: Session, fecha: str) -> list[DiscrepanciaSchema]:
    inicio, fin = _rango_dia(fecha)
    discrepancias = (
        db.query(Discrepancia)
        .filter(Discrepancia.fecha >= inicio, Discrepancia.fecha < fin)
        .order_by(Discrepancia.fecha.asc())
        .all()
    )
    return [
        DiscrepanciaSchema(
            codigo=discrepancia.codigo,
            fecha=_format_fecha(discrepancia.fecha),
            motivo=discrepancia.motivo,
        )
        for discrepancia in discrepancias
    ]


@router.get("/historial", response_model=list[ResumenDiarioSchema])
def historial(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Devuelve resumen diario de los últimos 14 días."""
    hoy = datetime.now().date()
    resultados = []

    for i in range(14):
        fecha = hoy - timedelta(days=i)
        fecha_str = fecha.isoformat()
        inicio, fin = _rango_dia(fecha_str)

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
            .filter(Muestra.fecha_ingreso >= inicio, Muestra.fecha_ingreso < fin)
            .first()
        )

        total = muestras_dia.total or 0
        rechazados = _discrepancias_por_fecha(db, fecha_str)
        resultados.append(
            ResumenDiarioSchema(
                fecha=fecha_str,
                ingresadas=total,
                procesadas=int(muestras_dia.procesadas or 0),
                finalizadas=int(muestras_dia.finalizadas or 0),
                pendientes=int(muestras_dia.pendientes or 0),
                discrepancias=len(rechazados),
                rechazados=rechazados,
            )
        )

    return resultados


@router.get("/{fecha}", response_model=ResumenDiarioSchema)
def resumen_fecha(
    fecha: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Devuelve el resumen de una fecha específica (YYYY-MM-DD)."""
    inicio, fin = _rango_dia(fecha)
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
        .filter(Muestra.fecha_ingreso >= inicio, Muestra.fecha_ingreso < fin)
        .first()
    )

    rechazados = _discrepancias_por_fecha(db, fecha)

    return ResumenDiarioSchema(
        fecha=fecha,
        ingresadas=muestras_dia.total or 0,
        procesadas=int(muestras_dia.procesadas or 0),
        finalizadas=int(muestras_dia.finalizadas or 0),
        pendientes=int(muestras_dia.pendientes or 0),
        discrepancias=len(rechazados),
        rechazados=rechazados,
    )
