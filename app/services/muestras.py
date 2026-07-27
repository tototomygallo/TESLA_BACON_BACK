from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Consecutivo, EstadoMuestra, Muestra, Discrepancia, MuestraAuditoria
from app.services import bacon
from app.services.auditoria import registrar_auditoria
from app.services.estudios import (
    TIPO_LACTOKIT,
    codigo_estudio_para_tipo,
    nombre_estudio_para_tipo,
    tipo_estudio_desde_codigo,
)

import smtplib
import json
from email.message import EmailMessage

ACCION_MARCAR_MAL_ANULADO = "marcar_mal_anulado"
ACCION_OPERACION_REVERTIR_EN_PROCESO = "operacion_revertir_a_en_proceso"
ACCION_VALORES_CORREGIDOS = "valores_corregidos"
ACCION_INFORME_REGENERADO = "informe_regenerado"

def _enviar_informe_por_mail(
    muestra: Muestra, pdf_bytes: bytes, *, asunto: str | None = None
) -> str | None:
    """Envía el informe en PDF por mail a BACON.

    No interrumpe el flujo si falla. Devuelve None si el envío fue exitoso,
    o un mensaje de advertencia describiendo el error si falló.
    """
    settings = get_settings()
    try:
        msg = EmailMessage()
        msg["Subject"] = asunto or f"Informe TauKit {muestra.codigo_taukit}"
        msg["From"] = settings.smtp_from_email
        msg["To"] = settings.bacon_contact_email

        msg.set_content(
            f"""
Se adjunta el informe generado.

Protocolo: {muestra.protocolo}
TauKit: {muestra.codigo_taukit}

Paciente: {muestra.paciente_apellido} {muestra.paciente_nombre}
"""
        )

        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"{muestra.codigo_taukit}.pdf",
        )

        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)

        print(f"[MAIL] Informe enviado para {muestra.codigo_taukit}")
        return None

    except Exception as e:
        print(f"[MAIL] Error enviando informe {muestra.codigo_taukit}: {e}")
        return f"El informe se subió y verificó en BACON, pero el envío por mail falló: {e}"


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


