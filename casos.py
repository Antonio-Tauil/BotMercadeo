"""
casos.py — Comando /caso-mercadeo: el agente elige el tipo de caso (paso 1) y llena el
formulario específico de esa categoría (paso 2). Al enviarlo, se valida y se guarda una
fila en la hoja "Casos" de Google Sheets (Componente 5 del documento).

Mecánica de 2 pasos en un solo comando (sección 7.1 del documento — "recomendado: un solo
comando con desplegable de categoría"): la PRIMERA vista solo tiene el desplegable de
categoría; al enviarla, Slack permite reemplazar esa misma ventana por una segunda
(`response_action: "update"`) ya con los campos que le tocan a esa categoría. Así no hace
falta un comando distinto por cada uno de los 9 tipos de caso.
"""
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    app, CATEGORIAS, ETIQUETA_POR_CATEGORIA, ESTADOS_CASO, pestana_de_categoria,
    abrir_pestana_casos, nombre_real_del_agente, CANAL_CASOS_MERCADEO, ASTRID_SLACK_ID,
    SLACK_BOT_TOKEN,
)
from formularios_casos import (
    construir_blocks_formulario, specs_validacion, FORM_SPECS,
    CATEGORIAS_CON_DOCUMENTO, ARCHIVO_BLOCK_ID,
)
from validaciones import _guardar_fila_por_encabezado, _VALIDADORES


CALLBACK_PASO1 = "caso_mercadeo_categoria"
CALLBACK_PASO2 = "caso_mercadeo_datos"


# Estilo "ticket" elegido para la tarjeta del canal: un ícono por tipo de campo y un
# color/círculo distinto por categoría, para reconocer el tipo de caso de un vistazo.
ICONO_CAMPO = {
    "Nombre": "👤", "Cedula": "🪪", "Empresa": "🏢", "Telefono": "📞", "Correo": "✉️",
    "Banco emisor": "🏦", "Referencia": "🔢", "Monto": "💰", "Fecha de pago": "📅",
    "Cuotas pagadas": "🧾", "Descripcion": "📝",
}

CIRCULO_Y_COLOR_CATEGORIA = {
    "Acceso": ("🟢", "#2EB67D"),
    "Registro": ("🟡", "#ECB22E"),
    "Carga de Documentos": ("🔵", "#36C5F0"),
    "Envío de Contrato": ("🟣", "#8B5CF6"),
    "Conciliación": ("🔴", "#E01E5A"),
    "Liquidación": ("🟠", "#F2952F"),
    "FAQ": ("⚪", "#8E8E93"),
    "Baja de Nivel": ("⚫", "#3C3C3C"),
    "Otros": ("🟤", "#6B4226"),
}


def _campos_llenados(categoria, datos):
    """Lista [(clave, etiqueta_visible, valor), ...] de los campos que el agente realmente
    llenó, en el mismo orden del formulario. La 'clave' viaja aparte para poder buscar su
    ícono en ICONO_CAMPO sin tener que adivinarlo a partir de la etiqueta visible."""
    campos = []
    for clave, etiqueta_visible, _validador, _multilinea in FORM_SPECS[categoria]:
        valor = datos.get(clave, "")
        if valor:
            campos.append((clave, etiqueta_visible, valor))
    return campos


def _resumen_datos_formulario(categoria, datos):
    """Versión en texto plano de _campos_llenados ('*Etiqueta:* valor' por línea) — se usa
    como fallback de notificación/accesibilidad del mensaje con tarjeta."""
    return [f"*{etiqueta}:* {valor}" for _clave, etiqueta, valor in _campos_llenados(categoria, datos)]


def _compartir_documento_en_canal(client, archivo, categoria, nombre_agente):
    """El archivo que el agente adjunta en el modal (bloque 'file_input') nace PRIVADO —
    solo la app puede verlo, nadie más en el equipo. Para que quede accesible para quien
    revise el caso, se descarga ese archivo y se vuelve a subir directo al canal de casos;
    el link resultante (permalink) es el que se guarda en el Sheet.

    Si algo falla aquí (por ejemplo, si a la app le faltan los scopes 'files:read' /
    'files:write'), no debe tumbar el guardado del caso — solo se pierde el link y queda
    un aviso en los logs de Railway para revisarlo a mano."""
    if not CANAL_CASOS_MERCADEO:
        return ""
    try:
        resp = requests.get(
            archivo["url_private_download"],
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=20,
        )
        resp.raise_for_status()
        subida = client.files_upload_v2(
            channel=CANAL_CASOS_MERCADEO,
            filename=archivo.get("name", "documento"),
            content=resp.content,
            title=f"{categoria} — {nombre_agente}",
        )
        return subida["file"]["permalink"]
    except Exception as e:
        print(f"⚠️ [caso-mercadeo] No se pudo republicar el documento adjunto en el canal: {e}")
        return ""


