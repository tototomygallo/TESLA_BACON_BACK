import hashlib
import os
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import EstadoMuestra, Muestra
from app.services.auditoria import registrar_auditoria
from app.services.estudios import TIPO_LACTOKIT, TIPO_SIBOKIT
from app.services.txt_parser import parsear_txt

# Firma del último TXT cargado, para detectar re-subidas del mismo archivo.
# Se guarda en un archivo (no en BD) para no depender de migraciones.
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
_ULTIMO_TXT_SIG = os.path.join(_DATA_DIR, "ultimo_txt.sig")


def _firma_txt(contenido: str) -> str:
    """Huella del contenido, normalizando fin de línea y espacios al borde."""
    normalizado = contenido.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def _leer_ultima_firma() -> str | None:
    try:
        with open(_ULTIMO_TXT_SIG, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _guardar_ultima_firma(firma: str) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_ULTIMO_TXT_SIG, "w", encoding="utf-8") as f:
        f.write(firma)


def _respuesta_vacia(txt_duplicado: bool = False) -> dict:
    return {
        "cargadosOk": [],
        "cargadosReintentando": [],
        "conErrorEquipo": [],
        "anuladas": [],
        "pendientesAnulacion": [],
        "noEncontrados": [],
        "yaCompletados": [],
        "yaAnuladas": [],
        "requierenReinicio": [],
        "controles": 0,
        "erroresParseo": 0,
        "txtDuplicado": txt_duplicado,
    }


def _puede_reemplazar_error_equipo(muestra: Muestra) -> bool:
    return (
        muestra.estado == EstadoMuestra.en_proceso
        and muestra.tiene_error
        and muestra.resultado_cargado_en is not None
        and 0 < muestra.intentos_fallidos < 2
    )


async def cargar_resultados_txt(db: Session, contenido: str, usuario_id: str | None = None) -> dict:
    """
    Parsea el TXT del HeliFan y carga resultados en las muestras correspondientes.
    Misma lógica que el mockApi del front.
    """
    # Si es exactamente el mismo TXT que la última carga, no se procesa nada:
    # evita que re-suban el mismo archivo por error.
    firma = _firma_txt(contenido)
    if firma == _leer_ultima_firma():
        return _respuesta_vacia(txt_duplicado=True)

    parseado = parsear_txt(contenido)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    cargados_ok: list[str] = []
    cargados_reintentando: list[str] = []
    con_error_equipo: list[str] = []
    anuladas: list[str] = []
    pendientes_anulacion: list[str] = []
    no_encontrados: list[str] = []
    ya_completados: list[str] = []
    ya_anuladas: list[str] = []
    requieren_reinicio: list[str] = []

    for r in parseado.resultados:
        muestra = db.query(Muestra).filter_by(protocolo=r.test_id).first()

        if not muestra:
            no_encontrados.append(r.test_id)
            continue

        if muestra.estado == EstadoMuestra.completado:
            ya_completados.append(muestra.protocolo)
            continue

        if muestra.estado == EstadoMuestra.anulado:
            ya_anuladas.append(muestra.protocolo)
            continue

        if muestra.estado == EstadoMuestra.pendiente_anulacion:
            ya_anuladas.append(muestra.protocolo)
            continue

        if muestra.estado == EstadoMuestra.eliminado:
            ya_anuladas.append(muestra.protocolo)
            continue

        if muestra.tipo_estudio in (TIPO_LACTOKIT, TIPO_SIBOKIT):
            no_encontrados.append(r.test_id)
            continue

        # Si ya tiene resultados cargados, no se pisa. Excepcion: un error de equipo
        # previo ya consumio el intento y la siguiente lectura puede reemplazarlo.
        reprocesa_error_equipo = _puede_reemplazar_error_equipo(muestra)
        if muestra.resultado_cargado_en is not None and not reprocesa_error_equipo:
            requieren_reinicio.append(muestra.protocolo)
            continue

        # Si tiene intentos previos, viene de un reinicio: es un reintento.
        es_reintento = muestra.intentos_fallidos > 0
        estado_anterior = muestra.estado
        intentos_anteriores = muestra.intentos_fallidos
        valores_anteriores = None
        if reprocesa_error_equipo:
            valores_anteriores = {
                "basal_co2": muestra.resultado_basal_co2,
                "post_co2": muestra.resultado_post_co2,
                "basal_delta": muestra.resultado_basal_delta,
                "post_delta": muestra.resultado_post_delta,
                "test_value": muestra.resultado_test_value,
                "cargado_en": muestra.resultado_cargado_en,
            }

        # Cargar los valores del resultado
        muestra.resultado_basal_co2 = r.basal_co2
        muestra.resultado_post_co2 = r.post_co2
        muestra.resultado_basal_delta = r.basal_delta
        muestra.resultado_post_delta = r.post_delta
        muestra.resultado_test_value = r.test_value
        muestra.resultado_cargado_en = ahora

        envio_bacon = False
        if r.tiene_error_equipo:
            muestra.tiene_error = True
            muestra.intentos_fallidos += 1
            if muestra.intentos_fallidos >= 2:
                muestra.estado = EstadoMuestra.pendiente_anulacion
                pendientes_anulacion.append(muestra.protocolo)
                accion = "txt_error_pendiente_anulacion"
                # No se informa a BACON hasta que el usuario confirme la anulacion.
            else:
                con_error_equipo.append(muestra.protocolo)
                accion = "txt_error_equipo"
        else:
            muestra.estado = EstadoMuestra.en_validacion
            muestra.tiene_error = False
            if es_reintento:
                cargados_reintentando.append(muestra.protocolo)
            else:
                cargados_ok.append(muestra.protocolo)
            accion = "txt_resultado_cargado"

        registrar_auditoria(
            db,
            accion=accion,
            muestra=muestra,
            usuario_id=usuario_id,
            estado_anterior=estado_anterior,
            estado_nuevo=muestra.estado,
            detalle="Carga de resultados desde TXT",
            datos={
                "basal_co2": r.basal_co2,
                "post_co2": r.post_co2,
                "basal_delta": r.basal_delta,
                "post_delta": r.post_delta,
                "test_value": r.test_value,
                "tiene_error_equipo": r.tiene_error_equipo,
                "intentos_anteriores": intentos_anteriores,
                "intentos_nuevos": muestra.intentos_fallidos,
                "envio_bacon": envio_bacon,
                "reprocesa_error_equipo_previo": reprocesa_error_equipo,
                "valores_anteriores": valores_anteriores,
            },
        )

    db.commit()

    # TXT distinto al anterior y ya procesado: se guarda como "último" (reemplaza al previo).
    _guardar_ultima_firma(firma)

    return {
        "cargadosOk": cargados_ok,
        "cargadosReintentando": cargados_reintentando,
        "conErrorEquipo": con_error_equipo,
        "anuladas": anuladas,
        "pendientesAnulacion": pendientes_anulacion,
        "noEncontrados": no_encontrados,
        "yaCompletados": ya_completados,
        "yaAnuladas": ya_anuladas,
        "requierenReinicio": requieren_reinicio,
        "controles": parseado.controles,
        "erroresParseo": parseado.errores,
        "txtDuplicado": False,
    }
