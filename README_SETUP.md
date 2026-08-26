# BotMercadeo — Guía para tenerlo listo el viernes

Este bot cubre el **Componente 4 (Slack)** y alimenta el **Componente 5 (Sheets)** del
documento de requerimientos. NO incluye la parte de CRM (Chatwoot/Zendesk), Meta Business
ni Dashboard — esas son piezas aparte que se conectan después, leyendo desde la misma hoja
de Sheets.

## Qué hace ahora mismo

Un solo comando, `/caso-mercadeo`, que:
1. Abre un modal para elegir el tipo de caso (9 categorías, tabla 7.2 del documento).
2. Al elegir, abre el formulario específico de esa categoría (solo los campos que le corresponden).
3. Valida los campos obligatorios (cédula, teléfono, correo, monto, fecha, texto no vacío).
4. Guarda una fila en la hoja "Casos" con: categoría, etiqueta de comisión (mapeada automáticamente
   según la tabla 7.3), todos los campos del formulario, nombre del agente (consultado en vivo por
   su cuenta de Slack — sin listas que mantener a mano), estado inicial "Abierto", fecha de alta y
   de última actualización.
5. Avisa al agente por DM si el caso se guardó bien o si hubo un error técnico guardándolo (para
   que nunca se pierda un caso sin que nadie se entere).

Lo que queda para una fase 2 (no bloquea las pruebas del viernes): el cambio de estatus de un
caso ya registrado directamente desde Slack (sección 7.4 del documento la deja como algo "a
evaluar"), y el comando de resumen personal por agente.

## Pasos para dejarlo funcionando

### 1. Crear la hoja de Google Sheets
Crear un Sheet nuevo (o una pestaña dentro de uno existente) llamada **"Casos"**, con esta fila
de encabezados en la primera fila (el orden no importa, el bot busca por nombre):

```
Categoria | Etiqueta | Nombre | Cedula | Empresa | Telefono | Correo | Banco emisor | Referencia | Monto | Fecha de pago | Cuotas pagadas | Descripcion | Agente | Agente Slack ID | Estado | Fecha alta | Fecha actualizacion
```

En la columna "Estado" conviene poner validación de datos (menú desplegable) con las 5 opciones:
Abierto, En espera, Sin respuesta, Cerrado, Finalizado — así se puede cambiar a mano mientras no
esté lista la fase 2 de cambio de estatus por Slack.

Compartir esa hoja (permiso de Editor) con el correo de la cuenta de servicio de Google que se
use para las credenciales (la misma cuenta de servicio de Robotín sirve si ya está creada, o se
puede crear una nueva en Google Cloud Console).

### 2. Crear la app de Slack (nueva, separada de Robotín)
En https://api.slack.com/apps → "Create New App" → "From scratch":
- Nombre sugerido: **BotMercadeo**.
- En "Slash Commands", crear `/caso-mercadeo` y `/ayuda-mercadeo`.
- En "OAuth & Permissions", agregar los scopes de bot: `commands`, `chat:write`, `im:write`, `users:read`.
- En "Socket Mode", activarlo y generar un App-Level Token (con scope `connections:write`) — ese es el `SLACK_APP_TOKEN`.
- Instalar la app en el workspace de Quoota — eso da el `SLACK_BOT_TOKEN` (empieza con `xoxb-`).

### 3. Variables de entorno (en Railway, como con Robotín)
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
GOOGLE_CREDENTIALS={"...credenciales de la cuenta de servicio..."}
SHEET_ID_CASOS_MERCADEO=<ID del Sheet creado en el paso 1>
PESTANA_CASOS_MERCADEO=Casos          (opcional, ya es el valor por defecto)
CANAL_CASOS_MERCADEO=<ID de canal>    (opcional — si se deja vacío, no publica resumen en canal)
```

### 4. Desplegar
Mismo patrón que Robotín: subir estos archivos a un repo (o carpeta) aparte, conectarlo a un
proyecto nuevo de Railway (o un segundo servicio dentro del mismo proyecto), poner las variables
de entorno de arriba, y dejar correr `main.py`.

### 5. Probar
Con la app instalada en el workspace, cualquier persona puede escribir `/caso-mercadeo` en
cualquier canal o DM con el bot. Antes de las pruebas del viernes, correr también
`python3 test_bot_mercadeo.py` (no necesita credenciales reales) para confirmar que la lógica
sigue intacta después de cualquier ajuste de último momento.

## Nota sobre los agentes

No hace falta una lista de nombres de agentes para que esto funcione: el bot consulta el nombre
real de quien reporta el caso directamente a la API de Slack usando su ID, en el momento en que
llena el formulario. Esto evita a propósito el mismo problema que tuvimos en Robotín cuando una
persona heredó la cuenta de Slack de otra y quedó una lista desactualizada.
