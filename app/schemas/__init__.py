from pydantic import BaseModel, field_validator, model_validator
from typing import Any, Optional


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


class ResultadoLactokitSchema(BaseModel):
    h2: list[Any]
    ch4: list[Any]
    co2: list[Any]
    valoracion: str
    condicion: Optional[str] = None  # "b"|"c"|"d"|"e" solo cuando valoracion == "6"
    descripcion: str
    cargadoEn: str


class MuestraResponse(BaseModel):
    protocolo: str
    codigoTauKit: str
    codigoLactokit: Optional[str] = None
    tipoEstudio: str = "taukit"
    paciente: PacienteSchema
    estudio: EstudioSchema
    sucursal: SucursalSchema
    estado: str
    fechaIngreso: str
    tieneError: bool
    intentosFallidos: int
    resultados: Optional[ResultadoMuestraSchema] = None
    resultadosLactokit: Optional[ResultadoLactokitSchema] = None
    pdfGenerado: bool = False
    pdfVerificado: bool = False
    pdfVerificacion: Optional[Any] = None
    advertencia: Optional[str] = None


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
    pendientesAnulacion: list[str] = []
    noEncontrados: list[str]
    yaCompletados: list[str]
    yaAnuladas: list[str]
    requierenReinicio: list[str] = []
    controles: int
    erroresParseo: int
    txtDuplicado: bool = False


class LactokitResultadosRequest(BaseModel):
    h2: list[Any]
    ch4: list[Any]
    co2: list[Any]
    confirmar: bool = True


class RevertirAnulacionRequest(BaseModel):
    motivo: str

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El motivo es obligatorio")
        return value


class MarcarMalAnuladoRequest(BaseModel):
    motivo: str
    detalle: Optional[str] = None
    usuarioId: Optional[str] = None

    @field_validator("motivo")
    @classmethod
    def motivo_valido(cls, value: str) -> str:
        motivo = value.strip()
        if motivo not in ("Error en la carga de resultados", "Otro"):
            raise ValueError("El motivo debe ser 'Error en la carga de resultados' u 'Otro'")
        return motivo

    @field_validator("detalle")
    @classmethod
    def detalle_limpio(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        detalle = value.strip()
        return detalle or None

    @model_validator(mode="after")
    def detalle_obligatorio_para_otro(self) -> "MarcarMalAnuladoRequest":
        if self.motivo == "Otro" and not self.detalle:
            raise ValueError("El detalle es obligatorio cuando el motivo es 'Otro'")
        return self


class AnuladoPendienteRevisionSchema(BaseModel):
    numeroSerie: str
    protocolo: str
    paciente: PacienteSchema
    estado: str
    motivo: str
    detalle: Optional[str] = None
    usuarioId: str
    fecha: str
    tipoEstudio: str = "taukit"
    intentosFallidos: int


class CompletadoCorreccionSchema(BaseModel):
    numeroSerie: str
    protocolo: str
    paciente: PacienteSchema
    estado: str
    fechaInforme: str
    resultados: Optional[ResultadoMuestraSchema] = None


class CorreccionValoresTaukitRequest(BaseModel):
    basalCO2: float
    postCO2: float
    basalDelta: float
    postDelta: float
    testValue: float
    usuarioId: Optional[str] = None


class GenerarInformeCorreccionRequest(BaseModel):
    usuarioId: Optional[str] = None


class InformeCorreccionResponse(BaseModel):
    protocolo: str
    estado: str
    pdfGenerado: bool
    pdfVerificado: bool
    advertencia: Optional[str] = None
    pdfVerificacion: Optional[Any] = None


class MuestraAuditoriaSchema(BaseModel):
    id: int
    protocolo: Optional[str] = None
    codigo: Optional[str] = None
    tipoEstudio: Optional[str] = None
    accion: str
    usuarioId: Optional[str] = None
    estadoAnterior: Optional[str] = None
    estadoNuevo: Optional[str] = None
    detalle: Optional[str] = None
    datos: Optional[str] = None
    fecha: str


class ProtocoloEditadoSchema(BaseModel):
    protocolo: str
    numeroSerie: str
    tipoEstudio: str
    fechaIngreso: str
    fechaEdicion: str
    motivo: str
    usuario: str
    camposEditados: list[str]


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
