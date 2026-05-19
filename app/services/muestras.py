from datetime import datetime
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Consecutivo, Muestra, Discrepancia
from app.services import bacon


def _siguiente_consecutivo(db: Session, estudio_codigo: str) -> int:
    row = db.query(Consecutivo).filter_by(estudio_codigo=estudio_codigo).first()
    if not row:
        row = Consecutivo(estudio_codigo=estudio_codigo, ultimo=0)
        db.add(row)
    row.ultimo += 1
    db.flush()
    return row.ultimo


def _generar_protocolo(sucursal_codigo: str, estudio_codigo: str, consecutivo: int) -> str:
    return f"{sucursal_codigo}-{estudio_codigo}-{str(consecutivo).zfill(8)}"


def listar_muestras(db: Session) -> list[Muestra]:
    return db.query(Muestra).order_by(Muestra.fecha_ingreso.desc()).all()


async def ingresar_lote(db: Session, codigos: list[str]) -> dict:
    settings = get_settings()
    ingresadas: list[Muestra] = []
    rechazadas: list[str] = []
    duplicadas: list[str] = []

    try:
        bacon_muestras = await bacon.obtener_muestras_enviadas()
    except Exception:
        bacon_muestras = []

    bacon_por_serie = {m["numero_serie"]: m for m in bacon_muestras}
    existentes = {m.codigo_taukit for m in db.query(Muestra.codigo_taukit).all()}
    ahora = datetime.now()

    for codigo_raw in codigos:
        codigo = codigo_raw.strip().upper()
        
        """
        if codigo in existentes:
            duplicadas.append(codigo)
            continue
        """

        muestra_existente = (
            db.query(Muestra)
            .filter(Muestra.codigo_taukit == codigo)
            .first()
        )

        if muestra_existente:
            muestra_existente.estado = "recibido"
            muestra_existente.fecha_ingreso = ahora

            ingresadas.append(muestra_existente)
            continue

        datos_bacon = bacon_por_serie.get(codigo)
        if not datos_bacon:
            rechazadas.append(codigo)
            continue

        paciente = datos_bacon.get("paciente", {})
        nombre_completo = paciente.get("nombre") or ""
        partes = nombre_completo.split(" ", 1)
        apellido = partes[0] if partes else ""
        nombre = partes[1] if len(partes) > 1 else ""

        consecutivo = _siguiente_consecutivo(db, settings.estudio_codigo)
        protocolo = _generar_protocolo(settings.sucursal_codigo, settings.estudio_codigo, consecutivo)

        muestra = Muestra(
            protocolo=protocolo, codigo_taukit=codigo,
            paciente_nombre=nombre, paciente_apellido=apellido,
            paciente_dni=paciente.get("documento") or "",
            fecha_toma_muestra="",
            estudio_codigo=settings.estudio_codigo, estudio_nombre=settings.estudio_nombre,
            sucursal_codigo=settings.sucursal_codigo, sucursal_nombre=settings.sucursal_nombre,
            estado="recibido", fecha_ingreso=ahora,
        )
        db.add(muestra)
        ingresadas.append(muestra)
        existentes.add(codigo)

    if rechazadas:
        for c in rechazadas:
            db.add(Discrepancia(codigo=c, motivo="No figura como enviado en BACON", fecha=ahora))

    db.commit()

    # Notificar a BACON que los TauKits fueron recibidos.
    # Se hace después del commit para no bloquear el ingreso si BACON falla.
    for muestra in ingresadas:
        resultado = await bacon.marcar_recibido_en_bacon(muestra.codigo_taukit)
        if resultado and resultado.get("success"):
            muestra.bacon_recibido = True
    db.commit()

    return {"ingresadas": ingresadas, "rechazadas": rechazadas, "duplicadas": duplicadas}


def validar_muestra(db: Session, protocolo: str) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != "en_validacion":
        raise ValueError("Solo se pueden validar muestras en estado 'En validación'")
    if muestra.intentos_fallidos >= 2:
        raise ValueError("No es posible generar el informe requerido con esta muestra")
    muestra.estado = "completado"
    muestra.tiene_error = False
    db.commit()
    return muestra


def reiniciar_muestra(db: Session, protocolo: str) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado == "anulado":
        raise ValueError("La muestra está anulada: el TauKit agotó sus 2 mediciones")
    if muestra.estado == "completado":
        raise ValueError("No se puede reiniciar una muestra completada")
    if muestra.estado == "recibido":
        raise ValueError("La muestra todavía no fue procesada")

    muestra.intentos_fallidos += 1
    if muestra.intentos_fallidos >= 2:
        muestra.estado = "anulado"
        muestra.tiene_error = True
        db.commit()
        return muestra

    muestra.estado = "en_proceso"
    muestra.tiene_error = False
    muestra.resultado_basal_co2 = None
    muestra.resultado_post_co2 = None
    muestra.resultado_basal_delta = None
    muestra.resultado_post_delta = None
    muestra.resultado_test_value = None
    muestra.resultado_cargado_en = None
    db.commit()
    return muestra


def imprimir_etiquetas(db: Session, protocolo: str) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != "recibido":
        return muestra
    muestra.estado = "en_proceso"
    db.commit()
    return muestra
