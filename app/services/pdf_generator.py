"""
Generador de informe PDF — Port del informePdf.ts del front.
Usa fpdf2 (Python puro, sin dependencias nativas).
"""
import os
from html import escape
from io import BytesIO
from fpdf import FPDF
from fpdf.fonts import FontFace, TextStyle
from sqlalchemy.orm import object_session

from app.models import Muestra
from app.services.estudios import TIPO_LACTOKIT
from app.services.lactokit import (
    LACTOKIT_DESCRIPCIONES,
    leer_valores_lactokit,
    obtener_resultado_lactokit,
)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
HEADER_IMG = os.path.join(ASSETS_DIR, "header-tesla.png")
FIRMA_IMG = os.path.join(ASSETS_DIR, "firma-pucci.png")
LACTOKIT_IMG = os.path.join(ASSETS_DIR, "lactokit.jpg")


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


def generar_informe_pdf(muestra: Muestra, validacion_clinica: bool = True) -> bytes:
    """
    Genera el PDF del informe de una muestra completada o anulada.
    Retorna los bytes del PDF.
    """
    if muestra.tipo_estudio == TIPO_LACTOKIT:
        return _generar_informe_lactokit_pdf(muestra, validacion_clinica)

    if muestra.resultado_test_value is None:
        raise ValueError("La muestra no tiene resultados cargados")

    resultado_texto = "Positivo" if muestra.resultado_test_value > 5 else "Negativo"
    if not validacion_clinica:
        resultado_texto = "Se sugiere repetir el estudio"
    post_delta_texto = (
        f"{muestra.resultado_post_delta:.1f}"
        if muestra.resultado_post_delta is not None
        else ""
    )
    if not validacion_clinica:
        post_delta_texto = (
            "Resultado no valorable"
        )
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

    # Fila 3: Solicitante
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Solicitado por:", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "LABORATORIOS BACON SAIC")
    pdf.set_font("Helvetica", "", 10)
    y += 5

    # Fila 4: DNI
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
    pdf.cell(45, 4, "VALORES DE REFERENCIA", align="R")
    y += 5

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
        ("Valor de lectura post 30 minut", post_delta_texto, False),
    ]

    pdf.set_font("Helvetica", "", 10)
    for label, valor, bold in filas:
        pdf.set_xy(margin_l, y)
        pdf.cell(0, 5, label)
        pdf.set_font("Helvetica", "B" if bold else "", 10)
        pdf.set_xy(col_valor, y)
        if not validacion_clinica and label == "Valor de lectura post 30 minut":
            pdf.multi_cell(36, 3.2, valor, align="C")
            y = max(y + 5.5, pdf.get_y())
        else:
            pdf.cell(0, 5, valor)
            y += 5.5
        pdf.set_font("Helvetica", "", 10)

    # Incremento sobre basal + valores de referencia
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Incremento sobre basal")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(col_valor, y)
    pdf.cell(
        0,
        5,
        "No concluyente"
        if not validacion_clinica
        else f"{muestra.resultado_test_value:.2f}",
    )
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

    if not validacion_clinica:
        pdf.set_text_color(170, 170, 170)
        pdf.set_font("Helvetica", "", 22)
        pdf.set_xy(42, 198)
        pdf.cell(126, 8, "INFORME SIN VALIDACIÓN CLÍNICA", align="C")
        pdf.set_text_color(0, 0, 0)

    # ============================================
    # PIE
    # ============================================
    if not validacion_clinica:
        return bytes(pdf.output())

    footer_line_y = 272

    # Firma
    if os.path.exists(FIRMA_IMG):
        pdf.image(FIRMA_IMG, x=page_w - margin_r - 45, y=footer_line_y - 30, w=35)

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


