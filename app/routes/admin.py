import smtplib
import json
from email.message import EmailMessage

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import EstadoMuestra, Muestra, MuestraAuditoria
from app.routes.configuracion import _require_admin
from app.schemas import ProtocoloEditadoSchema
from app.services.auditoria import registrar_auditoria

router = APIRouter(prefix="/admin", tags=["Administración"])


class AdminSerieDeleteRequest(BaseModel):
    motivo: str


class AdminPacienteUpdateRequest(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    dni: str | None = None
    motivo: str


def _json_auditoria(datos: str | None) -> dict:
    if not datos:
        return {}
    try:
        parsed = json.loads(datos)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.get("/protocolos-editados", response_model=list[ProtocoloEditadoSchema])
def listar_protocolos_editados(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    _require_admin(db, x_user_id)

    filas = (
        db.query(MuestraAuditoria, Muestra)
        .join(Muestra, MuestraAuditoria.protocolo == Muestra.protocolo)
        .filter(MuestraAuditoria.accion == "admin_paciente_actualizado")
        .order_by(MuestraAuditoria.fecha.desc(), MuestraAuditoria.id.desc())
        .all()
    )

    protocolos_vistos: set[str] = set()
    respuesta: list[ProtocoloEditadoSchema] = []
    for auditoria, muestra in filas:
        if auditoria.protocolo in protocolos_vistos:
            continue
        protocolos_vistos.add(auditoria.protocolo)

        datos = _json_auditoria(auditoria.datos)
        campos_editados = datos.get("campos_modificados") or []
        if not isinstance(campos_editados, list):
            campos_editados = []

        respuesta.append(
            ProtocoloEditadoSchema(
                protocolo=muestra.protocolo,
                numeroSerie=muestra.codigo_taukit,
                tipoEstudio=muestra.tipo_estudio or "taukit",
                fechaIngreso=muestra.fecha_ingreso.strftime("%Y-%m-%d %H:%M")
                if muestra.fecha_ingreso
                else "",
                fechaEdicion=auditoria.fecha.strftime("%Y-%m-%d %H:%M")
                if auditoria.fecha
                else "",
                motivo=datos.get("motivo") or auditoria.detalle or "",
                usuario=auditoria.usuario_id or "",
                camposEditados=[str(campo) for campo in campos_editados],
            )
        )

    return respuesta


def _motivo_obligatorio(motivo: str | None) -> str:
    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        raise HTTPException(status_code=422, detail="El motivo es obligatorio")
    return motivo_limpio


def _buscar_muestra_por_serie(db: Session, numero_serie: str) -> Muestra:
    muestra = db.query(Muestra).filter(Muestra.codigo_taukit == numero_serie.strip().upper()).first()
    if not muestra:
        raise HTTPException(status_code=404, detail="Numero de serie no encontrado")
    return muestra


@router.delete("/series/{numero_serie}")
def eliminar_serie(
    numero_serie: str,
    body: AdminSerieDeleteRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    _require_admin(db, x_user_id)
    motivo = _motivo_obligatorio(body.motivo)
    muestra = _buscar_muestra_por_serie(db, numero_serie)

    estado_anterior = muestra.estado
    muestra.estado = EstadoMuestra.eliminado
    muestra.tiene_error = True

    registrar_auditoria(
        db,
        accion="admin_serie_eliminada",
        muestra=muestra,
        usuario_id=x_user_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle=motivo,
        datos={
            "numero_serie": numero_serie,
            "motivo": motivo,
            "paciente_anterior": {
                "nombre": muestra.paciente_nombre,
                "apellido": muestra.paciente_apellido,
                "dni": muestra.paciente_dni,
            },
        },
    )
    db.commit()
    return {"ok": True}


@router.patch("/series/{numero_serie}/paciente")
def actualizar_paciente_serie(
    numero_serie: str,
    body: AdminPacienteUpdateRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    _require_admin(db, x_user_id)
    motivo = _motivo_obligatorio(body.motivo)
    muestra = _buscar_muestra_por_serie(db, numero_serie)

    anterior = {
        "nombre": muestra.paciente_nombre,
        "apellido": muestra.paciente_apellido,
        "dni": muestra.paciente_dni,
    }
    nuevo = {
        "nombre": muestra.paciente_nombre,
        "apellido": muestra.paciente_apellido,
        "dni": muestra.paciente_dni,
    }
    campos_modificados: list[str] = []

    if body.nombre is not None:
        nombre = body.nombre.strip()
        if not nombre:
            raise HTTPException(status_code=422, detail="El nombre no puede estar vacio")
        nuevo["nombre"] = nombre
        campos_modificados.append("nombre")

    if body.apellido is not None:
        apellido = body.apellido.strip()
        if not apellido:
            raise HTTPException(status_code=422, detail="El apellido no puede estar vacio")
        nuevo["apellido"] = apellido
        campos_modificados.append("apellido")

    if body.dni is not None:
        dni = body.dni.strip()
        if not dni:
            raise HTTPException(status_code=422, detail="El DNI no puede estar vacio")
        nuevo["dni"] = dni
        campos_modificados.append("dni")

    if not campos_modificados:
        raise HTTPException(status_code=422, detail="Debe informar al menos un campo a modificar")

    muestra.paciente_nombre = nuevo["nombre"]
    muestra.paciente_apellido = nuevo["apellido"]
    muestra.paciente_dni = nuevo["dni"]

    registrar_auditoria(
        db,
        accion="admin_paciente_actualizado",
        muestra=muestra,
        usuario_id=x_user_id,
        estado_anterior=muestra.estado,
        estado_nuevo=muestra.estado,
        detalle=motivo,
        datos={
            "numero_serie": numero_serie,
            "motivo": motivo,
            "campos_modificados": campos_modificados,
            "antes": anterior,
            "despues": nuevo,
        },
    )
    db.commit()
    return {"ok": True}


@router.post("/contacto-bacon")
async def contacto_bacon(
    asunto: str = Form(...),
    mensaje: str = Form(...),
    archivos: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    _require_admin(db, x_user_id)
    asunto_limpio = asunto.strip()
    mensaje_limpio = mensaje.strip()
    if not asunto_limpio:
        raise HTTPException(status_code=422, detail="El asunto es obligatorio")
    if not mensaje_limpio:
        raise HTTPException(status_code=422, detail="El mensaje es obligatorio")

    settings = get_settings()
    adjuntos = []
    msg = EmailMessage()
    msg["Subject"] = asunto_limpio
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = settings.bacon_contact_email
    msg.set_content(mensaje_limpio)

    for archivo in archivos or []:
        contenido = await archivo.read()
        nombre = archivo.filename or "adjunto"
        content_type = archivo.content_type or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            contenido,
            maintype=maintype,
            subtype=subtype,
            filename=nombre,
        )
        adjuntos.append({"nombre": nombre, "content_type": content_type, "bytes": len(contenido)})

    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:
        registrar_auditoria(
            db,
            accion="admin_contacto_bacon_error",
            usuario_id=x_user_id,
            tipo_estudio="admin",
            detalle="Error enviando mail a BACON",
            datos={
                "asunto": asunto_limpio,
                "mensaje_resumen": mensaje_limpio[:500],
                "adjuntos": adjuntos,
                "error": str(exc),
            },
        )
        db.commit()
        raise HTTPException(status_code=502, detail=f"No se pudo enviar el mail a BACON: {exc}")

    registrar_auditoria(
        db,
        accion="admin_contacto_bacon_enviado",
        usuario_id=x_user_id,
        tipo_estudio="admin",
        detalle="Mail enviado a BACON desde Administración",
        datos={
            "destinatario": settings.bacon_contact_email,
            "asunto": asunto_limpio,
            "mensaje_resumen": mensaje_limpio[:500],
            "adjuntos": adjuntos,
        },
    )
    db.commit()
    return {"ok": True}
