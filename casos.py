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
    SLACK_BOT_TOKEN, generar_id_caso, categoria_de_id_caso,
)
from formularios_casos import (
    construir_blocks_formulario, specs_validacion, FORM_SPECS,
    CATEGORIAS_CON_DOCUMENTO, ARCHIVO_BLOCK_ID,
)
from validaciones import _guardar_fila_por_encabezado, _actualizar_fila_por_id, _VALIDADORES


# Acción de Slack (action_id) que llevan TODOS los botones de cambio de estado en la tarjeta
# — se usa el mismo para los 4, y el propio botón lleva en su 'value' cuál caso y a qué
# estado hay que pasar (ver _bloque_botones_estado).
ACTION_CAMBIAR_ESTADO = "cambiar_estado_caso"

# No se pone un botón para volver a "Abierto": es el estado inicial de todo caso nuevo, así
# que no hace falta un botón para "reabrirlo" en el mismo instante en que se crea.
ESTADOS_CON_BOTON = [e for e in ESTADOS_CASO if e != "Abierto"]

EMOJI_ESTADO = {
    "Abierto": "🔵", "En espera": "🟡", "Sin respuesta": "🟠", "Cerrado": "✅", "Finalizado": "🏁",
}


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


def _bloque_botones_estado(id_caso):
    """Fila de botones (uno por cada estado al que se puede pasar) para que cambiar el
    estado del caso sea un clic, sin tener que ir al Sheet ni escribir ningún comando. Cada
    botón lleva en su 'value' el ID del caso + el estado destino, que es lo que lee
    actualizar_estado_caso() al recibir el clic."""
    return {
        "type": "actions",
        "block_id": f"estado_{id_caso}",
        "elements": [
            {
                "type": "button",
                "action_id": ACTION_CAMBIAR_ESTADO,
                "text": {"type": "plain_text", "text": f"{EMOJI_ESTADO.get(estado, '')} {estado}".strip()},
                "value": json.dumps({"id_caso": id_caso, "nuevo_estado": estado}),
            }
            for estado in ESTADOS_CON_BOTON
        ],
    }


def _tarjeta_caso(categoria, etiqueta, nombre_agente, ahora, datos, links_documentos=None, id_caso=None):
    """Arma el mensaje tipo 'ticket' para el canal: una franja de color por categoría
    (usando el color lateral de los 'attachments' de Slack) + una lista vertical de campos
    con ícono + un pie con la etiqueta, quién reportó el caso y cuándo (+ un link por cada
    documento adjunto, si la categoría los trae) + los botones para cambiar el estado."""
    campos = _campos_llenados(categoria, datos)
    circulo, color = CIRCULO_Y_COLOR_CATEGORIA.get(categoria, ("⚪", "#8E8E93"))

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{circulo} *{categoria}*"}},
    ]
    if campos:
        lineas = [f"{ICONO_CAMPO.get(clave, '•')} *{etq}:* {val}" for clave, etq, val in campos]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lineas)}})
    pie = f"🏷️ *{etiqueta}*   ·   🙋 Reportado por *{nombre_agente}*   ·   🕒 {ahora.strftime('%d/%m/%Y %H:%M')}"
    for i, link in enumerate(links_documentos or [], start=1):
        etiqueta_doc = "Ver documento" if len(links_documentos) == 1 else f"Ver documento {i}"
        pie += f"   ·   📎 <{link}|{etiqueta_doc}>"
    if id_caso:
        pie += f"   ·   🔖 `{id_caso}`"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": pie}]})
    if id_caso:
        blocks.append(_bloque_botones_estado(id_caso))
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
    # 'value'/'selected_option'. Se valida aparte que haya al menos un archivo adjunto (Slack
    # ya limita a MAX_ARCHIVOS_POR_CASO desde el propio modal, no hace falta validarlo aquí).
    archivos = []
    if categoria in CATEGORIAS_CON_DOCUMENTO:
        archivos = valores.get(ARCHIVO_BLOCK_ID, {}).get("valor", {}).get("files") or []
        if not archivos:
            errores[ARCHIVO_BLOCK_ID] = "Debes adjuntar al menos un documento antes de enviar el caso."

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

    # Se republica cada archivo por separado en el canal — si alguno falla, los demás igual
    # quedan guardados (no se pierde todo por un solo archivo problemático).
    links_documentos = [
        link for archivo in archivos
        if (link := _compartir_documento_en_canal(client, archivo, categoria, nombre_agente))
    ]

    id_caso = generar_id_caso(categoria, ahora)

    fila = {
        "Categoria": categoria,
        "Etiqueta": etiqueta,
        **datos,
        "Agente": nombre_agente,
        "Agente Slack ID": usuario_id,
        "Estado": ESTADOS_CASO[0],  # "Abierto"
        "Fecha alta": ahora.strftime("%d/%m/%Y %H:%M"),
        "Fecha actualizacion": ahora.strftime("%d/%m/%Y %H:%M"),
        "ID caso": id_caso,
    }
    # OJO: solo se agrega esta clave para las categorías que SÍ tienen columna "Documento
    # adjunto" en su pestaña — si se agregara siempre, en las otras 7 pestañas (que no tienen
    # esa columna) quedaría desalineada al final de la fila (el mismo bug que ya tuvimos con
    # los encabezados mal escritos a mano).
    if categoria in CATEGORIAS_CON_DOCUMENTO:
        # Varios links en la misma celda, uno por línea (conviene activar "ajustar texto"
        # en esta columna del Sheet para que se vean todos sin necesidad de expandir la fila).
        fila["Documento adjunto"] = "\n".join(links_documentos)

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
                attachments=_tarjeta_caso(categoria, etiqueta, nombre_agente, ahora, datos, links_documentos, id_caso),
            )
        except Exception as e:
            print(f"⚠️ [caso-mercadeo] No se pudo publicar en el canal de casos: {e}")