def _tarjeta_caso(categoria, etiqueta, nombre_agente, ahora, datos, link_documento=""):
    """Arma el mensaje tipo 'ticket' para el canal: una franja de color por categoría
    (usando el color lateral de los 'attachments' de Slack) + una lista vertical de campos
    con ícono + un pie con la etiqueta, quién reportó el caso y cuándo (+ link al documento
    adjunto, si la categoría lo trae)."""
    campos = _campos_llenados(categoria, datos)
    circulo, color = CIRCULO_Y_COLOR_CATEGORIA.get(categoria, ("⚪", "#8E8E93"))

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{circulo} *{categoria}*"}},
    ]
    if campos:
        lineas = [f"{ICONO_CAMPO.get(clave, '•')} *{etq}:* {val}" for clave, etq, val in campos]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lineas)}})
    pie = f"🏷️ *{etiqueta}*   ·   🙋 Reportado por *{nombre_agente}*   ·   🕒 {ahora.strftime('%d/%m/%Y %H:%M')}"
    if link_documento:
        pie += f"   ·   📎 <{link_documento}|Ver documento>"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": pie}]})
    # Se envuelve en un solo "attachment" (mecanismo clásico de Slack) para que aparezca la
    # franja de color a la izquierda — Block Kit por sí solo no permite ese acento de color.
    return [{"color": color, "blocks": blocks}]


def _vista_paso1():
    return {
        "type": "modal",
        "callback_id": CALLBACK_PASO1,
        "title": {"type": "plain_text", "text": "Nuevo caso"},
        "submit": {"type": "plain_text", "text": "Siguiente"},
        "blocks": [
            {
                "type": "input",
                "block_id": "categoria",
                "label": {"type": "plain_text", "text": "Tipo de caso"},
                "element": {
                    "type": "static_select",
                    "action_id": "valor",
                    "options": [{"text": {"type": "plain_text", "text": c}, "value": c} for c in CATEGORIAS],
                },
            }
        ],
    }


@app.command("/caso-mercadeo")
def abrir_caso_mercadeo(ack, body, client):
    ack()
    try:
        client.views_open(trigger_id=body["trigger_id"], view=_vista_paso1())
    except Exception as e:
        print(f"⚠️ [caso-mercadeo] No se pudo abrir el paso 1 del formulario: {e}")
        try:
            client.chat_postEphemeral(
                channel=body["channel_id"], user=body["user_id"],
                text="⚠️ No se pudo abrir el formulario a tiempo. Por favor vuelve a escribir el comando.",
            )
        except Exception:
            pass


@app.view(CALLBACK_PASO1)
def recibir_categoria(ack, body):
    categoria = body["view"]["state"]["values"]["categoria"]["valor"]["selected_option"]["value"]
    ack({
        "response_action": "update",
        "view": {
            "type": "modal",
            "callback_id": CALLBACK_PASO2,
            "private_metadata": categoria,
            "title": {"type": "plain_text", "text": categoria[:24]},
            "submit": {"type": "plain_text", "text": "Enviar caso"},
            "blocks": construir_blocks_formulario(categoria),
        },
    })


