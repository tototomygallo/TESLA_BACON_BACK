import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import LactokitResultado, Muestra

LACTOKIT_DESCRIPCIONES = {
    "1": "SE DEBE REPETIR LA PRUEBA POR MALA PRÁCTICA EN LA RECOJIDA DE LAS MUESTRAS DE ALIENTO (CO2 < 1,4%)",
    "2": "RESULTADO COMPATIBLE CON MALABSORCION DE LACTOSA CON ELEVACION DE HIDROGENO, SI EL PACIENTE REPORTA SINTOMAS, ENTONCES ESTARIAMOS FRENTE A UNA INTOLERANCIA A LA LACTOSA.",
    "3": "RESULTADO COMPATIBLE CON MALABSORCION DE LACTOSA CON ELEVACION DE METANO, SI EL PACIENTE REPORTA SINTOMAS, ENTONCES ESTARIAMOS FRENTE A UNA INTOLERANCIA A LA LACTOSA.",
    "4": "RESULTADO COMPATIBLE CON MALABSORCION DE LACTOSA CON ELEVACION DE HIDROGENO Y METANO. SI EL PACIENTE REPORTA SINTOMAS, ENTONCES ESTARIAMOS FRENTE A UNA INTOLERANCIA A LA LACTOSA.",
    "5": "RESULTADO NO COMPATIBLE CON MALABORCION DE LACTOSA.",
}

# Texto extra que se agrega debajo de la valoración cuando hay exactamente 3 frascos
# con CO2 < 1,4% (condición "f" -> valoración "6").
LACTOKIT_TEXTO_EXTRA_CO2 = (
    "DEBIDO A QUE VARIAS MUESTRAS CONTENIAN CO2 < 1,4%, SE SUGIERE REPETIR LA PRUEBA."
)

# Letra de la condición (b/c/d/e) según el código base de valoración. Para el caso "f"
# la valoración se guarda como "6" + letra ("6b"/"6c"/"6d"/"6e") para persistir qué
# condición la originó; la API la expone como valoracion="6" + campo `condicion`.
LACTOKIT_LETRA_CONDICION = {"2": "b", "3": "c", "4": "d", "5": "e"}

# Un frasco con CO2 por debajo de este % no representa aire alveolar valido:
# sus valores se descartan del calculo de la valoracion.
CO2_MINIMO_VALIDO = 1.4

# Si el primer frasco valido de un gas supera este valor (ppm) y el segundo valido
# es menor, se toma el segundo como basal (descarta un basal anomalo por mala prep).
BASAL_ELEVADO_PPM = 10


@dataclass(frozen=True)
class ValoracionLactokit:
    valoracion: str
    descripcion: str


def _normalizar_valor(valor: Any) -> float | str | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        limpio = valor.strip().upper()
        if not limpio:
            return None
        if limpio == "MI":
            return "MI"
        valor = limpio.replace(",", ".")
    try:
        return float(valor)
    except (TypeError, ValueError):
        return "MI"


def normalizar_frascos(valores: list[Any]) -> list[float | str | None]:
    normalizados = [_normalizar_valor(v) for v in valores]
    if len(normalizados) != 8:
        raise ValueError("Lactokit requiere exactamente 8 valores por analito")
    return normalizados


def normalizar_frascos_parcial(valores: list[Any]) -> list[float | str | None]:
    normalizados = [_normalizar_valor(v) for v in valores]
    if len(normalizados) > 8:
        raise ValueError("Lactokit permite hasta 8 valores por analito")
    return normalizados


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _frasco_co2_invalido(co2_valor: Any) -> bool:
    """Un frasco con CO2 < 1,4% no representa aire alveolar y se descarta del calculo."""
    return _es_numero(co2_valor) and float(co2_valor) < CO2_MINIMO_VALIDO


def _indice_basal(valores: list[float | str | None]) -> int | None:
    """Indice del frasco basal de un gas. Normalmente el primer frasco valido; si ese
    esta elevado (>= 10 ppm) y el siguiente valido es menor, se usa el siguiente."""
    validos = [i for i, v in enumerate(valores) if _es_numero(v)]
    if not validos:
        return None
    if len(validos) >= 2:
        i0, i1 = validos[0], validos[1]
        if float(valores[i0]) >= BASAL_ELEVADO_PPM and float(valores[i1]) < float(valores[i0]):
            return i1
    return validos[0]


def _max_incremento_h2(h2: list[float | str | None]) -> float | None:
    """Maximo incremento de H2 de un frasco posterior al basal respecto al basal."""
    basal_idx = _indice_basal(h2)
    if basal_idx is None:
        return None
    basal = float(h2[basal_idx])
    incrementos = [float(v) - basal for v in h2[basal_idx + 1:] if _es_numero(v)]
    return max(incrementos) if incrementos else None


def _max_ch4(ch4: list[float | str | None]) -> float | None:
    """Maximo CH4 entre los frascos posteriores al basal (el basal se excluye)."""
    basal_idx = _indice_basal(ch4)
    if basal_idx is None:
        return None
    posteriores = [float(v) for v in ch4[basal_idx + 1:] if _es_numero(v)]
    return max(posteriores) if posteriores else None


