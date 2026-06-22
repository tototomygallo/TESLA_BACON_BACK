from datetime import datetime
from sqlalchemy.orm import Session

from app.models import EstadoMuestra, Muestra
from app.services.auditoria import registrar_auditoria
from app.services.estudios import TIPO_LACTOKIT
from app.services.txt_parser import parsear_txt


def cargar_resultados_txt(db: Session, contenido: str, usuario_id: str | None = None) -> dict:
    """
    Parsea el TXT del HeliFan y carga resultados en las muestras correspondientes.
    Misma lógica que el mockApi del front.
    """
    parseado = parsear_txt(contenido)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    cargados_ok: list[str] = []
    cargados_reintentando: list[str] = []
    con_error_equipo: list[str] = []
    anuladas: list[str] = []
    no_encontrados: list[str] = []
    ya_completados: list[str] = []
    ya_anuladas: list[str] = []

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

        if muestra.estado == EstadoMuestra.eliminado:
            ya_anuladas.append(muestra.protocolo)
            continue

        if muestra.tipo_estudio == TIPO_LACTOKIT:
            no_encontrados.append(r.test_id)
            continue

        tuvo_error_previo = muestra.tiene_error
        estado_anterior = muestra.estado
        intentos_anteriores = muestra.intentos_fallidos

        # Cargar los valores del resultado
        muestra.resultado_basal_co2 = r.basal_co2
        muestra.resultado_post_co2 = r.post_co2
        muestra.resultado_basal_delta = r.basal_delta
        muestra.resultado_post_delta = r.post_delta
        muestra.resultado_test_value = r.test_value
        muestra.resultado_cargado_en = ahora

        if r.tiene_error_equipo:
            muestra.tiene_error = True
            muestra.intentos_fallidos += 1
            if muestra.intentos_fallidos >= 2:
                muestra.estado = EstadoMuestra.anulado
                anuladas.append(muestra.protocolo)
                accion = "txt_error_anulado"
            else:
                con_error_equipo.append(muestra.protocolo)
                accion = "txt_error_equipo"
        else:
            muestra.estado = EstadoMuestra.en_validacion
            muestra.tiene_error = False
            if tuvo_error_previo:
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
            },
        )

    db.commit()

    return {
        "cargadosOk": cargados_ok,
        "cargadosReintentando": cargados_reintentando,
        "conErrorEquipo": con_error_equipo,
        "anuladas": anuladas,
        "noEncontrados": no_encontrados,
        "yaCompletados": ya_completados,
        "yaAnuladas": ya_anuladas,
        "controles": parseado.controles,
        "erroresParseo": parseado.errores,
    }
