"""Dependencias de autenticación basadas en JWT (Authorization: Bearer <token>)."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RolUsuario, Usuario
from app.services.security import TokenInvalido, decodificar_token

_401 = HTTPException(
    status_code=401,
    detail="Token inválido o expirado",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extraer_bearer(authorization: str | None) -> str:
    if not authorization:
        raise _401
    esquema, _, token = authorization.partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        raise _401
    return token.strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Usuario:
    """Valida el access token y devuelve el Usuario activo correspondiente."""
    token = _extraer_bearer(authorization)
    try:
        payload = decodificar_token(token, tipo_esperado="access")
    except TokenInvalido:
        raise _401

    usuario = db.query(Usuario).filter(Usuario.id == payload.get("sub")).first()
    if not usuario or usuario.active is False:
        raise _401

    return usuario


def require_admin(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """Como get_current_user pero además exige rol admin."""
    if usuario.rol != RolUsuario.admin.value:
        raise HTTPException(status_code=403, detail="Solo administradores")
    return usuario
