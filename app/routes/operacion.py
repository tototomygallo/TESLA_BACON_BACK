from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import Usuario
from app.schemas import (
    AnuladoPendienteRevisionSchema,
    CompletadoCorreccionSchema,
    CorreccionValoresTaukitRequest,
    GenerarInformeCorreccionRequest,
    InformeCorreccionResponse,
    MuestraResponse,
)
from app.services import muestras as muestras_svc
from app.services.converters import muestra_to_response

router = APIRouter(prefix="/operacion/correccion-estados", tags=["Operacion"])


@router.get("/anulados-pendientes", response_model=list[AnuladoPendienteRevisionSchema])
def listar_anulados_pendientes(
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    return muestras_svc.listar_mal_anulados_pendientes_revision(db)


@router.post("/{protocolo}/revertir-a-en-proceso", response_model=MuestraResponse)
def revertir_a_en_proceso(
    protocolo: str,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    try:
        muestra = muestras_svc.revertir_mal_anulado_a_en_proceso(
            db, protocolo, usuario_id=admin.username
        )
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/completados/buscar", response_model=list[CompletadoCorreccionSchema])
def buscar_completados(
    q: str | None = None,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    return muestras_svc.listar_completados_para_correccion(db, q=q)


@router.post("/completados/{protocolo}/cargar-valores", response_model=MuestraResponse)
def cargar_valores_completado(
    protocolo: str,
    body: CorreccionValoresTaukitRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    try:
        muestra = muestras_svc.cargar_valores_correccion_completado(
            db,
            protocolo,
            basal_co2=body.basalCO2,
            post_co2=body.postCO2,
            basal_delta=body.basalDelta,
            post_delta=body.postDelta,
            test_value=body.testValue,
            usuario_id=admin.username,
            usuario_id_body=body.usuarioId,
        )
        return muestra_to_response(muestra)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/completados/{protocolo}/generar-informe", response_model=InformeCorreccionResponse)
async def generar_informe_completado(
    protocolo: str,
    body: GenerarInformeCorreccionRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin),
):
    try:
        muestra, advertencia, verificacion = await muestras_svc.generar_informe_correccion_completado(
            db,
            protocolo,
            usuario_id=admin.username,
            usuario_id_body=body.usuarioId,
        )
        return InformeCorreccionResponse(
            protocolo=muestra.protocolo,
            estado=muestra.estado,
            pdfGenerado=muestra.pdf_generado,
            pdfVerificado=bool(muestra.bacon_pdf_enviado),
            advertencia=advertencia,
            pdfVerificacion=verificacion,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
