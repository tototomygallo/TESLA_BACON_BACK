from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import (
    CargaTxtResponse,
    IngresarLoteRequest,
    IngresarLoteResponse,
    LactokitResultadosRequest,
    MuestraAuditoriaSchema,
    MuestraResponse,
)
from app.services import muestras as muestras_svc
from app.services.carga_txt import cargar_resultados_txt
from app.services.converters import muestra_to_response
from app.services.estudios import TIPO_LACTOKIT
from app.services.lactokit import guardar_resultados_lactokit, obtener_resultado_lactokit
from app.services.pdf_generator import generar_informe_pdf
from app.models import Muestra, MuestraAuditoria, Usuario

router = APIRouter(prefix="/muestras", tags=["Muestras"])


@router.get("", response_model=list[MuestraResponse])
def listar(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    filas = muestras_svc.listar_muestras(db)
    return [muestra_to_response(m) for m in filas]


@router.post("/ingresar-lote", response_model=IngresarLoteResponse)
async def ingresar_lote(
    body: IngresarLoteRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        resultado = await muestras_svc.ingresar_lote(db, body.codigos, usuario_id=usuario.username)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return IngresarLoteResponse(
        ingresadas=[muestra_to_response(m) for m in resultado["ingresadas"]],
        rechazadas=resultado["rechazadas"],
        duplicadas=resultado["duplicadas"],
    )


@router.post("/cargar-txt", response_model=CargaTxtResponse)
async def cargar_txt(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    contenido = (await request.body()).decode("utf-8")
    resultado = cargar_resultados_txt(db, contenido, usuario_id=usuario.username)
    return CargaTxtResponse(**resultado)


@router.post("/{protocolo}/resultados-lactokit", response_model=MuestraResponse)
def cargar_resultados_lactokit(
    protocolo: str,
    body: LactokitResultadosRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        muestra = guardar_resultados_lactokit(
            db,
            protocolo,
            body.h2,
            body.ch4,
            body.co2,
            confirmar=body.confirmar,
            usuario_id=usuario.username,
        )
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{protocolo}/validar", response_model=MuestraResponse)
async def validar(
    protocolo: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        muestra, advertencia = await muestras_svc.validar_muestra(
            db, protocolo, usuario_id=usuario.username
        )
        respuesta = muestra_to_response(muestra)
        respuesta.advertencia = advertencia
        return respuesta
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{protocolo}/reiniciar", response_model=MuestraResponse)
def reiniciar(
    protocolo: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        muestra = muestras_svc.reiniciar_muestra(db, protocolo, usuario_id=usuario.username)
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{protocolo}/imprimir-etiquetas", response_model=MuestraResponse)
def imprimir_etiquetas(
    protocolo: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        muestra = muestras_svc.imprimir_etiquetas(db, protocolo, usuario_id=usuario.username)
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{protocolo}/auditoria", response_model=list[MuestraAuditoriaSchema])
def auditoria(
    protocolo: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    filas = (
        db.query(MuestraAuditoria)
        .filter(MuestraAuditoria.protocolo == protocolo)
        .order_by(MuestraAuditoria.fecha.asc(), MuestraAuditoria.id.asc())
        .all()
    )
    return [
        MuestraAuditoriaSchema(
            id=fila.id,
            protocolo=fila.protocolo,
            codigo=fila.codigo,
            tipoEstudio=fila.tipo_estudio,
            accion=fila.accion,
            usuarioId=fila.usuario_id,
            estadoAnterior=fila.estado_anterior,
            estadoNuevo=fila.estado_nuevo,
            detalle=fila.detalle,
            datos=fila.datos,
            fecha=fila.fecha.strftime("%Y-%m-%d %H:%M:%S") if fila.fecha else "",
        )
        for fila in filas
    ]


@router.get("/{protocolo}/pdf")
def descargar_pdf(
    protocolo: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Genera y descarga el PDF del informe de una muestra."""
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        resultado_lactokit = obtener_resultado_lactokit(db, muestra.protocolo)
        sin_resultados = resultado_lactokit is None or not resultado_lactokit.valoracion
    else:
        sin_resultados = muestra.resultado_test_value is None
    if sin_resultados:
        raise HTTPException(status_code=422, detail="La muestra no tiene resultados cargados")
    try:
        validacion_clinica = muestra.estado != "anulado"
        pdf_bytes = generar_informe_pdf(
            muestra,
            validacion_clinica=validacion_clinica,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="informe-{protocolo}.pdf"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
