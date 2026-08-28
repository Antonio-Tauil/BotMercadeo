"""
config.py — Configuración general del BotMercadeo: conexión a Slack, ID del Sheet de
registro de casos, categorías del formulario y su mapeo a etiqueta de comisión.

Este bot es una APP DE SLACK SEPARADA de Robotín (BotCobrosQuoota) — tiene su propio
SLACK_BOT_TOKEN / SLACK_APP_TOKEN y su propio deploy en Railway. Puede convivir sin
problema en el mismo workspace de Slack.
"""
import os
import json
from concurrent.futures import ThreadPoolExecutor
from slack_bolt import App
from google.oauth2.service_account import Credentials
import gspread

# Mismo motivo que en Robotín: más hilos disponibles = menos riesgo de que un comando quede
# esperando turno más de los ~3 segundos que Slack da para usar un 'trigger_id' antes de que
# se venza (lo que haría fallar la apertura del modal).
# Se guarda aparte (además de pasárselo a App) porque casos.py lo necesita para descargar
# por su cuenta los documentos que el agente adjunta en el modal (ver ARCHIVO_BLOCK_ID en
# formularios_casos.py) — esa descarga se hace con una llamada HTTP directa, no por slack_bolt.
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
app = App(token=SLACK_BOT_TOKEN, listener_executor=ThreadPoolExecutor(max_workers=30))

# ============ CONFIGURACIÓN GENERAL ============
# ID del Sheet donde se registra cada caso reportado desde Slack (Componente 5 del documento).
# Poner el ID real del Sheet en la variable de entorno SHEET_ID_CASOS_MERCADEO en Railway.
SHEET_ID_CASOS_MERCADEO = os.environ.get("SHEET_ID_CASOS_MERCADEO", "")

# Canal donde se publica un resumen de cada caso nuevo (opcional — dejar vacío para no publicar).
CANAL_CASOS_MERCADEO = os.environ.get("CANAL_CASOS_MERCADEO", "")

# ID de Slack de Astrid (rol de supervisión — dashboard de ganancias, sección 5.3 y 9.2 del
# documento). Igual que con Robotín y el "aviso de guardado fantasma": si un caso se pierde
# al guardarlo, se le avisa aquí además de al agente que lo reportó, para que nunca quede un
# caso perdido sin que nadie se entere. Poner su ID real cuando se tenga (se obtiene con
# /listar-ids una vez instalado el bot) — si se deja vacío, simplemente no se le avisa a nadie
# más aparte del agente.
ASTRID_SLACK_ID = os.environ.get("ASTRID_SLACK_ID", "")
# ============ FIN CONFIGURACIÓN GENERAL ============


# ============ CATEGORÍAS DE CASO Y MAPEO A ETIQUETA DE COMISIÓN (secciones 4.4 y 7.3) ============
CATEGORIAS = [
    "Acceso",
    "Registro",
    "Carga de Documentos",
    "Envío de Contrato",
    "Conciliación",
    "Liquidación",
    "FAQ",
    "Baja de Nivel",
    "Otros",
]

# Cada pestaña del Sheet tiene su PROPIA etiqueta — ya no se agrupan varias categorías bajo
# una misma etiqueta compartida (a diferencia del mapeo original de comisión, sección 7.3 del
# documento). Como cada categoría ya vive en su propia pestaña, su etiqueta es simplemente su
# propio nombre — no hace falta que el agente elija nada manualmente (ni siquiera en "Otros").
ETIQUETA_POR_CATEGORIA = {c: c for c in CATEGORIAS}

ESTADOS_CASO = ["Abierto", "En espera", "Sin respuesta", "Cerrado", "Finalizado"]
# ============ FIN CATEGORÍAS ============


