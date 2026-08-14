TIPO_TAUKIT = "taukit"
TIPO_LACTOKIT = "lactokit"
TIPO_SIBOKIT = "sibokit"

ESTUDIO_TAUKIT_CODIGO = "001"
ESTUDIO_LACTOKIT_CODIGO = "002"
ESTUDIO_SIBOKIT_CODIGO = "003"

ESTUDIO_TAUKIT_NOMBRE = "Helicobacter Pylori (Urea-13C)"
ESTUDIO_LACTOKIT_NOMBRE = "Lactokit"
ESTUDIO_SIBOKIT_NOMBRE = "Sibokit"


def tipo_estudio_desde_codigo(codigo: str) -> str:
    codigo_limpio = (codigo or "").strip()
    if codigo_limpio.startswith("1"):
        return TIPO_TAUKIT
    if codigo_limpio.startswith("2"):
        return TIPO_LACTOKIT
    if codigo_limpio.startswith("3"):
        return TIPO_SIBOKIT
    raise ValueError("El codigo debe comenzar con 1 (Taukit), 2 (Lactokit) o 3 (Sibokit)")


def codigo_estudio_para_tipo(tipo_estudio: str) -> str:
    if tipo_estudio == TIPO_LACTOKIT:
        return ESTUDIO_LACTOKIT_CODIGO
    if tipo_estudio == TIPO_SIBOKIT:
        return ESTUDIO_SIBOKIT_CODIGO
    return ESTUDIO_TAUKIT_CODIGO


def nombre_estudio_para_tipo(tipo_estudio: str) -> str:
    if tipo_estudio == TIPO_LACTOKIT:
        return ESTUDIO_LACTOKIT_NOMBRE
    if tipo_estudio == TIPO_SIBOKIT:
        return ESTUDIO_SIBOKIT_NOMBRE
    return ESTUDIO_TAUKIT_NOMBRE
