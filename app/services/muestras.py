from datetime import datetime
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Consecutivo, EstadoMuestra, Muestra, Discrepancia
from app.services import bacon
from app.services.auditoria import registrar_auditoria
from app.services.estudios import (
    TIPO_LACTOKIT,
    codigo_estudio_para_tipo,
    nombre_estudio_para_tipo,
    tipo_estudio_desde_codigo,
)

import smtplib
from email.message import EmailMessage

def _enviar_informe_por_mail(muestra: Muestra, pdf_bytes: bytes) -> str | None:
    """Envía el informe en PDF por mail a BACON.

    No interrumpe el flujo si falla. Devuelve None si el envío fue exitoso,
    o un mensaje de advertencia describiendo el error si falló.
    """
    settings = get_settings()
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Informe TauKit {muestra.codigo_taukit}"
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
            # Ya estaba ingresado y BACON ya lo tiene como recibido -> duplicado.
            # No se reprocesa ni se vuelve a llamar a cambiarEstadoRecibido (daría 400).
            if muestra_existente.bacon_recibido:
                duplicadas.append(codigo)
                continue
            estado_anterior = muestra_existente.estado
            muestra_existente.estado = "recibido"
            muestra_existente.fecha_ingreso = ahora
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
            fecha_toma_muestra="",
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
            datos={"codigo_recibido": codigo},
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
    muestra.pdf_verificado_bacon = True
    muestra.pdf_verificacion_bacon = verificacion_bacon


async def _subir_informe_a_bacon(
    muestra: Muestra, *, validacion_clinica: bool
) -> tuple[dict, dict, bytes]:
    """Genera el PDF, lo sube a BACON y verifica la subida.

    Devuelve (resultado_subida, verificacion, pdf_bytes).
    Lanza ValueError si BACON rechaza el PDF o no se puede verificar; el caller
    decide si eso corta el flujo (validar) o solo se registra (anulación en lote).
    """
    from app.services.pdf_generator import generar_informe_pdf

    pdf_bytes = generar_informe_pdf(muestra, validacion_clinica=validacion_clinica)

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
    if muestra.estado in (EstadoMuestra.anulado, EstadoMuestra.cancelado):
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
        # Se agotaron las 2 mediciones del TauKit -> anular. Se conservan los últimos
        # resultados cargados para poder emitir el informe, que se envía a BACON igual
        # que cualquier otra anulada (informe sin validación clínica).
        muestra.estado = EstadoMuestra.anulado
        muestra.tiene_error = True
        envio_anulada = await _enviar_informe_anulada(muestra)
        registrar_auditoria(
            db,
            accion="reinicio_agota_taukit",
            muestra=muestra,
            usuario_id=usuario_id,
            estado_anterior=estado_anterior,
            estado_nuevo=muestra.estado,
            detalle="El reinicio agotó las 2 mediciones del TauKit: muestra anulada",
            datos={
                "intentos_anteriores": intentos_anteriores,
                "intentos_nuevos": muestra.intentos_fallidos,
                "consume_intento": True,
                "envio_anulada": envio_anulada,
            },
        )
        db.commit()
        # advertencia = detalle solo si el informe se subió/verificó en BACON pero el
        # mail falló (mismo contrato que validar_muestra). None en cualquier otro caso.
        advertencia = envio_anulada.get("mail_advertencia")
        return muestra, advertencia

    # Reinicio normal: queda lista para una nueva medición/carga.
    muestra.estado = "en_proceso"
    muestra.tiene_error = False
    muestra.resultado_basal_co2 = None
    muestra.resultado_post_co2 = None
    muestra.resultado_basal_delta = None
    muestra.resultado_post_delta = None
    muestra.resultado_test_value = None
    muestra.resultado_cargado_en = None
    muestra.pdf_generado = False
    muestra.pdf_generado_en = None
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
