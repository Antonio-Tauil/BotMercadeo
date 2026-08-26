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
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    app, CATEGORIAS, ETIQUETA_POR_CATEGORIA, ESTADOS_CASO,
    abrir_pestana_casos, nombre_real_del_agente, CANAL_CASOS_MERCADEO,
)
from formularios_casos import construir_blocks_formulario, specs_validacion
from validaciones import _guardar_fila_por_encabezado, _VALIDADORES


CALLBACK_PASO1 = "caso_mercadeo_categoria"
CALLBACK_PASO2 = "caso_mercadeo_datos"


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

    try:
        ws = abrir_pestana_casos()
        _guardar_fila_por_encabezado(ws, fila)
        guardado_ok = True
    except Exception as e:
        print(f"⚠️ [caso-mercadeo] Error guardando en Sheets: {e}")
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

    if guardado_ok and CANAL_CASOS_MERCADEO:
        try:
            client.chat_postMessage(
                channel=CANAL_CASOS_MERCADEO,
                text=f"📋 Nuevo caso *{categoria}* ({etiqueta}) reportado por {nombre_agente}.",
            )
        except Exception as e:
            print(f"⚠️ [caso-mercadeo] No se pudo publicar en el canal de casos: {e}")
