from sqlalchemy.orm import object_session

from app.models import Muestra
from app.schemas import (
    EstudioSchema, MuestraResponse, PacienteSchema,
    ResultadoLactokitSchema, ResultadoSibokitSchema, ResultadoMuestraSchema, SucursalSchema,
)
from app.services.estudios import TIPO_LACTOKIT, TIPO_SIBOKIT
from app.services.lactokit import leer_valores_lactokit, obtener_resultado_lactokit
from app.services.sibokit import leer_valores_sibokit, obtener_resultado_sibokit


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

    resultados_lactokit = None
    resultado_lactokit = None
    if m.tipo_estudio == TIPO_LACTOKIT:
        db = object_session(m)
        if db:
            resultado_lactokit = obtener_resultado_lactokit(db, m.protocolo)
    valores_lactokit = leer_valores_lactokit(resultado_lactokit)
    if valores_lactokit and resultado_lactokit:
        # La valoración "6" se persiste como "6b"/"6c"/"6d"/"6e" para guardar qué
        # condición (b/c/d/e) la originó. La API la expone como valoracion="6" + la
        # letra por separado en `condicion`.
        valoracion_guardada = resultado_lactokit.valoracion or ""
        if valoracion_guardada[:1] == "6" and len(valoracion_guardada) > 1:
            valoracion_api = "6"
            condicion = valoracion_guardada[1]
        else:
            valoracion_api = valoracion_guardada
            condicion = None
        resultados_lactokit = ResultadoLactokitSchema(
            h2=valores_lactokit["h2"],
            ch4=valores_lactokit["ch4"],
            co2=valores_lactokit["co2"],
            valoracion=valoracion_api,
            condicion=condicion,
            descripcion=resultado_lactokit.descripcion,
            cargadoEn=resultado_lactokit.cargado_en or "",
        )

    resultados_sibokit = None
    resultado_sibokit = None
    if m.tipo_estudio == TIPO_SIBOKIT:
        db = object_session(m)
        if db:
            resultado_sibokit = obtener_resultado_sibokit(db, m.protocolo)
    valores_sibokit = leer_valores_sibokit(resultado_sibokit)
    if valores_sibokit and resultado_sibokit:
        resultados_sibokit = ResultadoSibokitSchema(
            h2=valores_sibokit["h2"], ch4=valores_sibokit["ch4"], co2=valores_sibokit["co2"],
            factorCorreccion=valores_sibokit["factor_correccion"],
            valoracion=resultado_sibokit.valoracion, descripcion=resultado_sibokit.descripcion,
            notaAdicional=resultado_sibokit.nota_adicional, cargadoEn=resultado_sibokit.cargado_en or "",
        )

    return MuestraResponse(
        protocolo=m.protocolo,
        codigoTauKit=m.codigo_taukit,
        codigoLactokit=(
            resultado_lactokit.codigo_lactokit
            if resultado_lactokit
            else m.codigo_taukit if m.tipo_estudio == TIPO_LACTOKIT else None
        ),
        codigoSibokit=(resultado_sibokit.codigo_sibokit if resultado_sibokit else m.codigo_taukit if m.tipo_estudio == TIPO_SIBOKIT else None),
        tipoEstudio=m.tipo_estudio or "taukit",
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
        resultadosLactokit=resultados_lactokit,
        resultadosSibokit=resultados_sibokit,
        pdfGenerado=m.pdf_generado,
        pdfVerificado=bool(m.bacon_pdf_enviado),
        pdfVerificacion=None,
    )
