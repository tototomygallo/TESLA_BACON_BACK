TIPO_TAUKIT = "taukit"
TIPO_LACTOKIT = "lactokit"

ESTUDIO_TAUKIT_CODIGO = "001"
ESTUDIO_LACTOKIT_CODIGO = "002"

ESTUDIO_TAUKIT_NOMBRE = "Helicobacter Pylori (Urea-13C)"
ESTUDIO_LACTOKIT_NOMBRE = "Lactokit"


def tipo_estudio_desde_codigo(codigo: str) -> str:
    codigo_limpio = (codigo or "").strip()
    if codigo_limpio.startswith("1"):
        return TIPO_TAUKIT
    if codigo_limpio.startswith("2"):
        return TIPO_LACTOKIT
    raise ValueError("El codigo debe comenzar con 1 (Taukit) o 2 (Lactokit)")


def codigo_estudio_para_tipo(tipo_estudio: str) -> str:
    if tipo_estudio == TIPO_LACTOKIT:
        return ESTUDIO_LACTOKIT_CODIGO
    return ESTUDIO_TAUKIT_CODIGO


def nombre_estudio_para_tipo(tipo_estudio: str) -> str:
    if tipo_estudio == TIPO_LACTOKIT:
        return ESTUDIO_LACTOKIT_NOMBRE
    return ESTUDIO_TAUKIT_NOMBRE
