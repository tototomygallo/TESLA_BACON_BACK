from app.models import Muestra
from app.schemas import (
    EstudioSchema, MuestraResponse, PacienteSchema,
    ResultadoMuestraSchema, SucursalSchema,
)


def muestra_to_response(m: Muestra) -> MuestraResponse:
    resultados = None
    if m.resultado_test_value is not None:
        resultados = ResultadoMuestraSchema(
            basalCO2=m.resultado_basal_co2 or 0,
            postCO2=m.resultado_post_co2 or 0,
            basalDelta=m.resultado_basal_delta or 0,
            postDelta=m.resultado_post_delta or 0,
            testValue=m.resultado_test_value,
            cargadoEn=m.resultado_cargado_en or "",
        )

    return MuestraResponse(
        protocolo=m.protocolo,
        codigoTauKit=m.codigo_taukit,
        paciente=PacienteSchema(
            nombre=m.paciente_nombre, apellido=m.paciente_apellido,
            dni=m.paciente_dni, fechaTomaMuestra=m.fecha_toma_muestra,
        ),
        estudio=EstudioSchema(codigo=m.estudio_codigo, nombre=m.estudio_nombre),
        sucursal=SucursalSchema(codigo=m.sucursal_codigo, nombre=m.sucursal_nombre),
        estado=m.estado,
        fechaIngreso=m.fecha_ingreso.strftime("%Y-%m-%d %H:%M") if m.fecha_ingreso else "",
        tieneError=m.tiene_error,
        intentosFallidos=m.intentos_fallidos,
        resultados=resultados,
    )
