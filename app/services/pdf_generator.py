"""
Generador de informe PDF — Port del informePdf.ts del front.
Usa fpdf2 (Python puro, sin dependencias nativas).
"""
import os
from io import BytesIO
from fpdf import FPDF

from app.models import Muestra

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
HEADER_IMG = os.path.join(ASSETS_DIR, "header-tesla.png")
FIRMA_IMG = os.path.join(ASSETS_DIR, "firma-pucci.png")


def _fmt_fecha_informe(fecha_str: str) -> str:
    """'YYYY-MM-DD HH:mm' → 'DD/MM/YYYY HH:mm'"""
    if not fecha_str:
        return ""
    parts = fecha_str.split(" ")
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ""
    y, m, d = date_part.split("-") if "-" in date_part else ("", "", "")
    return f"{d}/{m}/{y} {time_part}".strip()


def _fmt_fecha_corta(fecha_str: str) -> str:
    """'YYYY-MM-DD' → 'DD-MM-YYYY'"""
    if not fecha_str or "-" not in fecha_str:
        return fecha_str or ""
    y, m, d = fecha_str.split("-")
    return f"{d}-{m}-{y}"


def generar_informe_pdf(muestra: Muestra) -> bytes:
    """
    Genera el PDF del informe de una muestra completada.
    Retorna los bytes del PDF.
    """
    if muestra.resultado_test_value is None:
        raise ValueError("La muestra no tiene resultados cargados")

    resultado_texto = "Positivo" if muestra.resultado_test_value > 5 else "Negativo"
    paciente_nombre = f"{muestra.paciente_apellido} {muestra.paciente_nombre}".upper()
    fecha_ingreso = muestra.fecha_ingreso.strftime("%Y-%m-%d %H:%M") if muestra.fecha_ingreso else ""

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    page_w = 210
    margin_l = 20
    margin_r = 20
    content_w = page_w - margin_l - margin_r

    y = 12

    # ============================================
    # CABECERA
    # ============================================
    if os.path.exists(HEADER_IMG):
        # Calcular aspect ratio del header
        pdf.image(HEADER_IMG, x=margin_l, y=y, w=content_w)
        # Estimar altura del header (aspect ratio ~8:1)
        header_h = content_w / 8
        y += header_h + 6
    else:
        y += 20

    # ============================================
    # DATOS DEL PACIENTE
    # ============================================
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)

    # Fila 1: Paciente + Página
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Paciente : ", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, paciente_nombre)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(page_w - margin_r - 30, y)
    pdf.cell(30, 5, "Página 1 de 1", align="R")
    y += 5

    # Fila 2: Protocolo + Ingreso
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Protocolo Nº : ", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, muestra.protocolo)
    pdf.set_font("Helvetica", "B", 10)
    ingreso_texto = f"Ingreso : {_fmt_fecha_informe(fecha_ingreso)}"
    pdf.set_xy(page_w - margin_r - 60, y)
    pdf.cell(60, 5, ingreso_texto, align="R")
    pdf.set_font("Helvetica", "", 10)
    y += 5

    # Fila 3: DNI
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Documento:", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, f"DNI {muestra.paciente_dni}")
    pdf.set_font("Helvetica", "", 10)
    y += 6

    # Disclaimer
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 3.5, "El presente informe es orientativo, no determinante y realizado para que lo interprete y evalúe el Médico solicitante, quien")
    y += 3.5
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 3.5, "tendrá en cuenta su Historia Clínica. Evite autodiagnosticarse.")
    y += 5

    # Línea separadora
    pdf.set_draw_color(0)
    pdf.set_line_width(0.3)
    pdf.line(margin_l, y, page_w - margin_r, y)
    y += 5

    # Encabezado de tabla
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(margin_l, y)
    pdf.cell(60, 4, "Determinación")
    pdf.cell(25, 4, "Resultado")
    pdf.cell(20, 4, "Unidad")
    pdf.set_xy(page_w - margin_r - 45, y)
    pdf.cell(45, 4, "Valores de Referencia", align="R")
    y += 2

    pdf.line(margin_l, y, page_w - margin_r, y)
    y += 8

    # ============================================
    # SECCIÓN DE RESULTADOS
    # ============================================
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "HELICOBACTER PYLORI AIRE ESPIRADO")
    y += 5

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 4, "Valoracion de 13CO2 por espectroscopia infraroja")
    y += 8

    # Campos de datos
    col_valor = 100
    filas = [
        ("Código TAUKIT", muestra.codigo_taukit, True),
        ("Fecha de toma de muestra", _fmt_fecha_corta(muestra.fecha_toma_muestra), False),
        ("Valor de lectura basal", f"{muestra.resultado_basal_delta:.1f}" if muestra.resultado_basal_delta is not None else "", False),
        ("Valor de lectura post 30 minut", f"{muestra.resultado_post_delta:.1f}" if muestra.resultado_post_delta is not None else "", False),
    ]

    pdf.set_font("Helvetica", "", 10)
    for label, valor, bold in filas:
        pdf.set_xy(margin_l, y)
        pdf.cell(0, 5, label)
        pdf.set_font("Helvetica", "B" if bold else "", 10)
        pdf.set_xy(col_valor, y)
        pdf.cell(0, 5, valor)
        pdf.set_font("Helvetica", "", 10)
        y += 5.5

    # Incremento sobre basal + valores de referencia
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Incremento sobre basal")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(col_valor, y)
    pdf.cell(0, 5, str(muestra.resultado_test_value))
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(page_w - margin_r - 45, y)
    pdf.cell(45, 4, "Hasta 5 : Negativo", align="R")
    y += 4.5
    pdf.set_xy(page_w - margin_r - 45, y)
    pdf.cell(45, 4, "Mayor de 5: Positivo", align="R")
    y += 7

    # Resultado
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Resultado")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(col_valor, y)
    pdf.cell(0, 5, resultado_texto)
    y += 8

    # Muestra recibida
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 4, f"Muestra recibida: {fecha_ingreso}")

    # ============================================
    # PIE
    # ============================================
    footer_line_y = 272

    # Firma
    if os.path.exists(FIRMA_IMG):
        pdf.image(FIRMA_IMG, x=page_w - margin_r - 42, y=footer_line_y - 48, w=40)

    pdf.set_draw_color(0)
    pdf.set_line_width(0.3)
    pdf.line(margin_l, footer_line_y, page_w - margin_r, footer_line_y)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(margin_l, footer_line_y - 15)
    pdf.cell(0, 3, "Este protocolo fue validado y firmado electrónicamente por:")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(page_w - margin_r - 42, footer_line_y - 16)
    pdf.cell(40, 3, "Lic. Jorge E.R.Pucci", align="R")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(page_w - margin_r - 42, footer_line_y - 10)
    pdf.cell(40, 3, "M.P. 3280  CPQ", align="R")

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(margin_l, footer_line_y + 3)
    pdf.cell(0, 3, "El presente documento es copia fiel del original que se encuentra alojado en servidores.")

    # fpdf2 puede devolver bytearray; httpx multipart espera bytes o file-like.
    return bytes(pdf.output())