@app.view(CALLBACK_PASO2)
def recibir_datos_caso(ack, body, client):
    categoria = body["view"]["private_metadata"]
    valores = body["view"]["state"]["values"]

    errores = {}
    for block_id, tipo in specs_validacion(categoria):
        campo = valores.get(block_id, {}).get("valor", {})
        # los campos de tipo static_select (solo pasa con "Etiqueta" en Otros) traen 'selected_option'
        if "selected_option" in campo:
            valor = (campo.get("selected_option") or {}).get("value", "")
        else:
            valor = campo.get("value", "")
        ok, msg = _VALIDADORES[tipo](valor)
        if not ok:
            errores[block_id] = msg

    # El campo de archivo ('file_input') no pasa por _VALIDADORES: trae 'files' en vez de
    # 'value'/'selected_option'. Se valida aparte que haya al menos un archivo adjunto.
    archivo = None
    if categoria in CATEGORIAS_CON_DOCUMENTO:
        archivos = valores.get(ARCHIVO_BLOCK_ID, {}).get("valor", {}).get("files") or []
        if not archivos:
            errores[ARCHIVO_BLOCK_ID] = "Debes adjuntar el documento antes de enviar el caso."
        else:
            archivo = archivos[0]

    if errores:
        ack({"response_action": "errors", "errors": errores})
        return

    ack()

    datos = {}
    for block_id, _tipo in specs_validacion(categoria):
        campo = valores.get(block_id, {}).get("valor", {})
        if "selected_option" in campo:
            datos[block_id] = (campo.get("selected_option") or {}).get("value", "")
        else:
            datos[block_id] = (campo.get("value") or "").strip()

    etiqueta = ETIQUETA_POR_CATEGORIA.get(categoria) or datos.pop("Etiqueta", "")

    usuario_id = body["user"]["id"]
    nombre_agente = nombre_real_del_agente(client, usuario_id)
    ahora = datetime.now(ZoneInfo("America/Caracas"))

    link_documento = ""
    if archivo:
        link_documento = _compartir_documento_en_canal(client, archivo, categoria, nombre_agente)

    fila = {
        "Categoria": categoria,
        "Etiqueta": etiqueta,
        **datos,
        "Agente": nombre_agente,
        "Agente Slack ID": usuario_id,
        "Estado": ESTADOS_CASO[0],  # "Abierto"
        "Fecha alta": ahora.strftime("%d/%m/%Y %H:%M"),
        "Fecha actualizacion": ahora.strftime("%d/%m/%Y %H:%M"),
    }
    # OJO: solo se agrega esta clave para las categorías que SÍ tienen columna "Documento
    # adjunto" en su pestaña — si se agregara siempre, en las otras 7 pestañas (que no tienen
    # esa columna) quedaría desalineada al final de la fila (el mismo bug que ya tuvimos con
    # los encabezados mal escritos a mano).
    if categoria in CATEGORIAS_CON_DOCUMENTO:
        fila["Documento adjunto"] = link_documento

    pestana = pestana_de_categoria(categoria)

    try:
        ws = abrir_pestana_casos(pestana)
        _guardar_fila_por_encabezado(ws, fila)
        guardado_ok = True
        # Log de confirmación en cada guardado exitoso (mismo patrón que Robotín: no solo se
        # avisa por Slack, también queda un rastro en los logs de Railway para depurar).
        print(f"✅ [caso-mercadeo] Guardado en hoja '{pestana}' (categoría={categoria}, agente={nombre_agente}).")
    except Exception as e:
        print(f"⚠️ [caso-mercadeo] Error guardando en Sheets (pestaña='{pestana}'): {e}")
        guardado_ok = False

    if guardado_ok:
        texto = f"✅ Caso de *{categoria}* registrado (etiqueta: {etiqueta})."
    else:
        texto = (f"🔴 El caso de *{categoria}* NO se pudo guardar en la hoja por un error técnico. "
                 "Avisa para registrarlo a mano mientras se revisa.")
    try:
        client.chat_postMessage(channel=usuario_id, text=texto)
    except Exception as e:
        print(f"⚠️ [caso-mercadeo] No se pudo avisar por DM al agente {usuario_id}: {e}")

    # Blindaje de "guardado fantasma" (mismo que agregamos en Robotín): si el guardado falla,
    # que no dependa solo de que el agente avise a mano — se le avisa también al supervisor.
    if not guardado_ok and ASTRID_SLACK_ID:
        try:
            client.chat_postMessage(
                channel=ASTRID_SLACK_ID,
                text=(f"🔴 *BotMercadeo: un caso de {categoria} NO se pudo guardar en Sheets* "
                      f"(agente: {nombre_agente}). Revisa los logs de Railway y regístralo a mano si hace falta."),
            )
        except Exception as e:
            print(f"⚠️ [caso-mercadeo] No se pudo avisar al supervisor del fallo de guardado: {e}")

    if guardado_ok and CANAL_CASOS_MERCADEO:
        texto_plano = (f"📋 Nuevo caso {categoria} ({etiqueta}) reportado por {nombre_agente}. "
                        + " | ".join(f"{e}: {v}" for _c, e, v in _campos_llenados(categoria, datos)))
        try:
            client.chat_postMessage(
                channel=CANAL_CASOS_MERCADEO,
                text=texto_plano,  # fallback de texto plano (notificaciones, accesibilidad)
                attachments=_tarjeta_caso(categoria, etiqueta, nombre_agente, ahora, datos, link_documento),
            )
        except Exception as e:
            print(f"⚠️ [caso-mercadeo] No se pudo publicar en el canal de casos: {e}")
