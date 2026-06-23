"""Emisión y validación de JWT (HS256) usando solo la stdlib.

Produce tokens JWT estándar (header.payload.signature, base64url) que el front
puede decodificar con cualquier librería tipo `jwt-decode`. No requiere
dependencias externas.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from app.config import get_settings


class TokenInvalido(Exception):
    """El token falta, está mal formado, la firma no valida o expiró."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segmento: str) -> bytes:
    relleno = "=" * (-len(segmento) % 4)
    return base64.urlsafe_b64decode(segmento + relleno)


def _firmar(mensaje: bytes, secret: str) -> str:
    firma = hmac.new(secret.encode("utf-8"), mensaje, hashlib.sha256).digest()
    return _b64url_encode(firma)


def _ahora_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _crear_token(claims: dict, minutos: int) -> tuple[str, int]:
    """Devuelve (token, expires_in_segundos)."""
    settings = get_settings()
    emitido = _ahora_ts()
    expira = emitido + minutos * 60

    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    payload = {**claims, "iat": emitido, "exp": expira}

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    firma_input = f"{header_b64}.{payload_b64}".encode("ascii")
    firma_b64 = _firmar(firma_input, settings.jwt_secret)

    return f"{header_b64}.{payload_b64}.{firma_b64}", minutos * 60


def crear_access_token(usuario) -> tuple[str, int]:
    settings = get_settings()
    claims = {
        "sub": usuario.id,
        "username": usuario.username,
        "rol": usuario.rol,
        "name": usuario.name,
        "type": "access",
    }
    return _crear_token(claims, settings.session_timeout_minutes)


def crear_refresh_token(usuario) -> tuple[str, int]:
    settings = get_settings()
    claims = {
        "sub": usuario.id,
        "username": usuario.username,
        "type": "refresh",
    }
    return _crear_token(claims, settings.refresh_timeout_minutes)


def decodificar_token(token: str, tipo_esperado: str) -> dict:
    """Valida firma, expiración y tipo. Devuelve los claims o lanza TokenInvalido."""
    settings = get_settings()
    if not token:
        raise TokenInvalido("Falta el token")

    partes = token.split(".")
    if len(partes) != 3:
        raise TokenInvalido("Token mal formado")

    header_b64, payload_b64, firma_b64 = partes

    try:
        header = json.loads(_b64url_decode(header_b64))
    except (ValueError, json.JSONDecodeError):
        raise TokenInvalido("Header inválido")

    if header.get("alg") != settings.jwt_algorithm:
        raise TokenInvalido("Algoritmo no soportado")

    firma_input = f"{header_b64}.{payload_b64}".encode("ascii")
    firma_esperada = _firmar(firma_input, settings.jwt_secret)
    if not hmac.compare_digest(firma_esperada, firma_b64):
        raise TokenInvalido("Firma inválida")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        raise TokenInvalido("Payload inválido")

    if payload.get("type") != tipo_esperado:
        raise TokenInvalido("Tipo de token incorrecto")

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < _ahora_ts():
        raise TokenInvalido("Token expirado")

    return payload
