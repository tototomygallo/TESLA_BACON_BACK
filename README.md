# TauKits — Backend

API REST para el sistema de gestión de muestras TauKits (Tesla Diagnóstico / BACON).

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Abrí `http://localhost:8000/docs` para ver la documentación interactiva (Swagger).

## Estructura

```
app/
├── main.py              # FastAPI app, CORS, startup, seed de usuarios
├── config.py            # Variables de entorno (.env)
├── database.py          # SQLAlchemy engine + sesión + init
├── models/              # Modelos de base de datos (ORM)
│   └── __init__.py      # Usuario, Muestra, Consecutivo
├── schemas/             # Pydantic schemas (request/response)
│   └── __init__.py      # LoginRequest, MuestraResponse, etc.
├── services/            # Lógica de negocio
│   ├── bacon.py         # Proxy a la API de BACON
│   ├── muestras.py      # CRUD de muestras + validación
│   ├── carga_txt.py     # Carga de TXT del HeliFan
│   ├── txt_parser.py    # Parser del formato del HeliFan
│   └── converters.py    # Modelo DB → Response API
└── routes/              # Endpoints HTTP
    ├── auth.py          # POST /api/auth/login
    ├── bacon_proxy.py   # GET  /api/bacon/muestras-enviadas
    └── muestras.py      # GET/POST /api/muestras/*
```

## Endpoints

| Método | Path | Descripción |
|--------|------|-------------|
| POST   | `/api/auth/login` | Login (`{userId}` → `Usuario`) |
| GET    | `/api/bacon/muestras-enviadas` | Proxy a BACON (estado=logistica) |
| GET    | `/api/muestras` | Listar todas las muestras |
| POST   | `/api/muestras/ingresar-lote` | Ingresar lote de TauKits (`{codigos}`) |
| POST   | `/api/muestras/cargar-txt` | Cargar TXT del HeliFan (body = texto plano) |
| POST   | `/api/muestras/{protocolo}/validar` | Validar muestra (→ completado) |
| POST   | `/api/muestras/{protocolo}/reiniciar` | Reiniciar muestra con error |

## Conectar con el front

En el front (`taukits-frontend`), editá `.env`:

```
VITE_API_MODE=real
VITE_API_BASE_URL=http://localhost:8000/api
```

## Variables de entorno (.env)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BACON_API_URL` | `https://demob.bacontrack.com.ar/api` | URL base de BACON |
| `BACON_TOKEN` | (demo) | Token de acceso a BACON |
| `DATABASE_URL` | `sqlite:///./taukits.db` | Conexión a la BD |
| `SUCURSAL_CODIGO` | `TM` | Código de sucursal (2 letras) |
| `SUCURSAL_NOMBRE` | `Tucumán - Mate de Luna` | Nombre de sucursal |
| `ESTUDIO_CODIGO` | `HU` | Código de estudio por defecto |
| `ESTUDIO_NOMBRE` | `Helicobacter Pylori (Urea-13C)` | Nombre de estudio |

## Base de datos

SQLite por defecto (archivo `taukits.db`, se crea solo). Para producción,
cambiar `DATABASE_URL` a PostgreSQL o SQL Server y remover el
`check_same_thread` en `database.py`.

Los usuarios se crean automáticamente al primer arranque (6 usuarios de prueba).

### Migraciones SQL Server

Si usás `mssql+pyodbc`, aplicá las migraciones de `migrations/` sobre la base
antes de levantar la API. Por ejemplo, si aparece un error en una consulta a
`lab.muestras` filtrando por `bacon_recibido`, ejecutar:

```sql
:r migrations/20260519_add_bacon_flags.sql
```
