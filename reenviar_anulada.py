"""
Reenvía a BACON el informe de UNA muestra anulada que quedó sin subir
(subir PDF + verificar + mail). Uso puntual / one-off.

La muestra sigue quedando 'anulado' localmente; lo que se arregla es el lado
de BACON (sube el PDF, cambia el estado) y el envío del mail.
"""
import asyncio

from app.config import get_settings
from app.database import SessionLocal
from app.models import Muestra
from app.services.muestras import _enviar_informe_anulada

PROTOCOLO = "001-001-00000863"


async def main():
    settings = get_settings()

    # --- Verificación de a qué entorno estás apuntando (por las dudas) ---
    print("BACON_API_URL :", settings.bacon_api_url)
    print("DB_SCHEMA     :", settings.db_schema)
    print("DATABASE      :", settings.database_url.split("@")[-1])
    if "demob" in settings.bacon_api_url:
        print("\n❌ ABORTADO: estás apuntando a BACON DEMO. Esta muestra es de PROD.")
        print("   Cambiá el .env a configuración de producción y volvé a correr.")
        return
    print("-" * 60)

    db = SessionLocal()
    try:
        m = db.query(Muestra).filter_by(protocolo=PROTOCOLO).first()
        if not m:
            print("No se encontró la muestra:", PROTOCOLO)
            return
        if m.estado != "anulado":
            print(f"OJO: estado = {m.estado} (esperaba 'anulado'). Aborto por las dudas.")
            return

        print(f"Reenviando informe anulado de {m.protocolo} / taukit {m.codigo_taukit}...")
        resultado = await _enviar_informe_anulada(m)
        print("Resultado:", resultado)

        if resultado.get("enviado"):
            db.commit()
            mail = "enviado" if resultado.get("mail_enviado") else f"FALLÓ ({resultado.get('mail_advertencia')})"
            print(f"\nOK ✅  PDF subido y verificado en BACON. Mail: {mail}")
        else:
            db.rollback()
            print("\nNO se pudo subir a BACON ❌:", resultado.get("error"))
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
