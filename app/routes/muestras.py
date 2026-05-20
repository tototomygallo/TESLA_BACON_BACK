from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    CargaTxtResponse,
    IngresarLoteRequest,
    IngresarLoteResponse,
    MuestraResponse,
)
from app.services import muestras as muestras_svc
from app.services.carga_txt import cargar_resultados_txt
from app.services.converters import muestra_to_response
from app.services.pdf_generator import generar_informe_pdf
from app.models import Muestra

router = APIRouter(prefix="/muestras", tags=["Muestras"])


@router.get("", response_model=list[MuestraResponse])
def listar(db: Session = Depends(get_db)):
    filas = muestras_svc.listar_muestras(db)
    return [muestra_to_response(m) for m in filas]


@router.post("/ingresar-lote", response_model=IngresarLoteResponse)
async def ingresar_lote(body: IngresarLoteRequest, db: Session = Depends(get_db)):
    resultado = await muestras_svc.ingresar_lote(db, body.codigos)
    return IngresarLoteResponse(
        ingresadas=[muestra_to_response(m) for m in resultado["ingresadas"]],
        rechazadas=resultado["rechazadas"],
        duplicadas=resultado["duplicadas"],
    )


@router.post("/cargar-txt", response_model=CargaTxtResponse)
async def cargar_txt(request: Request, db: Session = Depends(get_db)):
    contenido = (await request.body()).decode("utf-8")
    resultado = cargar_resultados_txt(db, contenido)
    return CargaTxtResponse(**resultado)


@router.post("/{protocolo}/validar", response_model=MuestraResponse)
async def validar(protocolo: str, db: Session = Depends(get_db)):
    try:
        muestra = await muestras_svc.validar_muestra(db, protocolo)
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{protocolo}/reiniciar", response_model=MuestraResponse)
def reiniciar(protocolo: str, db: Session = Depends(get_db)):
    try:
        muestra = muestras_svc.reiniciar_muestra(db, protocolo)
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{protocolo}/imprimir-etiquetas", response_model=MuestraResponse)
def imprimir_etiquetas(protocolo: str, db: Session = Depends(get_db)):
    try:
        muestra = muestras_svc.imprimir_etiquetas(db, protocolo)
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{protocolo}/pdf")
def descargar_pdf(protocolo: str, db: Session = Depends(get_db)):
    """Genera y descarga el PDF del informe de una muestra."""
    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.resultado_test_value is None:
        raise HTTPException(status_code=422, detail="La muestra no tiene resultados cargados")
    try:
        pdf_bytes = generar_informe_pdf(muestra)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="informe-{protocolo}.pdf"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
