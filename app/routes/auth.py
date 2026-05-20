from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario


import hashlib


router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    userId: str
    password: str  # Acepta password pero no lo valida en modo pruebas


class LoginResponse(BaseModel):
    id: str
    nombre: str
    rol: str


def verificar_password(password_plana: str, password_hash: str) -> bool:
    hash_generado = hashlib.sha256(password_plana.encode()).hexdigest()
    return hash_generado == password_hash


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == body.userId.strip().lower())
        .first()
    )

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    print(usuario.active, type(usuario.active))

    if usuario.active == False:
        raise HTTPException(status_code=403, detail="Usuario desactivado")
    
    if not verificar_password(body.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")


    return LoginResponse(id=usuario.id, nombre=usuario.username, rol=usuario.rol)