async def ingresar_lote(db: Session, codigos: list[str], usuario_id: str | None = None) -> dict:
    settings = get_settings()
    ingresadas: list[Muestra] = []
    rechazadas: list[str] = []
    duplicadas: list[str] = []

    try:
        bacon_muestras = await bacon.obtener_muestras_enviadas()
    except Exception as e:
        db.rollback()
        raise ValueError(f"No se pudo consultar BACON: {e}")

    bacon_por_serie = {m["numero_serie"]: m for m in bacon_muestras}
    ahora = datetime.now()

    for codigo_raw in codigos:
        codigo = codigo_raw.strip().upper()
        try:
            tipo_estudio = tipo_estudio_desde_codigo(codigo)
        except ValueError:
            rechazadas.append(codigo)
            continue
        
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
            datos_bacon_existente = bacon_por_serie.get(codigo) or {}
            fecha_carga_bacon = datos_bacon_existente.get("fecha_carga") or ""
            if fecha_carga_bacon and not muestra_existente.fecha_toma_muestra:
                muestra_existente.fecha_toma_muestra = fecha_carga_bacon
            # Ya estaba ingresado y BACON ya lo tiene como recibido -> duplicado.
            # No se reprocesa ni se vuelve a llamar a cambiarEstadoRecibido (daría 400).
            if muestra_existente.bacon_recibido:
                duplicadas.append(codigo)
                continue
            estado_anterior = muestra_existente.estado
            muestra_existente.estado = "recibido"
            if not muestra_existente.tipo_estudio:
                muestra_existente.tipo_estudio = tipo_estudio
            registrar_auditoria(
                db,
                accion="reingreso_lote",
                muestra=muestra_existente,
                usuario_id=usuario_id,
                estado_anterior=estado_anterior,
                estado_nuevo=muestra_existente.estado,
                detalle="Muestra existente reingresada desde lote",
                datos={"fecha_carga_bacon": fecha_carga_bacon},
            )

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

        estudio_codigo = codigo_estudio_para_tipo(tipo_estudio)
        estudio_nombre = nombre_estudio_para_tipo(tipo_estudio)
        consecutivo = _siguiente_consecutivo(db, estudio_codigo)
        protocolo = _generar_protocolo(settings.sucursal_codigo, estudio_codigo, consecutivo)

        muestra = Muestra(
            protocolo=protocolo, codigo_taukit=codigo,
            tipo_estudio=tipo_estudio,
            paciente_nombre=nombre, paciente_apellido=apellido,
            paciente_dni=paciente.get("documento") or "",
            fecha_toma_muestra=datos_bacon.get("fecha_carga") or "",
            estudio_codigo=estudio_codigo, estudio_nombre=estudio_nombre,
            sucursal_codigo=settings.sucursal_codigo, sucursal_nombre=settings.sucursal_nombre,
            estado="recibido", fecha_ingreso=ahora,
        )
        db.add(muestra)
        registrar_auditoria(
            db,
            accion="ingreso_lote",
            muestra=muestra,
            usuario_id=usuario_id,
            estado_anterior=None,
            estado_nuevo=muestra.estado,
            detalle="Muestra ingresada desde lote",
            datos={
                "codigo_recibido": codigo,
                "fecha_carga_bacon": datos_bacon.get("fecha_carga") or "",
            },
        )
        ingresadas.append(muestra)

    if rechazadas:
        for c in rechazadas:
            db.add(Discrepancia(codigo=c, motivo="No figura como enviado en BACON", fecha=ahora))
            registrar_auditoria(
                db,
                accion="ingreso_rechazado",
                usuario_id=usuario_id,
                codigo=c,
                detalle="No figura como enviado en BACON",
            )

    # BACON es parte obligatoria del ingreso: si falla, no se confirma nada local.
    # Excepción: si BACON responde 400 porque el TauKit YA está recibido, se trata como
    # duplicado y no se aborta el lote (el resto se ingresa normal).
    for muestra in list(ingresadas):
        resultado = await bacon.marcar_recibido_en_bacon(muestra.codigo_taukit)

        if resultado and resultado.get("success") is True:
            muestra.bacon_recibido = True
            registrar_auditoria(
                db,
                accion="bacon_recibido_notificado",
                muestra=muestra,
                usuario_id="sistema",
                detalle="BACON fue notificado como recibido",
                datos=resultado,
            )
            continue

        # El TauKit ya estaba recibido en BACON (400): es un duplicado, no un error.
        if isinstance(resultado, dict) and resultado.get("status") == 400:
            ingresadas.remove(muestra)
            duplicadas.append(muestra.codigo_taukit)
            muestra.bacon_recibido = True
            registrar_auditoria(
                db,
                accion="ingreso_duplicado",
                muestra=muestra,
                usuario_id=usuario_id,
                detalle="El TauKit ya estaba recibido en BACON: se reporta como duplicado",
                datos=resultado,
            )
            continue

        # Cualquier otro fallo de BACON sigue siendo bloqueante para todo el lote.
        if isinstance(resultado, dict):
            detalle_bacon = (
                resultado.get("error")
                or resultado.get("message")
                or resultado.get("mensaje")
                or "BACON no devolvio success=true"
            )
        else:
            detalle_bacon = "BACON no devolvio una respuesta valida"
        db.rollback()
        raise ValueError(
            f"No se pudo cambiar el estado en BACON para {muestra.codigo_taukit}: {detalle_bacon}"
        )
    db.commit()

    return {"ingresadas": ingresadas, "rechazadas": rechazadas, "duplicadas": duplicadas}


def _marcar_pdf_enviado(muestra: Muestra, verificacion_bacon: dict) -> None:
    """Marca en la muestra que el PDF fue generado, subido y verificado en BACON."""
    muestra.bacon_pdf_enviado = True
    muestra.pdf_generado = True
    muestra.pdf_generado_en = datetime.now()


def _limpiar_resultados_taukit(muestra: Muestra) -> None:
    muestra.resultado_basal_co2 = None
    muestra.resultado_post_co2 = None
    muestra.resultado_basal_delta = None
    muestra.resultado_post_delta = None
    muestra.resultado_test_value = None
    muestra.resultado_cargado_en = None
    muestra.pdf_generado = False
    muestra.pdf_generado_en = None
    muestra.bacon_pdf_enviado = False