def _dibujar_cabecera_lactokit(
    pdf: FPDF,
    muestra: Muestra,
    page_w: int,
    margin_l: int,
    margin_r: int,
    y: float,
) -> float:
    content_w = page_w - margin_l - margin_r
    if os.path.exists(HEADER_IMG):
        pdf.image(HEADER_IMG, x=margin_l, y=y, w=content_w)
        y += content_w / 8 + 6
    else:
        y += 20

    paciente_nombre = f"{muestra.paciente_apellido} {muestra.paciente_nombre}".upper()
    fecha_ingreso = muestra.fecha_ingreso.strftime("%Y-%m-%d %H:%M") if muestra.fecha_ingreso else ""

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)

    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Paciente : ", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, paciente_nombre)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(page_w - margin_r - 30, y)
    pdf.cell(30, 5, "Página 1 de 1", align="R")
    y += 5

    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Protocolo Nro. : ", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, muestra.protocolo)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(page_w - margin_r - 60, y)
    pdf.cell(60, 5, f"Ingreso : {_fmt_fecha_informe(fecha_ingreso)}", align="R")
    pdf.set_font("Helvetica", "", 10)
    y += 5

    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Solicitado por:", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "LABORATORIOS BACON SAIC")
    pdf.set_font("Helvetica", "", 10)
    y += 5

    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "Documento:", new_x="END")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, f"DNI {muestra.paciente_dni}")
    pdf.set_font("Helvetica", "", 10)
    y += 6

    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 3.5, "El presente informe es orientativo, no determinante y realizado para que lo interprete y evalúe el Médico solicitante, quien")
    y += 3.5
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 3.5, "tendrá en cuenta su Historia Clínica. Evite autodiagnosticarse.")
    y += 5

    pdf.line(margin_l, y, page_w - margin_r, y)
    return y + 5


def _valor_grafico(valor) -> float | None:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    return None


def _dibujar_grafico_lactokit(
    pdf: FPDF,
    x: float,
    y: float,
    w: float,
    h: float,
    h2: list,
    ch4: list,
) -> float:
    tiempos = [0, 25, 50, 75, 100, 125, 150, 175]
    valores_num = [
        v
        for v in [_valor_grafico(v) for v in h2 + ch4]
        if v is not None
    ]
    max_val = max(160, int(max(valores_num or [0]) + 20))
    if max_val % 20:
        max_val += 20 - (max_val % 20)

    left = x + 12
    top = y + 8
    chart_w = w - 24
    chart_h = h - 18
    bottom = top + chart_h

    pdf.set_font("Helvetica", "B", 7)
    pdf.set_xy(x, y)
    pdf.cell(w, 4, "Concentración de Hidrógeno y Metano en función del tiempo", align="C")

    pdf.set_draw_color(225, 225, 225)
    pdf.set_line_width(0.1)
    for i in range(9):
        gx = left + (chart_w / 8) * i
        pdf.line(gx, top, gx, bottom)
    for valor in range(0, max_val + 1, 20):
        gy = bottom - (valor / max_val) * chart_h
        pdf.line(left, gy, left + chart_w, gy)
        pdf.set_font("Helvetica", "", 5.5)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(x + 1, gy - 1.5)
        pdf.cell(9, 3, str(valor), align="R")

    pdf.set_draw_color(0, 0, 0)
    pdf.line(left, top, left, bottom)
    pdf.line(left, bottom, left + chart_w, bottom)

    def punto(idx: int, valor: float) -> tuple[float, float]:
        px = left + (tiempos[idx] / 175) * chart_w
        py = bottom - (valor / max_val) * chart_h
        return px, py

    def serie(valores: list, color: tuple[int, int, int]) -> None:
        pdf.set_draw_color(*color)
        pdf.set_fill_color(*color)
        anterior = None
        for idx, valor_raw in enumerate(valores):
            valor = _valor_grafico(valor_raw)
            if valor is None:
                anterior = None
                continue
            actual = punto(idx, valor)
            if anterior:
                pdf.line(anterior[0], anterior[1], actual[0], actual[1])
            pdf.ellipse(actual[0] - 0.7, actual[1] - 0.7, 1.4, 1.4, style="F")
            anterior = actual

    serie(h2, (35, 75, 255))
    serie(ch4, (255, 35, 35))

    pdf.set_font("Helvetica", "", 5.8)
    pdf.set_text_color(0, 0, 0)
    for idx, tiempo in enumerate(tiempos):
        px = left + (tiempo / 175) * chart_w
        pdf.set_xy(px - 4, bottom + 1.5)
        pdf.cell(8, 3, str(tiempo), align="C")

    pdf.set_font("Helvetica", "B", 5.8)
    pdf.set_xy(left + chart_w - 12, bottom + 6)
    pdf.cell(16, 3, "Tiempo (min)")

    legend_y = bottom + 8
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(35, 75, 255)
    legend_w = 55
    legend_x = 105 - (legend_w / 2)
    pdf.set_xy(legend_x, legend_y)
    pdf.cell(legend_w, 3, "H2 (ppm) CORREGIDO", align="C")
    pdf.set_text_color(255, 35, 35)
    pdf.set_xy(legend_x, legend_y + 6)
    pdf.cell(legend_w, 3, "CH4 (ppm) CORREGIDO", align="C")
    pdf.set_text_color(0, 0, 0)
    return y + h + 8


