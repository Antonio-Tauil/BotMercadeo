"""
main.py — Punto de entrada del BotMercadeo. Arranca la conexión de Slack (Socket Mode) y
registra todos los comandos.
"""
import os
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import app
import casos  # noqa: F401  (registra /caso-mercadeo y sus vistas al importarse)


@app.command("/ayuda-mercadeo")
def ayuda(ack, respond):
    ack()
    respond(
        "*Comandos disponibles:*\n"
        "• `/caso-mercadeo` — reportar un caso nuevo (elige el tipo y llena el formulario).\n"
        "• Para cambiar el estado de un caso ya registrado, usa los botones que aparecen debajo "
        "de su tarjeta en el canal de casos — no hace falta ningún comando.\n"
        "\n_Próximamente: resumen personal de casos por agente (fase 2)._"
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("🚀 BotMercadeo iniciado.")
    handler.start()
