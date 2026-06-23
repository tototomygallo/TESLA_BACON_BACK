from datetime import datetime, timedelta
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Usuario
from app.services.auditoria import registrar_auditoria
from app.services.security import (
    TokenInvalido,
    crear_access_token,
    crear_refresh_token,
    decodificar_token,
)


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


class UsuarioOut(BaseModel):
    id: str
    username: str
    nombre: str
    rol: str
    passwordExpired: bool = False


class LoginResponse(BaseModel):
    usuario: UsuarioOut
    token: str
    tokenType: str = "Bearer"
    expiresIn: int            # segundos de vida del access token
    refreshToken: str
    refreshExpiresIn: int     # segundos de vida del refresh token


class RefreshRequest(BaseModel):
    refreshToken: str


class RefreshResponse(BaseModel):
    token: str
    tokenType: str = "Bearer"
    expiresIn: int
    refreshToken: str
    refreshExpiresIn: int


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

    access_token, expires_in = crear_access_token(usuario)
    refresh_token, refresh_expires_in = crear_refresh_token(usuario)

    return LoginResponse(
        usuario=UsuarioOut(
            id=usuario.id,
            username=usuario.username,
            nombre=usuario.name,
            rol=usuario.rol,
            passwordExpired=password_expirada(usuario),
        ),
        token=access_token,
        expiresIn=expires_in,
        refreshToken=refresh_token,
        refreshExpiresIn=refresh_expires_in,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decodificar_token(body.refreshToken, tipo_esperado="refresh")
    except TokenInvalido:
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.query(Usuario).filter(Usuario.id == payload.get("sub")).first()
    if not usuario or usuario.active is False:
        raise HTTPException(
            status_code=401,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = crear_access_token(usuario)
    # Rotación del refresh token: cada refresh renueva también la ventana larga.
    refresh_token, refresh_expires_in = crear_refresh_token(usuario)

    return RefreshResponse(
        token=access_token,
        expiresIn=expires_in,
        refreshToken=refresh_token,
        refreshExpiresIn=refresh_expires_in,
    )


@router.post("/cambiar-password")
def cambiar_password(
    body: CambiarPasswordRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    # El usuario solo puede cambiar su propia contraseña: el objetivo sale del token,
    # no del body (se ignoran userId/username/id que el front pudiera mandar).
    password_actual = body.passwordActual or body.currentPassword or body.actualPassword
    password_nueva = body.passwordNueva or body.newPassword or body.nuevaPassword

    if not password_actual:
        raise HTTPException(status_code=422, detail="Falta passwordActual")
    if not password_nueva:
        raise HTTPException(status_code=422, detail="Falta passwordNueva")

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
        usuario_id=usuario.username,
        codigo=usuario.username,
        tipo_estudio="usuario",
        detalle="Usuario cambio su contraseña",
        datos={"usuario_id": usuario.id, "username": usuario.username},
    )
    db.commit()
    return {"ok": True}
