import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Muestra, MuestraAuditoria


def registrar_auditoria(
    db: Session,
    *,
    accion: str,
    muestra: Muestra | None = None,
    usuario_id: str | None = None,
    protocolo: str | None = None,
    codigo: str | None = None,
    tipo_estudio: str | None = None,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
    detalle: str | None = None,
    datos: dict[str, Any] | None = None,
) -> None:
    db.add(
        MuestraAuditoria(
            protocolo=muestra.protocolo if muestra else protocolo,
            codigo=muestra.codigo_taukit if muestra else codigo,
            tipo_estudio=muestra.tipo_estudio if muestra else tipo_estudio,
            accion=accion,
            usuario_id=usuario_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            detalle=detalle,
            datos=json.dumps(datos, ensure_ascii=False) if datos else None,
        )
    )
