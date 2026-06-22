from datetime import datetime, timedelta
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.services.auditoria import registrar_auditoria


router = APIRouter(prefix="/auth", tags=["Auth"])
PASSWORD_EXPIRATION_DAYS = 90

PASSWORD_POLICY_MESSAGE = (
    "La contraseña debe tener más de 6 caracteres, una mayúscula, "
    "un número y un carácter especial."
)


class LoginRequest(BaseModel):
    userId: str | None = None
    username: str | None = None
    password: str  # Acepta password pero no lo valida en modo pruebas


class CambiarPasswordRequest(BaseModel):
    userId: str | None = None
    username: str | None = None
    id: str | None = None
    passwordActual: str | None = None
    passwordNueva: str | None = None
    currentPassword: str | None = None
    newPassword: str | None = None
    actualPassword: str | None = None
    nuevaPassword: str | None = None


class LoginResponse(BaseModel):
    id: str
    username: str
    nombre: str
    rol: str
    passwordExpired: bool = False


def verificar_password(password_plana: str, password_hash: str) -> bool:
    return hash_password(password_plana) == password_hash


def hash_password(password_plana: str) -> str:
    return hashlib.sha256(password_plana.encode()).hexdigest()


def validar_password_fuerte(password: str) -> None:
    if (
        len(password) <= 6
        or not any(char.isupper() for char in password)
        or not any(char.isdigit() for char in password)
        or not any(not char.isalnum() for char in password)
    ):
        raise HTTPException(status_code=422, detail=PASSWORD_POLICY_MESSAGE)


def password_expirada(usuario: Usuario) -> bool:
    if usuario.force_password_change:
        return True
    if not usuario.password_changed_at:
        return True
    return usuario.password_changed_at <= datetime.now() - timedelta(days=PASSWORD_EXPIRATION_DAYS)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user_id = body.username or body.userId
    if not user_id:
        raise HTTPException(status_code=422, detail="Falta username")

    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == user_id.strip().lower())
        .first()
    )

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if usuario.active == False:
        raise HTTPException(status_code=403, detail="Usuario desactivado")
    
    if not verificar_password(body.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")


    return LoginResponse(
        id=usuario.id,
        username=usuario.username,
        nombre=usuario.name,
        rol=usuario.rol,
        passwordExpired=password_expirada(usuario),
    )


@router.post("/cambiar-password")
def cambiar_password(
    body: CambiarPasswordRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
):
    user_id = body.userId or body.username or body.id or x_user_id
    password_actual = body.passwordActual or body.currentPassword or body.actualPassword
    password_nueva = body.passwordNueva or body.newPassword or body.nuevaPassword

    if not user_id:
        raise HTTPException(status_code=422, detail="Falta userId")
    if not password_actual:
        raise HTTPException(status_code=422, detail="Falta passwordActual")
    if not password_nueva:
        raise HTTPException(status_code=422, detail="Falta passwordNueva")

    user_id = user_id.strip().lower()
    usuario = db.query(Usuario).filter(Usuario.username == user_id).first()
    if not usuario:
        usuario = db.query(Usuario).filter(Usuario.id == user_id).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.active == False:
        raise HTTPException(status_code=403, detail="Usuario desactivado")

    if not verificar_password(password_actual, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Contraseña actual incorrecta")

    validar_password_fuerte(password_nueva)

    usuario.password_hash = hash_password(password_nueva)
    usuario.password_changed_at = datetime.now()
    usuario.force_password_change = False
    usuario.updated_at = datetime.now()
    registrar_auditoria(
        db,
        accion="usuario_cambio_password",
        usuario_id=x_user_id or usuario.username,
        codigo=usuario.username,
        tipo_estudio="usuario",
        detalle="Usuario cambio su contraseña",
        datos={"usuario_id": usuario.id, "username": usuario.username},
    )
    db.commit()
    return {"ok": True}
