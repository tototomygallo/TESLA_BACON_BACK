from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    userId: str
    password: str = ""  # Acepta password pero no lo valida en modo pruebas


class LoginResponse(BaseModel):
    id: str
    nombre: str
    rol: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter_by(id=body.userId.strip().lower()).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return LoginResponse(id=usuario.id, nombre=usuario.nombre, rol=usuario.rol)
