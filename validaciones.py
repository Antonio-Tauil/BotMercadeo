"""
validaciones.py — Funciones de apoyo: guardar/leer en el Sheet por NOMBRE de columna (no por
posición), reintento ante cuota excedida de Google, y validadores de campos de formulario.
Es una versión adaptada del mismo archivo probado de Robotín (BotCobrosQuoota), con un
validador de correo agregado (los formularios de Acceso/Envío de Contrato lo necesitan).
"""
import re
import time
import unicodedata
from datetime import date
from gspread.utils import rowcol_to_a1


# ============ GUARDAR EN SHEETS POR NOMBRE DE COLUMNA ============
def _normalizar_encabezado(texto):
    t = str(texto or "").strip().lower()
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def _guardar_fila_por_encabezado(sheet, datos):
    """
    Guarda una fila nueva colocando cada valor en la columna que le corresponde POR NOMBRE.
    'datos' es un diccionario {nombre_de_columna: valor}. Si una clave no tiene columna con
    ese nombre en el Sheet todavía (por ejemplo, una pestaña vieja a la que le falta "ID
    caso" porque se creó antes de agregar esa función), la pestaña se "autorepara" sola: se
    escribe el encabezado que falta en la fila 1, en la misma columna donde va a caer el
    valor, ANTES de guardar la fila — así nadie tiene que entrar al Sheet a mano a escribir
    encabezados nuevos. (Antes, el valor se pegaba igual al final pero SIN encabezado, lo que
    lo dejaba imposible de encontrar por nombre después — ese fue justo el motivo de que los
    botones de estado no encontraran la columna 'ID caso' en pestañas viejas.)
    """
    encabezados_sheet = _con_reintento(lambda: sheet.row_values(1))
    restantes = dict(datos)
    fila = []
    for encabezado in encabezados_sheet:
        objetivo = _normalizar_encabezado(encabezado)
        valor_encontrado = ""
        for clave in list(restantes.keys()):
            if _normalizar_encabezado(clave) == objetivo:
                valor_encontrado = restantes.pop(clave)
                break
        fila.append(valor_encontrado)
    if restantes:
        primera_col_nueva = len(encabezados_sheet) + 1
        nuevos_encabezados = list(restantes.keys())
        rango = (f"{rowcol_to_a1(1, primera_col_nueva)}:"
                 f"{rowcol_to_a1(1, primera_col_nueva + len(nuevos_encabezados) - 1)}")
        _con_reintento(lambda: sheet.update(range_name=rango, values=[nuevos_encabezados]))
        fila.extend(restantes.values())
    # value_input_option="USER_ENTERED": le pide a Sheets que interprete cada valor tal como
    # lo interpretaría si una persona lo hubiera tecleado a mano. Sin esto (el modo por
    # defecto, "RAW"), "Fecha alta"/"Fecha actualizacion" quedaban guardadas como texto
    # plano, y ninguna fórmula de fecha (COUNTIFS, SUMPRODUCT con fechas, etc.) las podía
    # comparar con HOY()/TODAY(). Con USER_ENTERED, Sheets reconoce el patrón DD/MM/AAAA
    # HH:MM y lo guarda como fecha real, sin cambiar cómo se ve la celda.
    _con_reintento(lambda: sheet.append_row(fila, value_input_option="USER_ENTERED"))


def _columna_por_nombre(ws, nombre):
    objetivo = _normalizar_encabezado(nombre)
    encabezados = [_normalizar_encabezado(c) for c in _con_reintento(lambda: ws.row_values(1))]
    if objetivo in encabezados:
        return encabezados.index(objetivo) + 1
    return None


def _actualizar_fila_por_id(ws, columna_id, valor_id, cambios):
    """
    Busca la fila donde la columna 'columna_id' tiene el valor 'valor_id' (por ejemplo,
    columna_id='ID caso', valor_id='CD-280826-142233') y actualiza, por NOMBRE de columna,
    cada par en 'cambios' ({nombre_de_columna: nuevo_valor}) — usado para cambiar el Estado
    de un caso ya guardado desde los botones de Slack, sin tocar el resto de la fila.

    Lanza ValueError si la columna_id no existe en la pestaña o si no se encuentra ningún
    caso con ese valor — así el llamador puede avisar del error en vez de fallar en silencio.
    """
    col_id = _columna_por_nombre(ws, columna_id)
    if col_id is None:
        raise ValueError(f"La pestaña no tiene una columna '{columna_id}'.")
    valores_columna = _con_reintento(lambda: ws.col_values(col_id))
    try:
        fila_idx = valores_columna.index(valor_id) + 1  # ya viene con el encabezado incluido
    except ValueError:
        raise ValueError(f"No se encontró ningún caso con {columna_id}='{valor_id}'.")
    for nombre_columna, nuevo_valor in cambios.items():
        col = _columna_por_nombre(ws, nombre_columna)
        if col is not None:
            # ws.update_cell() de gspread ya usa "USER_ENTERED" internamente (a diferencia de
            # append_row(), que por defecto usa "RAW") — por eso "Fecha actualizacion" ya se
            # guardaba como fecha real incluso antes de este ajuste; el que faltaba era
            # "Fecha alta" en el guardado inicial (ver _guardar_fila_por_encabezado arriba).
            _con_reintento(lambda c=col, v=nuevo_valor: ws.update_cell(fila_idx, c, v))