def calcular_valoracion_lactokit(
    h2_raw: list[Any],
    ch4_raw: list[Any],
    co2_raw: list[Any],
) -> ValoracionLactokit:
    h2 = normalizar_frascos(h2_raw)
    ch4 = normalizar_frascos(ch4_raw)
    co2 = normalizar_frascos(co2_raw)

    # Frascos invalidos = CO2 < 1,4% (mala calidad de la muestra de aliento).
    invalidos = [_frasco_co2_invalido(c) for c in co2]
    n_invalidos = sum(1 for inv in invalidos if inv)

    # Condicion "a": 4 o mas frascos con CO2 < 1,4% -> mala practica (valoracion 1).
    if n_invalidos >= 4:
        return ValoracionLactokit(
            valoracion="1",
            descripcion=LACTOKIT_DESCRIPCIONES["1"],
        )

    # Condiciones b/c/d/e: los frascos invalidos se excluyen del calculo de H2/CH4
    # (se enmascaran). La tabla y el grafico del informe siguen mostrando todos los
    # valores sin alterar.
    h2_validos = [None if inv else v for v, inv in zip(h2, invalidos)]
    ch4_validos = [None if inv else v for v, inv in zip(ch4, invalidos)]

    max_delta_h2 = _max_incremento_h2(h2_validos)
    max_ch4 = _max_ch4(ch4_validos)
    h2_elevado = max_delta_h2 is not None and max_delta_h2 > 20   # estricto: > 20
    ch4_elevado = max_ch4 is not None and max_ch4 > 10            # estricto: > 10

    if h2_elevado and ch4_elevado:
        base = "4"   # d: b y c en simultaneo
    elif h2_elevado:
        base = "2"   # b: elevacion de H2
    elif ch4_elevado:
        base = "3"   # c: elevacion de CH4
    else:
        base = "5"   # e: no compatible

    # Condicion "f": exactamente 3 frascos con CO2 < 1,4% -> valoracion base (b/c/d/e)
    # mas el texto extra de "repetir prueba" (valoracion 6).
    if n_invalidos == 3:
        return ValoracionLactokit(
            valoracion=f"6{LACTOKIT_LETRA_CONDICION[base]}",
            descripcion=f"{LACTOKIT_DESCRIPCIONES[base]}\n{LACTOKIT_TEXTO_EXTRA_CO2}",
        )

    return ValoracionLactokit(
        valoracion=base,
        descripcion=LACTOKIT_DESCRIPCIONES[base],
    )


def guardar_resultados_lactokit(
    db: "Session",
    protocolo: str,
    h2: list[Any],
    ch4: list[Any],
    co2: list[Any],
    confirmar: bool = True,
    usuario_id: str | None = None,
) -> "Muestra":
    from app.models import EstadoMuestra, LactokitResultado, Muestra
    from app.services.auditoria import registrar_auditoria

    muestra = db.query(Muestra).filter_by(protocolo=protocolo).first()
    if not muestra:
        raise ValueError("Muestra no encontrada")
    if muestra.tipo_estudio != "lactokit":
        raise ValueError("La muestra no corresponde a Lactokit")
    if muestra.estado == EstadoMuestra.completado:
        raise ValueError("La muestra ya esta completada")
    if muestra.estado in (EstadoMuestra.anulado, EstadoMuestra.cancelado):
        raise ValueError("La muestra esta cancelada")

    if confirmar:
        h2_normalizado = normalizar_frascos(h2)
        ch4_normalizado = normalizar_frascos(ch4)
        co2_normalizado = normalizar_frascos(co2)
        resultado = calcular_valoracion_lactokit(h2_normalizado, ch4_normalizado, co2_normalizado)
    else:
        h2_normalizado = normalizar_frascos_parcial(h2)
        ch4_normalizado = normalizar_frascos_parcial(ch4)
        co2_normalizado = normalizar_frascos_parcial(co2)
        resultado = None
    estado_anterior = muestra.estado

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    resultado_db = db.query(LactokitResultado).filter_by(protocolo=protocolo).first()
    if not resultado_db:
        resultado_db = LactokitResultado(
            protocolo=protocolo,
            codigo_lactokit=muestra.codigo_taukit,
        )
        db.add(resultado_db)

    resultado_db.codigo_lactokit = muestra.codigo_taukit
    resultado_db.h2 = json.dumps(h2_normalizado)
    resultado_db.ch4 = json.dumps(ch4_normalizado)
    resultado_db.co2 = json.dumps(co2_normalizado)
    resultado_db.valoracion = resultado.valoracion if resultado else ""
    resultado_db.descripcion = resultado.descripcion if resultado else ""
    resultado_db.cargado_en = ahora
    if confirmar:
        muestra.estado = EstadoMuestra.en_validacion
        muestra.tiene_error = resultado.valoracion == "ERROR"
    else:
        muestra.estado = EstadoMuestra.en_proceso
        muestra.tiene_error = False
        muestra.pdf_generado = False
        muestra.pdf_generado_en = None
    registrar_auditoria(
        db,
        accion="lactokit_resultado_confirmado" if confirmar else "lactokit_resultado_parcial_guardado",
        muestra=muestra,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=muestra.estado,
        detalle=(
            "Carga de resultados Lactokit y calculo automatico de valoracion"
            if confirmar
            else "Guardado parcial de resultados Lactokit"
        ),
        datos={
            "h2": h2_normalizado,
            "ch4": ch4_normalizado,
            "co2": co2_normalizado,
            "confirmar": confirmar,
            "valoracion": resultado.valoracion if resultado else None,
            "descripcion": resultado.descripcion if resultado else None,
        },
    )

    db.commit()
    return muestra


def obtener_resultado_lactokit(db: "Session", protocolo: str) -> "LactokitResultado | None":
    from app.models import LactokitResultado

    return db.query(LactokitResultado).filter_by(protocolo=protocolo).first()


def leer_valores_lactokit(resultado: "LactokitResultado | None") -> dict[str, list[Any]] | None:
    if not resultado:
        return None
    return {
        "h2": json.loads(resultado.h2),
        "ch4": json.loads(resultado.ch4),
        "co2": json.loads(resultado.co2),
    }