def _fmt_lactokit_valor(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:g}"
    return str(valor)


def _descripcion_lactokit_pdf(resultado_lactokit) -> str:
    return LACTOKIT_DESCRIPCIONES.get(
        resultado_lactokit.valoracion,
        resultado_lactokit.descripcion or "",
    )


def _write_html_lactokit(
    pdf: FPDF,
    x: float,
    y: float,
    html: str,
    font_size: float = 8.5,
    paragraph_gap: float = 1.8,
) -> float:
    pdf.set_left_margin(x)
    pdf.set_right_margin(x)
    pdf.set_xy(x, y)
    pdf.write_html(
        html,
        tag_styles={
            "p": TextStyle(
                font_family="Helvetica",
                font_size_pt=font_size,
                color=(0, 0, 0),
                t_margin=0,
                b_margin=paragraph_gap,
            ),
            "b": FontFace(
                family="Helvetica",
                emphasis="B",
                size_pt=font_size,
                color=(0, 0, 0),
            ),
        },
    )
    return pdf.get_y()


def _html_p(texto: str, align: str = "J") -> str:
    return f'<p align="{align}">{escape(texto)}</p>'


def _html_p_rich(partes: list[tuple[str, bool]], align: str = "J") -> str:
    contenido = "".join(
        f"<b>{escape(texto)}</b>" if bold else escape(texto)
        for texto, bold in partes
    )
    return f'<p align="{align}">{contenido}</p>'


def _dibujar_titulo_lactokit(
    pdf: FPDF,
    page_w: int,
    margin_l: int,
    margin_r: int,
    y: float,
) -> float:
    content_w = page_w - margin_l - margin_r
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(margin_l, y)
    pdf.cell(
        content_w,
        4.5,
        "ANÁLISIS DE LA PRUEBA DE ALIENTO DE H2 Y CH4 PARA EL ESTUDIO DE LA",
        align="C",
    )
    y += 6

    texto = "MALABSORCIÓN E INTOLERANCIA A LA LACTOSA"
    logo_w = 19
    logo_h = 5.2
    texto_w = pdf.get_string_width(texto)
    logo_gap = 3 if os.path.exists(LACTOKIT_IMG) else 0
    logo_space = logo_w + logo_gap if os.path.exists(LACTOKIT_IMG) else 0
    total_w = texto_w + logo_space
    x = margin_l + (content_w - total_w) / 2

    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(texto_w, 4.5, texto)
    if os.path.exists(LACTOKIT_IMG):
        pdf.image(LACTOKIT_IMG, x=x + texto_w + logo_gap, y=y - 0.4, w=logo_w, h=logo_h)
    else:
        pdf.cell(0, 4.5, " Lactokit")
    y += 7

    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.25)
    pdf.line(margin_l, y, page_w - margin_r, y)
    return y + 4