async def _subir_informe_a_bacon(
    muestra: Muestra, *, validacion_clinica: bool, sin_restriccion: bool = False
) -> tuple[dict, dict, bytes]:
    """Genera el PDF, lo sube a BACON y verifica la subida.

    Devuelve (resultado_subida, verificacion, pdf_bytes).
    Lanza ValueError si BACON rechaza el PDF o no se puede verificar; el caller
    decide si eso corta el flujo (validar) o solo se registra (anulación en lote).
    """
    from app.services.pdf_generator import generar_informe_pdf

    pdf_bytes = generar_informe_pdf(muestra, validacion_clinica=validacion_clinica)

    if sin_restriccion:
        resultado_bacon = await bacon.subir_pdf_sin_restriccion_a_bacon(
            muestra.codigo_taukit, pdf_bytes
        )
    else:
        resultado_bacon = await bacon.subir_pdf_a_bacon(muestra.codigo_taukit, pdf_bytes)
    if isinstance(resultado_bacon, dict) and resultado_bacon.get("success") is False:
        detalle_bacon = resultado_bacon.get("error") or "BACON rechazo el PDF"
        raise ValueError(f"No se pudo subir el PDF a BACON: {detalle_bacon}")

    verificacion_bacon = await bacon.verificar_pdf_en_bacon(muestra.codigo_taukit)
    if not verificacion_bacon or verificacion_bacon.get("success") is not True:
        detalle_bacon = (
            verificacion_bacon.get("error")
            if isinstance(verificacion_bacon, dict)
            else "BACON no devolvio una verificacion valida"
        )
        raise ValueError(f"El PDF fue enviado pero no pudo verificarse en BACON: {detalle_bacon}")

    return resultado_bacon, verificacion_bacon, pdf_bytes


async def _enviar_informe_anulada(muestra: Muestra) -> dict:
    """Envía a BACON el informe 'sin validación clínica' de una muestra anulada.

    Mismo flujo que una validada (subir PDF + verificar + mail), pero TOLERANTE a
    fallos: nunca lanza. Si la muestra no tiene resultados para el informe, también
    devuelve enviado=False. Un fallo de envío nunca debe cortar el flujo que la anuló.
    """
    try:
        _resultado, verificacion_bacon, pdf_bytes = await _subir_informe_a_bacon(
            muestra, validacion_clinica=False
        )
    except Exception as exc:  # noqa: BLE001 - un fallo de envío nunca debe cortar el flujo
        print(f"[ANULADA] No se pudo enviar a BACON {muestra.protocolo}: {exc}")
        return {"enviado": False, "error": str(exc)}

    advertencia_mail = _enviar_informe_por_mail(muestra, pdf_bytes)
    _marcar_pdf_enviado(muestra, verificacion_bacon)
    return {
        "enviado": True,
        "mail_enviado": advertencia_mail is None,
        "mail_advertencia": advertencia_mail,
    }


async def validar_muestra(
    db: Session, protocolo: str, usuario_id: str | None = None
) -> tuple[Muestra, str | None]:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != "en_validacion":
        raise ValueError("Solo se pueden validar muestras en estado 'En validación'")
    if muestra.intentos_fallidos >= 2:
        raise ValueError("No es posible generar el informe requerido con esta muestra")

    # Generar + subir + verificar el PDF en BACON (lanza si BACON rechaza o no verifica).
    resultado_bacon, verificacion_bacon, pdf_bytes = await _subir_informe_a_bacon(
        muestra, validacion_clinica=True
    )

    # Una vez verificada la subida en BACON, se envía el informe por mail.
    advertencia_mail = _enviar_informe_por_mail(muestra, pdf_bytes)

    estado_anterior = muestra.estado
    _marcar_pdf_enviado(muestra, verificacion_bacon)

    # Marcar como completado en nuestro sistema
    muestra.estado = "completado"
    muestra.tiene_error = False
    registrar_auditoria(
        db,
        accion="validacion_bioquimica",
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Muestra validada, PDF generado y subido a BACON",
        datos={
            "subida_pdf": resultado_bacon,
            "verificacion_pdf": verificacion_bacon,
            "mail_enviado": advertencia_mail is None,
            "mail_advertencia": advertencia_mail,
        },
    )
    db.commit()
    return muestra, advertencia_mail


