import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Muestra, SibokitResultado

CO2_MINIMO_VALIDO = 1.4
CO2_REFERENCIA = 5.5
TIEMPOS_SIBOKIT = [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165]

SIBOKIT_DESCRIPCIONES = {
    "1": "SE DEBE REPETIR LA PRUEBA POR MALA PRÁCTICA EN LA RECOJIDA DE LAS MUESTRAS DE ALIENTO (CO2 < 1,4%).",
    "2": "VALORES DE HIDROGENO COMPATIBLES CON SOBRECRECIMIENTO BACTERIANO EN EL INTESTINO DELGADO (SIBO).",
    "3": "VALORES DE METANO COMPATIBLES CON SOBRECRECIMIENTO METANOGENICO EN EL INTESTINO - ARQUEAS (IMO).",
    "4": "VALORES DE HIDROGENO COMPATIBLES CON SOBRECRECIMIENTO BACTERIANO EN EL INSTESTINO DELGADO (SIBO). VALORES DE METANO COMPATIBLES CON SOBRECRECIMIENTO METANOGENICO EN EL INTESTINO - ARQUEAS (IMO).",
    "5": "RESULTADO VALORES DE HIDROGENO Y METANO NO COMPATIBLES CON SOBRECRECIMIENTO BACTERIANO.",
}
SIBOKIT_NOTA_INSUFICIENTES = (
    "VALORES HIDROGENO Y METANO INDETERMINADOS POR MUESTRAS INSUFICIENTES (MI), "
    "EN VARIAS RECOGIDAS DE ALIENTO (+3) - SE SUGIERE REPETIR LA PRUEBA."
)
LETRA_BASE = {"2": "b", "3": "c", "4": "d", "5": "e"}


@dataclass(frozen=True)
class ValoracionSibokit:
    valoracion: str
    descripcion: str
    nota_adicional: str | None = None


def _numero(valor: Any) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
        if not valor:
            return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"Valor numérico inválido: {valor}")


def _normalizar(h2: list[Any], ch4: list[Any], co2: list[Any], confirmar: bool) -> tuple[list, list, list]:
    limite = len(TIEMPOS_SIBOKIT)
    if not (len(h2) == len(ch4) == len(co2)):
        raise ValueError("Cada toma debe contener H2, CH4 y CO2")
    if confirmar and len(h2) != limite:
        raise ValueError("Sibokit requiere exactamente 12 valores por gas para confirmar")
    if not confirmar and len(h2) > limite:
        raise ValueError("Sibokit permite hasta 12 tomas")
    nh2, nch4, nco2 = ([_numero(v) for v in valores] for valores in (h2, ch4, co2))
    if any(v is None for fila in zip(nh2, nch4, nco2) for v in fila):
        raise ValueError("No se puede guardar una toma incompleta")
    return nh2, nch4, nco2


def factores_correccion(co2: list[float]) -> list[float | None]:
    # Fórmula documentada en el informe del analizador: corrección a 5,5 % de CO2.
    return [round(CO2_REFERENCIA / valor, 2) if valor > 0 else None for valor in co2]


def calcular_valoracion_sibokit(h2_raw: list[Any], ch4_raw: list[Any], co2_raw: list[Any]) -> ValoracionSibokit:
    h2, ch4, co2 = _normalizar(h2_raw, ch4_raw, co2_raw, True)
    invalidos = [valor <= CO2_MINIMO_VALIDO for valor in co2]
    cantidad_invalidos = sum(invalidos)
    if cantidad_invalidos >= 6:
        return ValoracionSibokit("1", SIBOKIT_DESCRIPCIONES["1"])

    indices_validos = [i for i, invalido in enumerate(invalidos) if not invalido]
    basal_pos = 0
    if len(indices_validos) > 1:
        primero, segundo = indices_validos[:2]
        if h2[primero] >= 10 and h2[segundo] < h2[primero]:
            basal_pos = 1
    basal_idx = indices_validos[basal_pos]
    h2_sibo = any(
        i <= 6 and i > basal_idx and h2[i] - h2[basal_idx] >= 20
        for i in indices_validos
    )
    ch4_imo = any(ch4[i] >= 10 for i in indices_validos)
    base = "4" if h2_sibo and ch4_imo else "2" if h2_sibo else "3" if ch4_imo else "5"
    if 3 <= cantidad_invalidos <= 5:
        return ValoracionSibokit(
            f"6{LETRA_BASE[base]}", SIBOKIT_DESCRIPCIONES[base], SIBOKIT_NOTA_INSUFICIENTES
        )
    return ValoracionSibokit(base, SIBOKIT_DESCRIPCIONES[base])


def guardar_resultados_sibokit(db: "Session", protocolo: str, h2: list[Any], ch4: list[Any], co2: list[Any], confirmar: bool = True, usuario_id: str | None = None) -> "Muestra":
    from app.models import EstadoMuestra, Muestra, SibokitResultado
    from app.services.auditoria import registrar_auditoria

    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.tipo_estudio != "sibokit":
        raise ValueError("La muestra no corresponde a Sibokit")
    if muestra.estado in (EstadoMuestra.completado, EstadoMuestra.anulado, EstadoMuestra.cancelado, EstadoMuestra.eliminado):
        raise ValueError("La muestra no se encuentra en un estado válido para recibir resultados")
    nh2, nch4, nco2 = _normalizar(h2, ch4, co2, confirmar)
    calculo = calcular_valoracion_sibokit(nh2, nch4, nco2) if confirmar else None
    anterior = muestra.estado
    fila = db.query(SibokitResultado).filter_by(protocolo=protocolo).first()
    if not fila:
        fila = SibokitResultado(protocolo=protocolo, codigo_sibokit=muestra.codigo_taukit)
        db.add(fila)
    fila.codigo_sibokit = muestra.codigo_taukit
    fila.h2, fila.ch4, fila.co2 = map(json.dumps, (nh2, nch4, nco2))
    fila.factor_correccion = json.dumps(factores_correccion(nco2))
    fila.valores_descartados = json.dumps([i for i, valor in enumerate(nco2) if valor <= CO2_MINIMO_VALIDO])
    fila.valoracion = calculo.valoracion if calculo else ""
    fila.descripcion = calculo.descripcion if calculo else ""
    fila.nota_adicional = calculo.nota_adicional if calculo else None
    fila.cargado_en = datetime.now().strftime("%Y-%m-%d %H:%M")
    fila.usuario_id = usuario_id
    muestra.estado = EstadoMuestra.en_validacion if confirmar else EstadoMuestra.en_proceso
    muestra.tiene_error = False
    if not confirmar:
        muestra.pdf_generado = False
        muestra.pdf_generado_en = None
    registrar_auditoria(db, accion="sibokit_resultado_confirmado" if confirmar else "sibokit_resultado_parcial_guardado", muestra=muestra, usuario_id=usuario_id, estado_anterior=anterior, estado_nuevo=muestra.estado, detalle="Carga de resultados Sibokit", datos={"h2": nh2, "ch4": nch4, "co2": nco2, "confirmar": confirmar, "valoracion": fila.valoracion or None})
    db.commit()
    return muestra


def obtener_resultado_sibokit(db: "Session", protocolo: str) -> "SibokitResultado | None":
    from app.models import SibokitResultado
    return db.query(SibokitResultado).filter_by(protocolo=protocolo).first()


def leer_valores_sibokit(resultado: "SibokitResultado | None") -> dict[str, list[Any]] | None:
    if not resultado:
        return None
    return {campo: json.loads(getattr(resultado, campo)) for campo in ("h2", "ch4", "co2", "factor_correccion")}
