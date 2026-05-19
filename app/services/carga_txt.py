from datetime import datetime
from sqlalchemy.orm import Session

from app.models import EstadoMuestra, Muestra
from app.services.txt_parser import parsear_txt


def cargar_resultados_txt(db: Session, contenido: str) -> dict:
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

        tuvo_error_previo = muestra.tiene_error

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
            else:
                con_error_equipo.append(muestra.protocolo)
        else:
            muestra.estado = EstadoMuestra.en_validacion
            muestra.tiene_error = False
            if tuvo_error_previo:
                cargados_reintentando.append(muestra.protocolo)
            else:
                cargados_ok.append(muestra.protocolo)

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