async def reiniciar_muestra(
    db: Session, protocolo: str, usuario_id: str | None = None
) -> tuple[Muestra, str | None]:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado == EstadoMuestra.eliminado:
        raise ValueError("La muestra fue eliminada por administración")
    if muestra.estado in (
        EstadoMuestra.anulado,
        EstadoMuestra.cancelado,
        EstadoMuestra.pendiente_anulacion,
    ):
        raise ValueError("La muestra está anulada: el TauKit agotó sus 2 mediciones")
    if muestra.estado == "completado":
        raise ValueError("No se puede reiniciar una muestra completada")
    if muestra.estado == "recibido":
        raise ValueError("La muestra todavía no fue procesada")

    estado_anterior = muestra.estado
    intentos_anteriores = muestra.intentos_fallidos

    # Cada reinicio consume una medición del TauKit (igual que un error de equipo).
    muestra.intentos_fallidos += 1

    if muestra.intentos_fallidos >= 2:
        # Se agotaron las 2 mediciones del TauKit. No se informa a BACON hasta que
        # el usuario confirme la anulacion.
        muestra.estado = EstadoMuestra.pendiente_anulacion
        muestra.tiene_error = True
        registrar_auditoria(
            db,
            accion="reinicio_pendiente_anulacion",
            muestra=muestra,
            usuario_id=usuario_id,
            estado_anterior=estado_anterior,
            estado_nuevo=muestra.estado,
            detalle="El reinicio agoto las 2 mediciones del TauKit: pendiente de anulacion",
            datos={
                "intentos_anteriores": intentos_anteriores,
                "intentos_nuevos": muestra.intentos_fallidos,
                "consume_intento": True,
                "envio_bacon": False,
            },
        )
        db.commit()
        return muestra, None

    # Reinicio normal: queda lista para una nueva medición/carga.
    muestra.estado = "en_proceso"
    muestra.tiene_error = False
    _limpiar_resultados_taukit(muestra)
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        from app.models import LactokitResultado
        db.query(LactokitResultado).filter_by(protocolo=protocolo).delete()
    registrar_auditoria(
        db,
        accion="reinicio_muestra",
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Muestra reiniciada para nueva medicion/carga",
        datos={
            "intentos_anteriores": intentos_anteriores,
            "intentos_nuevos": muestra.intentos_fallidos,
            "consume_intento": True,
        },
    )
    db.commit()
    return muestra, None


def listar_pendientes_anulacion(db: Session) -> list[Muestra]:
    derivada_a_revision = (
        db.query(MuestraAuditoria.id)
        .filter(
            MuestraAuditoria.protocolo == Muestra.protocolo,
            MuestraAuditoria.accion == ACCION_MARCAR_MAL_ANULADO,
        )
        .exists()
    )
    return (
        db.query(Muestra)
        .filter(
            Muestra.estado == EstadoMuestra.pendiente_anulacion,
            Muestra.bacon_pdf_enviado == False,  # noqa: E712
            Muestra.tipo_estudio != TIPO_LACTOKIT,
            ~derivada_a_revision,
        )
        .order_by(Muestra.updated_at.desc(), Muestra.fecha_ingreso.desc())
        .all()
    )


def _json_auditoria(datos: str | None) -> dict:
    if not datos:
        return {}
    try:
        parsed = json.loads(datos)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ultima_marca_mal_anulado(db: Session, protocolo: str) -> MuestraAuditoria | None:
    return (
        db.query(MuestraAuditoria)
        .filter(
            MuestraAuditoria.protocolo == protocolo,
            MuestraAuditoria.accion == ACCION_MARCAR_MAL_ANULADO,
        )
        .order_by(MuestraAuditoria.fecha.desc(), MuestraAuditoria.id.desc())
        .first()
    )


def marcar_mal_anulado(
    db: Session,
    protocolo: str,
    *,
    motivo: str,
    detalle: str | None = None,
    usuario_id: str | None = None,
    usuario_id_body: str | None = None,
) -> Muestra:
    motivo_limpio = motivo.strip()
    detalle_limpio = (detalle or "").strip() or None
    if motivo_limpio not in ("Error en la carga de resultados", "Otro"):
        raise ValueError("El motivo debe ser 'Error en la carga de resultados' u 'Otro'")
    if motivo_limpio == "Otro" and not detalle_limpio:
        raise ValueError("El detalle es obligatorio cuando el motivo es 'Otro'")

    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != EstadoMuestra.pendiente_anulacion or muestra.bacon_pdf_enviado:
        raise ValueError("Solo se pueden marcar como mal anuladas muestras pendientes no informadas a BACON")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        raise ValueError("La marca de mal anulado aplica solo a Taukit")

    registrar_auditoria(
        db,
        accion=ACCION_MARCAR_MAL_ANULADO,
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=muestra.estado,
        estado_nuevo=muestra.estado,
        detalle=motivo_limpio,
        datos={
            "motivo": motivo_limpio,
            "detalle": detalle_limpio,
            "usuario_marca": usuario_id,
            "usuario_id_body": usuario_id_body,
            "fecha_marca": datetime.now().isoformat(timespec="seconds"),
            "envio_bacon": False,
        },
    )
    db.commit()
    return muestra


