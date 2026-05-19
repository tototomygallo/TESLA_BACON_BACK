from pydantic import BaseModel
from typing import Optional


class PacienteSchema(BaseModel):
    nombre: str
    apellido: str
    dni: str
    fechaTomaMuestra: str


class EstudioSchema(BaseModel):
    codigo: str
    nombre: str


class SucursalSchema(BaseModel):
    codigo: str
    nombre: str


class ResultadoMuestraSchema(BaseModel):
    basalCO2: float
    postCO2: float
    basalDelta: float
    postDelta: float
    testValue: float
    cargadoEn: str


class MuestraResponse(BaseModel):
    protocolo: str
    codigoTauKit: str
    paciente: PacienteSchema
    estudio: EstudioSchema
    sucursal: SucursalSchema
    estado: str
    fechaIngreso: str
    tieneError: bool
    intentosFallidos: int
    resultados: Optional[ResultadoMuestraSchema] = None


class IngresarLoteRequest(BaseModel):
    codigos: list[str]


class IngresarLoteResponse(BaseModel):
    ingresadas: list[MuestraResponse]
    rechazadas: list[str]
    duplicadas: list[str]


class CargaTxtResponse(BaseModel):
    cargadosOk: list[str]
    cargadosReintentando: list[str]
    conErrorEquipo: list[str]
    anuladas: list[str]
    noEncontrados: list[str]
    yaCompletados: list[str]
    yaAnuladas: list[str]
    controles: int
    erroresParseo: int


class DiscrepanciaSchema(BaseModel):
    codigo: str
    fecha: str
    motivo: str


class ResumenDiarioSchema(BaseModel):
    fecha: str
    ingresadas: int
    procesadas: int
    finalizadas: int
    pendientes: int
    discrepancias: int
    rechazados: list[DiscrepanciaSchema] = []


class BaconPacienteSchema(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    documento: Optional[str] = None


class BaconMuestraSchema(BaseModel):
    REM: str
    numero_serie: str
    ctm: str
    medico: Optional[str] = None
    estado: str
    fecha_carga: str
    paciente: BaconPacienteSchema