def _referencias_lactokit_html() -> str:
    return "".join(
        [
            _html_p_rich(
                [
                    ("Si la concentración de ", False),
                    ("hidrógeno en el aliento se incrementa en más de 20 ppm", True),
                    (" con respecto al valor basal y/o la concentración de ", False),
                    ("metano es mayor 10 ppm", True),
                    (" en cualquier punto de la gráfica, se considera que hay malabsorción de la lactosa.", False),
                ]
            ),
            _html_p_rich(
                [
                    ("Si el incremento de los gases viene acompañado de sintomatología asociada a la malabsorción se puede hablar de una ", False),
                    ("intolerancia a la lactosa", True),
                    (".", False),
                ]
            ),
            _html_p_rich(
                [
                    (
                        "Este resultado se complementará con la clínica y anamnesis del paciente para que el facultativo prescriptor determine el diagnóstico",
                        True,
                    )
                ]
            ),
        ]
    )


def _notas_lactokit_html() -> str:
    return "".join(
        [
            _html_p(
                "Valores de referencia obtenidos de: Rezaie A et al. Hydrogen and Methane-Based Breath Testing in Gastrointestinal Disorders: The North American Consensus. Am J Gastroenterology 2017 May;112(5):775-784."
            ),
            _html_p(
                "Los valores de H2 y CH4 son corregidos proporcionalmente un valor de 5,5% de CO 2 según las especificaciones del analizador."
            ),
            _html_p_rich(
                [
                    ("Toda muestra con un valor igual o inferior a 1,4% de CO2 será \"", False),
                    ("Muestra Insuficiente", True),
                    ("\", ya que se considera que la muestra está contaminada o diluida. En este caso los valores de H2 y CH4 no pueden ser informados y su resultado será cero.", False),
                ]
            ),
        ]
    )


def _dibujar_tabla_lactokit(pdf: FPDF, x: float, y: float, valores: dict[str, list]) -> float:
    tiempos = [0, 25, 50, 75, 100, 125, 150, 175]
    col_w = [30, 48, 48, 44]
    row_h = 4.5
    headers = [
        "TIEMPO (min)",
        "H2 (ppm) CORREGIDO",
        "CH4 (ppm) CORREGIDO",
        "CO2 (%) MUESTRA",
    ]

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.15)
    pdf.set_font("Helvetica", "B", 5.5)
    pdf.set_xy(x, y)
    for idx, header in enumerate(headers):
        cx = x + sum(col_w[:idx])
        pdf.rect(cx, y, col_w[idx], row_h)
        if idx in (0, 3, 4):
            pdf.set_text_color(0, 70, 140)
        elif idx == 1:
            pdf.set_text_color(35, 75, 255)
        else:
            pdf.set_text_color(255, 35, 35)
        pdf.set_xy(cx, y + 0.7)
        pdf.cell(col_w[idx], 3, header, align="C")
    y += row_h

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(0, 70, 140)
    for idx, tiempo in enumerate(tiempos):
        pdf.set_xy(x, y)
        fila = [
            str(tiempo),
            _fmt_lactokit_valor(valores["h2"][idx]),
            _fmt_lactokit_valor(valores["ch4"][idx]),
            _fmt_lactokit_valor(valores["co2"][idx]),
        ]
        for col_idx, valor in enumerate(fila):
            cx = x + sum(col_w[:col_idx])
            pdf.rect(cx, y, col_w[col_idx], row_h)
            if col_idx == 1:
                pdf.set_text_color(35, 75, 255)
                pdf.set_font("Helvetica", "B", 7)
            elif col_idx == 2:
                pdf.set_text_color(255, 35, 35)
                pdf.set_font("Helvetica", "B", 7)
            else:
                pdf.set_text_color(0, 70, 140)
                pdf.set_font("Helvetica", "", 7)
            pdf.set_xy(cx, y + 0.7)
            pdf.cell(col_w[col_idx], 3, valor, align="C")
        y += row_h
    pdf.set_text_color(0, 0, 0)
    return y + 5


def _dibujar_footer_lactokit(pdf: FPDF, page_w: int, margin_l: int, margin_r: int) -> None:
    footer_line_y = 272
    if os.path.exists(FIRMA_IMG):
        pdf.image(FIRMA_IMG, x=page_w - margin_r - 45, y=footer_line_y - 30, w=35)
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