def listar_mal_anulados_pendientes_revision(db: Session) -> list[dict]:
    filas = (
        db.query(MuestraAuditoria, Muestra)
        .join(Muestra, MuestraAuditoria.protocolo == Muestra.protocolo)
        .filter(
            MuestraAuditoria.accion == ACCION_MARCAR_MAL_ANULADO,
            Muestra.estado == EstadoMuestra.pendiente_anulacion,
            Muestra.bacon_pdf_enviado == False,  # noqa: E712
        )
        .order_by(MuestraAuditoria.fecha.desc(), MuestraAuditoria.id.desc())
        .all()
    )

    protocolos_vistos: set[str] = set()
    pendientes: list[dict] = []
    for auditoria, muestra in filas:
        if muestra.protocolo in protocolos_vistos:
            continue
        protocolos_vistos.add(muestra.protocolo)

        datos = _json_auditoria(auditoria.datos)
        pendientes.append(
            {
                "numeroSerie": muestra.codigo_taukit,
                "protocolo": muestra.protocolo,
                "paciente": {
                    "nombre": muestra.paciente_nombre,
                    "apellido": muestra.paciente_apellido,
                    "dni": muestra.paciente_dni,
                    "fechaTomaMuestra": muestra.fecha_toma_muestra,
                },
                "estado": muestra.estado,
                "motivo": datos.get("motivo") or auditoria.detalle or "",
                "detalle": datos.get("detalle"),
                "usuarioId": auditoria.usuario_id or datos.get("usuario_marca") or "",
                "fecha": auditoria.fecha.strftime("%Y-%m-%d %H:%M:%S") if auditoria.fecha else "",
                "tipoEstudio": muestra.tipo_estudio or "taukit",
                "intentosFallidos": muestra.intentos_fallidos,
            }
        )
    return pendientes


def _resultado_taukit_dict(muestra: Muestra) -> dict | None:
    if (
        muestra.resultado_basal_co2 is None
        or muestra.resultado_post_co2 is None
        or muestra.resultado_basal_delta is None
        or muestra.resultado_post_delta is None
        or muestra.resultado_test_value is None
    ):
        return None
    return {
        "basalCO2": muestra.resultado_basal_co2,
        "postCO2": muestra.resultado_post_co2,
        "basalDelta": muestra.resultado_basal_delta,
        "postDelta": muestra.resultado_post_delta,
        "testValue": muestra.resultado_test_value,
        "cargadoEn": muestra.resultado_cargado_en,
    }


def _ultima_auditoria_accion(
    db: Session, protocolo: str, accion: str
) -> MuestraAuditoria | None:
    return (
        db.query(MuestraAuditoria)
        .filter(MuestraAuditoria.protocolo == protocolo, MuestraAuditoria.accion == accion)
        .order_by(MuestraAuditoria.fecha.desc(), MuestraAuditoria.id.desc())
        .first()
    )


def _tiene_correccion_pendiente_informe(db: Session, protocolo: str) -> bool:
    valores = _ultima_auditoria_accion(db, protocolo, ACCION_VALORES_CORREGIDOS)
    if not valores:
        return False
    informe = _ultima_auditoria_accion(db, protocolo, ACCION_INFORME_REGENERADO)
    if not informe:
        return True
    if valores.fecha and informe.fecha and valores.fecha != informe.fecha:
        return valores.fecha > informe.fecha
    return valores.id > informe.id


