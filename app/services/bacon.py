import httpx
import asyncio

from app.config import get_settings

BACON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "es-ES,es;q=0.9",
}


async def obtener_muestras_enviadas() -> list[dict]:
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

        if isinstance(data, dict) and data.get("type") == "danger":
            raise Exception(f"Error de BACON: {data.get('message', 'desconocido')}")

        return data


async def validar_taukit_en_bacon(numero_serie: str) -> dict | None:
    muestras = await obtener_muestras_enviadas()
    for muestra in muestras:
        if muestra.get("numero_serie") == numero_serie:
            return muestra
    return None


async def marcar_recibido_en_bacon(numero_serie: str) -> dict:
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
            if response.status_code >= 400:
                cuerpo = response.text[:500]
                print(
                    f"[BACON] cambiarEstadoRecibido {numero_serie} -> HTTP "
                    f"{response.status_code}. Respuesta BACON: {cuerpo!r}"
                )
                return {
                    "success": False,
                    "status": response.status_code,
                    "error": f"BACON respondio HTTP {response.status_code}: {cuerpo}",
                    "raw": cuerpo,
                }
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                print(f"[BACON] Error al marcar recibido {numero_serie}: {data}")
                return {
                    "success": False,
                    "error": data.get("message") or data.get("error") or "BACON rechazo el cambio de estado",
                    "raw": data,
                }
            if isinstance(data, dict) and data.get("success"):
                print(f"[BACON] TauKit {numero_serie}: estado cambiado a recibido")
            return data
    except Exception as exc:
        print(f"[BACON] Error al marcar recibido {numero_serie}: {exc}")
        return {"success": False, "error": str(exc)}


async def subir_pdf_a_bacon(numero_serie: str, pdf_bytes: bytes) -> dict | None:
    pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
    print(f"[BACON] PDF generado para TauKit {numero_serie}: {pdf_size_mb:.2f}MB")

    if len(pdf_bytes) > 10 * 1024 * 1024:
        print(f"[BACON] PDF de {numero_serie} supera el limite de 10MB")
        return None

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.bacon_api_url}/subirResultadoPDF",
                data={
                    "token": settings.bacon_token,
                    "numero_serie": numero_serie,
                },
                files={
                    "archivo_pdf": (f"{numero_serie}.pdf", pdf_bytes, "application/pdf"),
                },
                headers={
                    "User-Agent": BACON_HEADERS["User-Agent"],
                    "Accept": BACON_HEADERS["Accept"],
                    "Accept-Language": BACON_HEADERS["Accept-Language"],
                },
            )
            if response.status_code >= 400:
                cuerpo = response.text[:500]
                print(
                    f"[BACON] subirResultadoPDF {numero_serie} -> HTTP "
                    f"{response.status_code}. Respuesta BACON: {cuerpo!r}"
                )
                return {
                    "success": False,
                    "error": f"BACON respondio HTTP {response.status_code}: {cuerpo}",
                    "raw": cuerpo,
                }
            data = response.json()
            if isinstance(data, dict) and (
                data.get("success") is False or data.get("type") == "danger"
            ):
                print(f"[BACON] Error al subir PDF de {numero_serie}: {data}")
                return {
                    "success": False,
                    "error": data.get("message") or data.get("error") or "BACON rechazo el PDF",
                    "raw": data,
                }
            print(f"[BACON] PDF subido para TauKit {numero_serie}: {data}")
            return data
    except Exception as exc:
        print(f"[BACON] Error al subir PDF de {numero_serie}: {exc}")
        return {"success": False, "error": str(exc)}


def _extraer_archivos_pdf_verificacion(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("data", "pdfs", "archivos", "resultados"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


async def verificar_pdf_en_bacon(
    numero_serie: str,
    intentos: int = 3,
    espera_segundos: float = 1.0,
) -> dict:
    settings = get_settings()
    nombre_esperado = f"{numero_serie}.pdf".lower()

    for intento in range(1, intentos + 1):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{settings.bacon_api_url}/verificarPDF",
                    params={"token": settings.bacon_token},
                    headers=BACON_HEADERS,
                )
                response.raise_for_status()
                data = response.json()
                archivos = _extraer_archivos_pdf_verificacion(data)
                for archivo in archivos:
                    nombre = str(archivo.get("nombre") or "").lower()
                    url = str(archivo.get("url") or "").lower()
                    if nombre == nombre_esperado or url.endswith(f"/{nombre_esperado}"):
                        print(f"[BACON] PDF verificado para {numero_serie}: {archivo}")
                        return {
                            "success": True,
                            "nombre_esperado": f"{numero_serie}.pdf",
                            "archivo": archivo,
                            "raw": data,
                        }

                if intento < intentos:
                    await asyncio.sleep(espera_segundos)
                    continue
                return {
                    "success": False,
                    "error": f"No se encontro {numero_serie}.pdf en verificarPDF",
                    "nombre_esperado": f"{numero_serie}.pdf",
                    "raw": data,
                }
        except Exception as exc:
            if intento < intentos:
                await asyncio.sleep(espera_segundos)
                continue
            print(f"[BACON] Error al verificar PDF de {numero_serie}: {exc}")
            return {"success": False, "error": str(exc), "nombre_esperado": f"{numero_serie}.pdf"}