def _dibujar_informe_error_lactokit(
    pdf: FPDF,
    muestra: Muestra,
    resultado_lactokit,
    valores: dict[str, list],
    page_w: int,
    margin_l: int,
    margin_r: int,
) -> bytes:
    y = _dibujar_cabecera_lactokit(pdf, muestra, page_w, margin_l, margin_r, 12)
    y = _dibujar_titulo_lactokit(pdf, page_w, margin_l, margin_r, y)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(160, 0, 0)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 5, "INFORME DE ERROR LACTOKIT")
    y += 8
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(margin_l, y)
    pdf.multi_cell(
        page_w - margin_l - margin_r,
        4,
        "Los resultados ingresados no permiten determinar una valoración válida según las reglas definidas para el estudio Lactokit. "
        "El formato definitivo de este informe queda sujeto a la documentación del proveedor.",
    )
    y = pdf.get_y() + 5
    y = _dibujar_tabla_lactokit(pdf, margin_l, y, valores)
    pdf.set_font("Helvetica", "BU", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(margin_l, y)
    pdf.cell(0, 4, "VALORACIÓN DE LA PRUEBA")
    y += 7
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(margin_l, y)
    pdf.multi_cell(
        page_w - margin_l - margin_r,
        4,
        f"{resultado_lactokit.valoracion}: {_descripcion_lactokit_pdf(resultado_lactokit)}",
    )
    pdf.set_text_color(0, 0, 0)
    _dibujar_footer_lactokit(pdf, page_w, margin_l, margin_r)
    return bytes(pdf.output())


def _generar_informe_lactokit_pdf(muestra: Muestra, validacion_clinica: bool = True) -> bytes:
    db = object_session(muestra)
    resultado_lactokit = obtener_resultado_lactokit(db, muestra.protocolo) if db else None
    valores = leer_valores_lactokit(resultado_lactokit)
    if not valores or not resultado_lactokit:
        raise ValueError("La muestra Lactokit no tiene resultados cargados")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    page_w = 210
    margin_l = 20
    margin_r = 20
    if resultado_lactokit.valoracion == "ERROR":
        return _dibujar_informe_error_lactokit(pdf, muestra, resultado_lactokit, valores, page_w, margin_l, margin_r)

    y = _dibujar_cabecera_lactokit(pdf, muestra, page_w, margin_l, margin_r, 12)
    y = _dibujar_titulo_lactokit(pdf, page_w, margin_l, margin_r, y)
    y = _dibujar_grafico_lactokit(pdf, margin_l + 18, y, 134, 65, valores["h2"], valores["ch4"]) + 3
    y = _dibujar_tabla_lactokit(pdf, margin_l, y, valores)

    ref_x = 16

    pdf.set_font("Helvetica", "BU", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(ref_x, y)
    pdf.cell(0, 4, "VALORACIÓN DE LA PRUEBA")
    y += 7
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(ref_x, y)
    pdf.multi_cell(
        page_w - (ref_x * 2),
        4.2,
        _descripcion_lactokit_pdf(resultado_lactokit).upper(),
    )
    y = pdf.get_y() + 4

    pdf.set_font("Helvetica", "BU", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(ref_x, y)
    pdf.cell(0, 4, "VALORES DE REFERENCIA")
    y += 7
    pdf.set_text_color(0, 0, 0)
    y = _write_html_lactokit(
        pdf,
        ref_x,
        y,
        _referencias_lactokit_html(),
        font_size=8.5,
        paragraph_gap=1.7,
    )

    pdf.add_page()
    y = 24
    pdf.set_font("Helvetica", "BU", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(ref_x, y)
    pdf.cell(0, 4, "NOTA:")
    y += 7
    y = _write_html_lactokit(
        pdf,
        ref_x,
        y,
        _notas_lactokit_html(),
        font_size=8.5,
        paragraph_gap=2,
    )

    if not validacion_clinica:
        pdf.set_text_color(170, 170, 170)
        pdf.set_font("Helvetica", "", 22)
        pdf.set_xy(42, 198)
        pdf.cell(126, 8, "INFORME SIN VALIDACIÓN CLÍNICA", align="C")
        return bytes(pdf.output())

    _dibujar_footer_lactokit(pdf, page_w, margin_l, margin_r)
    return bytes(pdf.output())