def listar_completados_para_correccion(db: Session, q: str | None = None) -> list[dict]:
    query = db.query(Muestra).filter(
        Muestra.estado == EstadoMuestra.completado,
        Muestra.tipo_estudio != TIPO_LACTOKIT,
    )

    termino = (q or "").strip()
    if termino:
        like = f"%{termino}%"
        filtros = [
            Muestra.codigo_taukit.like(like),
            Muestra.protocolo.like(like),
            Muestra.paciente_nombre.like(like),
            Muestra.paciente_apellido.like(like),
            Muestra.paciente_dni.like(like),
            (Muestra.paciente_nombre + " " + Muestra.paciente_apellido).like(like),
            (Muestra.paciente_apellido + " " + Muestra.paciente_nombre).like(like),
        ]
        try:
            filtros.append(Muestra.resultado_test_value == float(termino.replace(",", ".")))
        except ValueError:
            pass
        query = query.filter(or_(*filtros))

    filas = query.order_by(Muestra.pdf_generado_en.desc(), Muestra.fecha_ingreso.desc()).limit(50).all()
    respuesta: list[dict] = []
    for muestra in filas:
        resultado = _resultado_taukit_dict(muestra)
        respuesta.append(
            {
                "numeroSerie": muestra.codigo_taukit,
                "protocolo": muestra.protocolo,
                "paciente": {
                    "nombre": muestra.paciente_nombre,
                    "apellido": muestra.paciente_apellido,
                    "dni": muestra.paciente_dni,
                    "fechaTomaMuestra": muestra.fecha_toma_muestra,
                },
                "estado": muestra.estado,
                "fechaInforme": muestra.pdf_generado_en.strftime("%Y-%m-%d %H:%M:%S")
                if muestra.pdf_generado_en
                else "",
                "resultados": resultado,
            }
        )
    return respuesta


def cargar_valores_correccion_completado(
    db: Session,
    protocolo: str,
    *,
    basal_co2: float,
    post_co2: float,
    basal_delta: float,
    post_delta: float,
    test_value: float,
    usuario_id: str | None = None,
    usuario_id_body: str | None = None,
) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        raise ValueError("La correccion de completados aplica solo a Taukit")
    if muestra.estado != EstadoMuestra.completado:
        raise ValueError("Solo se pueden corregir muestras Taukit completadas")

    valores_anteriores = _resultado_taukit_dict(muestra)
    valores_nuevos = {
        "basalCO2": basal_co2,
        "postCO2": post_co2,
        "basalDelta": basal_delta,
        "postDelta": post_delta,
        "testValue": test_value,
    }
    ahora = datetime.now()
    muestra.resultado_basal_co2 = basal_co2
    muestra.resultado_post_co2 = post_co2
    muestra.resultado_basal_delta = basal_delta
    muestra.resultado_post_delta = post_delta
    muestra.resultado_test_value = test_value
    muestra.resultado_cargado_en = ahora.strftime("%Y-%m-%d %H:%M")
    muestra.pdf_generado = False
    muestra.pdf_generado_en = None
    muestra.bacon_pdf_enviado = False
    muestra.tiene_error = False

    registrar_auditoria(
        db,
        accion=ACCION_VALORES_CORREGIDOS,
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=muestra.estado,
        estado_nuevo=muestra.estado,
        detalle="Valores de muestra completada corregidos desde Operacion",
        datos={
            "fecha_correccion": ahora.isoformat(timespec="seconds"),
            "usuario_id_body": usuario_id_body,
            "valores_anteriores": valores_anteriores,
            "valores_nuevos": valores_nuevos,
            "envio_bacon": False,
        },
    )
    db.commit()
    return muestra


async def generar_informe_correccion_completado(
    db: Session,
    protocolo: str,
    *,
    usuario_id: str | None = None,
    usuario_id_body: str | None = None,
) -> tuple[Muestra, str | None, dict]:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        raise ValueError("La correccion de completados aplica solo a Taukit")
    if muestra.estado != EstadoMuestra.completado:
        raise ValueError("Solo se puede regenerar informe de muestras Taukit completadas")
    if not _tiene_correccion_pendiente_informe(db, protocolo):
        raise ValueError("Primero deben cargarse valores corregidos")
    if muestra.resultado_test_value is None:
        raise ValueError("La muestra no tiene resultados corregidos cargados")

    estado_anterior = muestra.estado
    resultado_bacon, verificacion_bacon, pdf_bytes = await _subir_informe_a_bacon(
        muestra, validacion_clinica=True, sin_restriccion=True
    )
    advertencia_mail = _enviar_informe_por_mail(
        muestra,
        pdf_bytes,
        asunto=f"Reenvio Informe TauKit {muestra.codigo_taukit}",
    )
    _marcar_pdf_enviado(muestra, verificacion_bacon)
    muestra.estado = EstadoMuestra.completado
    muestra.tiene_error = False
    registrar_auditoria(
        db,
        accion=ACCION_INFORME_REGENERADO,
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Informe corregido regenerado y subido a BACON",
        datos={
            "fecha_regeneracion": datetime.now().isoformat(timespec="seconds"),
            "usuario_id_body": usuario_id_body,
            "valores": _resultado_taukit_dict(muestra),
            "endpoint_bacon": "subirPDFSinRestriccion",
            "subida_pdf": resultado_bacon,
            "verificacion_pdf": verificacion_bacon,
            "mail_enviado": advertencia_mail is None,
            "mail_advertencia": advertencia_mail,
        },
    )
    db.commit()
    return muestra, advertencia_mail, verificacion_bacon