# ============ UNA PESTAÑA DE SHEETS POR CADA UNO DE LOS 9 FORMULARIOS (tabla 7.2 del documento) ============
# Cada categoría tiene su propia pestaña, con exactamente sus columnas — así ninguna fila
# queda con espacios en blanco (a diferencia de agrupar por etiqueta, donde categorías con
# campos distintos comparten pestaña). Los NOMBRES DE PESTAÑA van sin tildes a propósito
# (menos margen de error al crearlas/escribirlas a mano en Sheets); las categorías que se ven
# en Slack sí conservan sus tildes normales — este diccionario es el único lugar que traduce
# de una a otra, para no tener que desalinear nada más si cambia.
CATEGORIA_A_PESTANA = {
    "Conciliación": "Conciliacion",
    "Liquidación": "Liquidacion",
    "Carga de Documentos": "Carga de Documentos",
    "Envío de Contrato": "Envio de Contrato",
    "Acceso": "Acceso",
    "Registro": "Registro",
    "FAQ": "FAQ",
    "Baja de Nivel": "Baja de Nivel",
    "Otros": "Otros",
}


def pestana_de_categoria(categoria):
    return CATEGORIA_A_PESTANA.get(categoria, categoria)
# ============ FIN PESTAÑA POR CATEGORÍA ============


# ============ CONEXIÓN COMPARTIDA A GOOGLE SHEETS ============
# Reutiliza el mismo patrón de Robotín: una sola conexión cacheada en memoria en vez de
# reconectar en cada llamada (la parte lenta de hablar con Sheets es autenticarse, no leer/escribir).
_CLIENTE_SHEETS_CACHEADO = None
_PESTANAS_CACHEADAS = {}


def get_cliente_sheets():
    global _CLIENTE_SHEETS_CACHEADO
    if _CLIENTE_SHEETS_CACHEADO is not None:
        return _CLIENTE_SHEETS_CACHEADO
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds_json["private_key"] = creds_json["private_key"].replace("\\n", "\n")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    _CLIENTE_SHEETS_CACHEADO = gspread.authorize(creds)
    return _CLIENTE_SHEETS_CACHEADO


def abrir_pestana_casos(nombre_pestana):
    """Abre (con caché en memoria) la pestaña donde se registran los casos de una etiqueta."""
    clave = (SHEET_ID_CASOS_MERCADEO, nombre_pestana)
    if clave in _PESTANAS_CACHEADAS:
        return _PESTANAS_CACHEADAS[clave]
    cliente = get_cliente_sheets()
    hoja = cliente.open_by_key(SHEET_ID_CASOS_MERCADEO)
    ws = hoja.worksheet(nombre_pestana)
    _PESTANAS_CACHEADAS[clave] = ws
    return ws
# ============ FIN CONEXIÓN A GOOGLE SHEETS ============


# ============ NOMBRE REAL DEL AGENTE (sin lista fija — se busca en vivo por su ID de Slack) ============
# A propósito NO se usa una lista fija tipo "nombre -> ID de Slack" como COBRADOR_SLACK_IDS en
# Robotín: esa lista se desactualiza cada vez que alguien nuevo entra o hereda la cuenta de
# Slack de quien se fue (así pasó con Valentina/Rebeca). En su lugar, el nombre del agente se
# consulta en vivo a la API de Slack por su ID — siempre está al día, sin mantenimiento manual.
_NOMBRES_CACHEADOS = {}


def nombre_real_del_agente(client, user_id):
    if user_id in _NOMBRES_CACHEADOS:
        return _NOMBRES_CACHEADOS[user_id]
    try:
        info = client.users_info(user=user_id)
        perfil = info["user"]["profile"]
        nombre = perfil.get("real_name") or info["user"].get("real_name") or user_id
    except Exception as e:
        print(f"⚠️ No se pudo obtener el nombre real de {user_id}: {e}")
        nombre = user_id
    _NOMBRES_CACHEADOS[user_id] = nombre
    return nombre
# ============ FIN NOMBRE REAL DEL AGENTE ============
