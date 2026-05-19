import httpx

def testear_endpoint_tesla():
    # La URL exacta con el token 
    url = "https://demob.bacontrack.com.ar/api/getSerialNumbers"
    params = {
        "token": "6f81d766-bbc8-4b49-b279-24c4c2528b09",
        "estado": "logistica"
    }
    
    # Los headers de simulación 
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    
    print(f"Haciendo petición GET a: {url}...")
    
    try:
        # Usamos httpx porque es la librería que está usando el backend 
        with httpx.Client(headers=headers, timeout=10.0) as client:
            response = client.get(url, params=params)
            
            print("\n--- RESULTADO DE LA PRUEBA ---")
            print(f"Código de estado HTTP: {response.status_code}")
            
            # Intentamos ver si devolvió JSON (datos o error de Imunify)
            try:
                print("Respuesta del servidor (JSON):")
                print(response.json())
            except Exception:
                print("La respuesta no es JSON. Contenido crudo:")
                print(response.text[:500]) # Muestra los primeros 500 caracteres (por si devuelve el HTML de Imunify)
                
    except httpx.ConnectError:
        print("\n[ERROR]: No se pudo conectar al servidor. Posible bloqueo duro de IP (Server disconnected).")
    except Exception as e:
        print(f"\n[ERROR inesperado]: {e}")

if __name__ == "__main__":
    testear_endpoint_tesla()