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
        "\n_Próximamente: cambio de estatus de un caso ya registrado (fase 2)._"
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("🚀 BotMercadeo iniciado.")
    handler.start()