async def confirmar_anulacion(
    db: Session, protocolo: str, usuario_id: str | None = None
) -> tuple[Muestra, str | None]:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != EstadoMuestra.pendiente_anulacion:
        raise ValueError("Solo se pueden confirmar muestras pendientes de anulacion")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        raise ValueError("La confirmacion de anulacion aplica solo a Taukit")
    if muestra.bacon_pdf_enviado:
        raise ValueError("La anulacion ya fue informada a BACON")

    estado_anterior = muestra.estado
    muestra.estado = EstadoMuestra.anulado
    muestra.tiene_error = True

    try:
        resultado_bacon, verificacion_bacon, pdf_bytes = await _subir_informe_a_bacon(
            muestra, validacion_clinica=False
        )
    except Exception:
        db.rollback()
        raise

    advertencia_mail = _enviar_informe_por_mail(muestra, pdf_bytes)
    _marcar_pdf_enviado(muestra, verificacion_bacon)
    registrar_auditoria(
        db,
        accion="confirmar_anulacion",
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Anulacion Taukit confirmada, PDF generado y subido a BACON",
        datos={
            "fecha_confirmacion": datetime.now().isoformat(timespec="seconds"),
            "subida_pdf": resultado_bacon,
            "verificacion_pdf": verificacion_bacon,
            "mail_enviado": advertencia_mail is None,
            "mail_advertencia": advertencia_mail,
        },
    )
    db.commit()
    return muestra, advertencia_mail


def revertir_anulacion(
    db: Session, protocolo: str, motivo: str, usuario_id: str | None = None
) -> Muestra:
    raise ValueError(
        "La reversiÃ³n directa fue reemplazada por el flujo de revisiÃ³n administrativa. "
        "Use marcar-mal-anulado y luego revertir desde OperaciÃ³n."
    )


def revertir_mal_anulado_a_en_proceso(
    db: Session, protocolo: str, usuario_id: str | None = None
) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if (
        muestra.estado != EstadoMuestra.pendiente_anulacion
        or muestra.bacon_pdf_enviado
    ):
        raise ValueError(
            "No se puede revertir esta muestra porque la anulacion ya fue confirmada o informada a BACON."
        )
    marca = _ultima_marca_mal_anulado(db, protocolo)
    if not marca:
        raise ValueError("Solo se puede revertir una muestra marcada como mal anulada y pendiente de revisiÃ³n")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        raise ValueError("La reversion de anulacion aplica solo a Taukit")

    datos_marca = _json_auditoria(marca.datos)
    estado_anterior = muestra.estado
    intentos_anteriores = muestra.intentos_fallidos
    _limpiar_resultados_taukit(muestra)
    muestra.estado = EstadoMuestra.en_proceso
    muestra.tiene_error = False
    muestra.intentos_fallidos = 1
    registrar_auditoria(
        db,
        accion=ACCION_OPERACION_REVERTIR_EN_PROCESO,
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Anulacion Taukit pendiente revertida desde Operacion",
        datos={
            "motivo": datos_marca.get("motivo"),
            "detalle": datos_marca.get("detalle"),
            "usuario_marca": marca.usuario_id,
            "fecha_marca": marca.fecha.isoformat(timespec="seconds") if marca.fecha else None,
            "fecha_reversion": datetime.now().isoformat(timespec="seconds"),
            "intentos_anteriores": intentos_anteriores,
            "intentos_nuevos": muestra.intentos_fallidos,
            "envio_bacon": False,
        },
    )
    db.commit()
    return muestra


def imprimir_etiquetas(db: Session, protocolo: str, usuario_id: str | None = None) -> Muestra:
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.estado != "recibido":
        return muestra
    estado_anterior = muestra.estado
    muestra.estado = "en_proceso"
    registrar_auditoria(
        db,
        accion="impresion_etiquetas",
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle="Impresion de etiquetas / inicio de proceso",
    )
    db.commit()
    return muestra
