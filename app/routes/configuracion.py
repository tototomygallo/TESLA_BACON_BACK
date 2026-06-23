from datetime import datetime
import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import MuestraAuditoria, RolUsuario, Usuario
from app.routes.auth import hash_password, validar_password_fuerte
from app.schemas import MuestraAuditoriaSchema
from app.services.auditoria import registrar_auditoria

router = APIRouter(prefix="/configuracion", tags=["Configuración"])


class UsuarioResponse(BaseModel):
    id: str
    username: str
    name: str
    email: str
    rol: str
    active: bool


class UsuarioCrearRequest(BaseModel):
    username: str
    name: str
    email: str
    rol: RolUsuario
    password: str
    active: bool = True


class UsuarioActualizarRequest(BaseModel):
    username: Any = None
    name: Any = None
    email: Any = None
    rol: Any = None
    active: Any = None


class ResetPasswordRequest(BaseModel):
    passwordNueva: str


def _usuario_to_response(usuario: Usuario) -> UsuarioResponse:
    return UsuarioResponse(
        id=usuario.id,
        username=usuario.username,
        name=usuario.name,
        email=usuario.email,
        rol=usuario.rol,
        active=bool(usuario.active),
    )


def _campos_enviados(body: BaseModel) -> set[str]:
    return getattr(body, "model_fields_set", getattr(body, "__fields_set__", set()))


def _validar_email(email: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    usuarios = db.query(Usuario).order_by(Usuario.username.asc()).all()
    return [_usuario_to_response(usuario) for usuario in usuarios]


@router.get("/auditoria", response_model=list[MuestraAuditoriaSchema])
def listar_auditoria_configuracion(
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    filas = (
        db.query(MuestraAuditoria)
        .filter(MuestraAuditoria.tipo_estudio == "usuario")
        .order_by(MuestraAuditoria.fecha.desc(), MuestraAuditoria.id.desc())
        .limit(300)
        .all()
    )
    return [
        MuestraAuditoriaSchema(
            id=fila.id,
            protocolo=fila.protocolo,
            codigo=fila.codigo,
            tipoEstudio=fila.tipo_estudio,
            accion=fila.accion,
            usuarioId=fila.usuario_id,
            estadoAnterior=fila.estado_anterior,
            estadoNuevo=fila.estado_nuevo,
            detalle=fila.detalle,
            datos=fila.datos,
            fecha=fila.fecha.strftime("%Y-%m-%d %H:%M:%S") if fila.fecha else "",
        )
        for fila in filas
    ]


@router.post("/usuarios", response_model=UsuarioResponse)
def crear_usuario(
    body: UsuarioCrearRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    username = body.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=422, detail="El usuario debe tener al menos 3 caracteres")
    validar_password_fuerte(body.password)

    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese username")

    ahora = datetime.now()
    usuario = Usuario(
        id=str(uuid4()),
        username=username,
        name=body.name.strip(),
        email=str(body.email),
        rol=body.rol.value,
        password_hash=hash_password(body.password),
        active=body.active,
        password_changed_at=ahora,
        force_password_change=False,
        created_at=ahora,
        updated_at=ahora,
    )
    db.add(usuario)
    registrar_auditoria(
        db,
        accion="usuario_creado",
        usuario_id=admin.username,
        codigo=username,
        tipo_estudio="usuario",
        detalle="Usuario creado desde configuracion",
        datos={
            "usuario_id": usuario.id,
            "username": usuario.username,
            "rol": usuario.rol,
            "active": bool(usuario.active),
        },
    )
    db.commit()
    db.refresh(usuario)
    return _usuario_to_response(usuario)


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioResponse)
def actualizar_usuario(
    usuario_id: str,
    body: UsuarioActualizarRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    campos = _campos_enviados(body)
    datos_anteriores = {
        "username": usuario.username,
        "name": usuario.name,
        "email": usuario.email,
        "rol": usuario.rol,
        "active": bool(usuario.active),
    }

    if "username" in campos:
        if not isinstance(body.username, str) or not body.username.strip():
            raise HTTPException(status_code=422, detail="El username no puede estar vacío")
        username = body.username.strip().lower()
        if len(username) < 3:
            raise HTTPException(status_code=422, detail="El usuario debe tener al menos 3 caracteres")
        existente = (
            db.query(Usuario)
            .filter(Usuario.username == username, Usuario.id != usuario_id)
            .first()
        )
        if existente:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese username")
        usuario.username = username

    if "name" in campos:
        if not isinstance(body.name, str) or not body.name.strip():
            raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
        usuario.name = body.name.strip()

    if "email" in campos:
        if not isinstance(body.email, str) or not body.email.strip():
            raise HTTPException(status_code=422, detail="El email no puede estar vacío")
        email = body.email.strip()
        if not _validar_email(email):
            raise HTTPException(status_code=422, detail="El email debe tener un formato válido")
        usuario.email = email

    if "rol" in campos:
        roles_validos = {rol.value for rol in RolUsuario}
        if body.rol not in roles_validos:
            raise HTTPException(status_code=422, detail="El rol debe ser tecnico, bioquimico o admin")
        usuario.rol = body.rol

    if "active" in campos:
        if not isinstance(body.active, bool):
            raise HTTPException(status_code=422, detail="active debe ser boolean")
        usuario.active = body.active

    usuario.updated_at = datetime.now()
    registrar_auditoria(
        db,
        accion="usuario_actualizado",
        usuario_id=admin.username,
        codigo=usuario.username,
        tipo_estudio="usuario",
        detalle="Usuario actualizado desde configuracion",
        datos={
            "usuario_id": usuario.id,
            "campos": sorted(campos),
            "antes": datos_anteriores,
            "despues": {
                "username": usuario.username,
                "name": usuario.name,
                "email": usuario.email,
                "rol": usuario.rol,
                "active": bool(usuario.active),
            },
        },
    )

    db.commit()
    db.refresh(usuario)
    return _usuario_to_response(usuario)


@router.post("/usuarios/{usuario_id}/reset-password")
def reset_password_usuario(
    usuario_id: str,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    validar_password_fuerte(body.passwordNueva)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario.password_hash = hash_password(body.passwordNueva)
    usuario.password_changed_at = datetime.now()
    usuario.force_password_change = True
    usuario.updated_at = datetime.now()
    registrar_auditoria(
        db,
        accion="usuario_reset_password",
        usuario_id=admin.username,
        codigo=usuario.username,
        tipo_estudio="usuario",
        detalle="Administrador reseteo la contraseña de un usuario",
        datos={"usuario_id": usuario.id, "username": usuario.username},
    )
    db.commit()
    return {"ok": True}


@router.delete("/usuarios/{usuario_id}")
def eliminar_usuario(
    usuario_id: str,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    if admin.id == usuario_id:
        raise HTTPException(status_code=422, detail="No podés eliminar tu propio usuario")

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    registrar_auditoria(
        db,
        accion="usuario_eliminado",
        usuario_id=admin.username,
        codigo=usuario.username,
        tipo_estudio="usuario",
        detalle="Usuario eliminado desde configuracion",
        datos={
            "usuario_id": usuario.id,
            "username": usuario.username,
            "name": usuario.name,
            "email": usuario.email,
            "rol": usuario.rol,
        },
    )
    db.delete(usuario)
    db.commit()
    return {"ok": True}
