"""
Parser de TXT del HeliFan — port del parser TypeScript.
"""

from dataclasses import dataclass, field


@dataclass
class ResultadoTxt:
    test_id: str
    basal_co2: float
    post_co2: float
    basal_delta: float
    post_delta: float
    test_value: float
    tiene_error_equipo: bool  # postDelta <= -9999


@dataclass
class ParseResult:
    resultados: list[ResultadoTxt] = field(default_factory=list)
    controles: int = 0
    errores: int = 0
    total_filas_muestra: int = 0


def _parse_num(s: str) -> float:
    return float(s.replace(",", "."))


def _es_test_id_valido(test_id: str) -> bool:
    t = test_id.strip()
    if not t:
        return False
    if "CONTROL" in t.upper():
        return False
    if ".." in t:
        return False
    return True


def parsear_txt(contenido: str) -> ParseResult:
    lineas = [l.rstrip() for l in contenido.splitlines() if l.strip()]
    result = ParseResult()

    basal_pendiente: dict | None = None

    for i, linea in enumerate(lineas):
        tokens = linea.split()
        if not tokens:
            continue

        try:
            t_min = int(tokens[0])
        except ValueError:
            continue  # Header u otra línea no numérica

        # --- Minuto 0: basal ---
        if t_min == 0:
            if len(tokens) < 5:
                result.errores += 1
                basal_pendiente = None
                continue

            try:
                basal_co2 = _parse_num(tokens[1])
                basal_delta = _parse_num(tokens[2])
                test_value = _parse_num(tokens[3])
            except (ValueError, IndexError):
                result.errores += 1
                basal_pendiente = None
                continue

            test_id = " ".join(tokens[4:])
            result.total_filas_muestra += 1

            if not _es_test_id_valido(test_id):
                result.controles += 1
                basal_pendiente = None
                continue

            basal_pendiente = {
                "test_id": test_id.strip(),
                "basal_co2": basal_co2,
                "basal_delta": basal_delta,
                "test_value": test_value,
            }
            continue

        # --- Minuto 30: post ---
        if t_min == 30:
            if not basal_pendiente:
                continue

            if len(tokens) < 3:
                result.errores += 1
                basal_pendiente = None
                continue

            try:
                post_co2 = _parse_num(tokens[1])
                post_delta = _parse_num(tokens[2])
            except (ValueError, IndexError):
                result.errores += 1
                basal_pendiente = None
                continue

            result.resultados.append(ResultadoTxt(
                test_id=basal_pendiente["test_id"],
                basal_co2=basal_pendiente["basal_co2"],
                post_co2=post_co2,
                basal_delta=basal_pendiente["basal_delta"],
                post_delta=post_delta,
                test_value=basal_pendiente["test_value"],
                tiene_error_equipo=post_delta <= -9999,
            ))
            basal_pendiente = None

    return result