# ============ FIN GUARDAR POR NOMBRE DE COLUMNA ============


# ============ REINTENTO ANTE CUOTA EXCEDIDA DE GOOGLE SHEETS ============
def _es_error_de_cuota(e):
    texto = str(e)
    return "429" in texto or "Quota exceeded" in texto or "RESOURCE_EXHAUSTED" in texto


def _con_reintento(func, intentos=3, espera_inicial=5):
    espera = espera_inicial
    for intento in range(intentos):
        try:
            return func()
        except Exception as e:
            if not _es_error_de_cuota(e) or intento == intentos - 1:
                raise
            print(f"⚠️ Google Sheets pidió esperar (cuota excedida), "
                  f"reintentando en {espera}s (intento {intento + 1}/{intentos})...")
            time.sleep(espera)
            espera *= 3
# ============ FIN REINTENTO ANTE CUOTA EXCEDIDA ============


# ============ VALIDACIÓN DE DATOS ============
def _es_cedula_valida(texto):
    t = str(texto or "").strip().upper()
    if not t:
        return False, "La cédula está vacía."
    t2 = t.replace(".", "").replace("-", "").replace(" ", "")
    m = re.match(r"^([VEJPG]?)(\d+)$", t2)
    if not m:
        return False, "Cédula inválida. Usa números y opcional V/E/J/P (ej: V-12.345.678)."
    digitos = m.group(2)
    if not (6 <= len(digitos) <= 10):
        return False, f"La cédula debe tener entre 6 y 10 dígitos (tiene {len(digitos)})."
    return True, ""


def _es_texto_no_vacio(texto):
    t = str(texto or "").strip()
    if not t:
        return False, "Este campo no puede quedar vacío (o solo con espacios en blanco)."
    if len(t) < 2:
        return False, "Este campo parece incompleto (muy corto). Revisa que esté completo."
    return True, ""


def _es_telefono_valido(texto):
    t = str(texto or "").strip()
    if not t:
        return False, "El teléfono está vacío."
    limpio = re.sub(r"[()\-\s+]", "", t)
    if not limpio.isdigit():
        return False, "El teléfono solo debe tener números (ej: 0414-1234567)."
    n = len(limpio)
    if n not in (10, 11, 12):
        return False, f"El teléfono debe tener 10, 11 o 12 dígitos (tiene {n}). Ej: 04141234567."
    return True, ""


def _es_correo_valido(texto):
    t = str(texto or "").strip()
    if not t:
        return False, "El correo está vacío."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", t):
        return False, "Ese correo no parece válido (ej: nombre@dominio.com)."
    return True, ""


def _es_fecha_valida(texto):
    t = str(texto or "").strip()
    if not t:
        return False, "La fecha está vacía."
    partes = re.split(r"[/\-]", t)
    if len(partes) != 3:
        return False, "Fecha inválida. Usa el formato DD/MM/AAAA (ej: 25/12/2026)."
    try:
        d = int(partes[0]); mth = int(partes[1]); y = int(partes[2])
    except ValueError:
        return False, "La fecha debe tener solo números en formato DD/MM/AAAA."
    if y < 100:
        y += 2000
    try:
        date(y, mth, d)
    except ValueError:
        return False, "Esa fecha no existe. Revisa día/mes (formato DD/MM/AAAA)."
    if not (2024 <= y <= 2030):
        return False, "El año parece un error de tipeo. Usa DD/MM/AAAA (ej: 25/12/2026)."
    return True, ""


def parse_numero(texto):
    if texto is None:
        raise ValueError("vacío")
    s = re.sub(r"[^0-9.,\-]", "", str(texto).strip())
    neg = s.startswith("-")
    s = s.lstrip("-").strip(".,")
    if s == "":
        raise ValueError("sin dígitos")
    if neg:
        s = "-" + s
    tiene_punto = "." in s
    tiene_coma = "," in s
    if tiene_punto and tiene_coma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tiene_coma:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            _, _, dec = s.partition(",")
            s = s.replace(",", "") if len(dec) == 3 else s.replace(",", ".")
    elif tiene_punto:
        if s.count(".") > 1:
            s = s.replace(".", "")
        else:
            _, _, dec = s.partition(".")
            if len(dec) == 3:
                s = s.replace(".", "")
    return float(s)


MONTO_MIN = 0.01
MONTO_MAX = 5_000_000_000


def _es_monto_valido(texto):
    t = str(texto or "").strip()
    if not t:
        return False, "El monto está vacío."
    try:
        num = parse_numero(t)
    except (ValueError, ZeroDivisionError, TypeError):
        return False, "Ese monto no es un número válido. Ejemplo: 1500,50."
    if num < MONTO_MIN:
        return False, "El monto no puede ser cero ni negativo."
    if num > MONTO_MAX:
        return False, f"El monto *{num:,.2f}* parece un error de tipeo (demasiado alto). Revisa y vuelve a intentar."
    return True, ""


_VALIDADORES = {
    "cedula": _es_cedula_valida,
    "telefono": _es_telefono_valido,
    "correo": _es_correo_valido,
    "fecha": _es_fecha_valida,
    "monto": _es_monto_valido,
    "requerido": _es_texto_no_vacio,
}
# ============ FIN VALIDACIÓN DE DATOS ============
