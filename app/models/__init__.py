from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
import enum

from app.database import Base


class EstadoMuestra(str, enum.Enum):
    recibido = "recibido"
    en_proceso = "en_proceso"
    en_validacion = "en_validacion"
    completado = "completado"
    anulado = "anulado"


class RolUsuario(str, enum.Enum):
    tecnico = "tecnico"
    bioquimico = "bioquimico"
    admin = "admin"


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = {"schema": "lab"}

    id = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    clave = Column(String, nullable=False)
    rol = Column(String, nullable=False)


class Muestra(Base):
    __tablename__ = "muestras"
    __table_args__ = {"schema": "lab"}

    protocolo = Column(String, primary_key=True)
    codigo_taukit = Column(String, nullable=False, unique=True, index=True)
    paciente_nombre = Column(String, nullable=False, default="")
    paciente_apellido = Column(String, nullable=False, default="")
    paciente_dni = Column(String, nullable=False, default="")
    fecha_toma_muestra = Column(String, nullable=False, default="")
    estudio_codigo = Column(String, nullable=False)
    estudio_nombre = Column(String, nullable=False)
    sucursal_codigo = Column(String, nullable=False)
    sucursal_nombre = Column(String, nullable=False)
    estado = Column(String, nullable=False, default="recibido")
    tiene_error = Column(Boolean, nullable=False, default=False)
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    resultado_basal_co2 = Column(Float, nullable=True)
    resultado_post_co2 = Column(Float, nullable=True)
    resultado_basal_delta = Column(Float, nullable=True)
    resultado_post_delta = Column(Float, nullable=True)
    resultado_test_value = Column(Float, nullable=True)
    resultado_cargado_en = Column(String, nullable=True)
    bacon_recibido = Column(Boolean, nullable=False, default=False)  # True = BACON fue notificado
    fecha_ingreso = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Consecutivo(Base):
    __tablename__ = "consecutivos"
    __table_args__ = {"schema": "lab"}
    estudio_codigo = Column(String, primary_key=True)
    ultimo = Column(Integer, nullable=False, default=0)


class Discrepancia(Base):
    __tablename__ = "discrepancias"
    __table_args__ = {"schema": "lab"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String, nullable=False)
    motivo = Column(String, nullable=False)
    fecha = Column(DateTime, server_default=func.now())
