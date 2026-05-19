import httpx
from app.config import get_settings

# Headers requeridos por BACON para que no rechace requests que no vienen de un navegador.
BACON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}


async def obtener_muestras_enviadas() -> list[dict]:
    """
    Consulta a BACON las muestras con estado=logistica (enviadas).
    El token se guarda en el servidor, nunca se expone al front.
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{settings.bacon_api_url}/getSerialNumbers",
            params={
                "token": settings.bacon_token,
                "estado": "logistica",
            },
            headers=BACON_HEADERS,
        )
        response.raise_for_status()
        data = response.json()

        # BACON puede devolver un dict de error en vez de lista
        if isinstance(data, dict) and data.get("type") == "danger":
            raise Exception(f"Error de BACON: {data.get('message', 'desconocido')}")

        return data


async def validar_taukit_en_bacon(numero_serie: str) -> dict | None:
    """
    Busca un TauKit específico en las muestras enviadas de BACON.
    Retorna los datos de la muestra si existe, None si no.
    """
    muestras = await obtener_muestras_enviadas()
    for m in muestras:
        if m.get("numero_serie") == numero_serie:
            return m
    return None


async def marcar_recibido_en_bacon(numero_serie: str) -> dict | None:
    """
    Notifica a BACON que un TauKit fue recibido en el laboratorio.
    Cambia el estado de 'Logística' (enviado) a 'Lectura' (recibido).
    Retorna la respuesta de BACON o None si falló.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.bacon_api_url}/cambiarEstadoRecibido",
                json={
                    "token": settings.bacon_token,
                    "numero_serie": numero_serie,
                },
                headers={
                    **BACON_HEADERS,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                print(f"[BACON] TauKit {numero_serie}: {data.get('data', {}).get('estado_anterior')} → {data.get('data', {}).get('estado_actual')}")
            return data
    except Exception as e:
        # No bloqueamos el ingreso si BACON falla al cambiar estado.
        # Se loguea para monitoreo pero la muestra se ingresa igual.
        print(f"[BACON] Error al marcar recibido {numero_serie}: {e}")
        return None