@app.action(ACTION_CAMBIAR_ESTADO)
def actualizar_estado_caso(ack, body, client):
    """Se dispara cuando cualquier agente le da clic a uno de los botones de estado en la
    tarjeta del canal. Los botones quedan siempre activos (no se deshabilitan tras usarlos)
    para poder ir moviendo el caso por sus distintos estados con el tiempo. La confirmación
    (o el error) se publica como respuesta en el mismo hilo del mensaje, para dejar un
    rastro de quién cambió qué y cuándo sin tener que reconstruir toda la tarjeta original."""
    ack()
    try:
        valor = json.loads(body["actions"][0]["value"])
        id_caso = valor["id_caso"]
        nuevo_estado = valor["nuevo_estado"]
    except Exception as e:
        print(f"⚠️ [estado-caso] No se pudo leer el botón presionado: {e}")
        return

    categoria = categoria_de_id_caso(id_caso)
    if not categoria:
        print(f"⚠️ [estado-caso] No se reconoce a qué categoría pertenece el caso '{id_caso}'.")
        return
    pestana = pestana_de_categoria(categoria)

    usuario_id = body["user"]["id"]
    quien = nombre_real_del_agente(client, usuario_id)
    ahora = datetime.now(ZoneInfo("America/Caracas"))

    try:
        ws = abrir_pestana_casos(pestana)
        _actualizar_fila_por_id(ws, "ID caso", id_caso, {
            "Estado": nuevo_estado,
            "Fecha actualizacion": ahora.strftime("%d/%m/%Y %H:%M"),
        })
        ok = True
        print(f"✅ [estado-caso] '{id_caso}' actualizado a '{nuevo_estado}' por {quien}.")
    except Exception as e:
        ok = False
        print(f"⚠️ [estado-caso] No se pudo actualizar '{id_caso}' en Sheets: {e}")

    if ok:
        texto = f"🔁 Estado del caso `{id_caso}` actualizado a *{nuevo_estado}* por {quien}."
    else:
        texto = (f"⚠️ No se pudo actualizar el estado del caso `{id_caso}` en el Sheet — revisa "
                 f"que la pestaña '{pestana}' tenga la columna 'ID caso' (agente: {quien}).")
    try:
        client.chat_postMessage(
            channel=body["channel"]["id"],
            thread_ts=body["message"]["ts"],
            text=texto,
        )
    except Exception as e:
        print(f"⚠️ [estado-caso] No se pudo publicar la confirmación en el hilo: {e}")
