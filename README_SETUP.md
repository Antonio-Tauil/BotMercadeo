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

Lo que queda para una fase 2: el comando de resumen personal por agente.

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

## Adjuntar documentos (Carga de Documentos y Envío de Contrato)

Estas dos categorías traen un campo para adjuntar **hasta 5 archivos a la vez** (pdf, jpg, png,
doc, docx) directo en el modal de Slack (el mismo botón deja arrastrar o seleccionar varios de
una sola vez — el límite se ajusta en `MAX_ARCHIVOS_POR_CASO` en `formularios_casos.py`). Los
archivos nacen PRIVADOS (solo la app los ve) — el bot descarga cada uno y los vuelve a publicar
en `CANAL_CASOS_MERCADEO` para que queden con un link visible para todo el equipo, y esos links
(uno por línea) son los que se guardan en la columna **"Documento adjunto"** del Sheet. Si alguno
falla al republicarse, los demás igual quedan guardados normalmente.

Sugerencia: en la columna "Documento adjunto" del Sheet, activa "Ajustar texto" (Formato > Ajuste
de texto > Ajustar) para que se vean todos los links cuando un caso trae más de uno.

Para que esto funcione hace falta:
1. **Agregar 2 scopes nuevos a la app de Slack**: en https://api.slack.com/apps → tu app
   BotMercadeo → "OAuth & Permissions" → "Bot Token Scopes" → agregar `files:read` y `files:write`.
2. **Reinstalar la app** en el workspace (el mismo panel te lo pide con un botón "Reinstall to
   Workspace" en cuanto agregas un scope nuevo). Esto puede generar un `SLACK_BOT_TOKEN` distinto —
   si cambia, hay que actualizarlo en Railway.
3. **Agregar la columna "Documento adjunto"** en la primera fila de las pestañas "Carga de
   Documentos" y "Envío de Contrato" del Sheet (en las otras 7 pestañas NO hace falta esa columna).
4. Instalar la nueva dependencia: `requests` ya está en `requirements.txt` — Railway la instala
   sola en el próximo deploy.

Si algo de esto falta (scope, columna, etc.), el caso se sigue guardando igual — solo se pierde el
link del documento y queda un aviso `⚠️` en los logs de Railway para revisarlo a mano.

## Cambiar el estado del caso desde Slack (botones en la tarjeta)

Cada tarjeta en el canal ahora trae, debajo del pie, botones para cambiar el estado del caso:
**🟡 En espera**, **🟠 Sin respuesta**, **✅ Cerrado**, **🏁 Finalizado** (no hay botón para volver
a "Abierto" porque ese ya es el estado inicial de todo caso nuevo). Cualquier persona que vea el
mensaje puede darle clic — no hace falta escribir ningún comando ni ir al Sheet a buscar la fila.

Al hacer clic:
1. El bot busca la fila del caso en la pestaña correspondiente (usando la columna nueva **"ID
   caso"** — ver más abajo) y actualiza ahí mismo su "Estado" y su "Fecha actualizacion".
2. Publica una confirmación como respuesta en el mismo hilo del mensaje original (por ejemplo:
   "🔁 Estado del caso `FQ-280826-142233` actualizado a *Cerrado* por Antonio") — así queda un
   historial de quién cambió qué y cuándo, sin tener que reconstruir toda la tarjeta.
3. Los botones se quedan activos después de usarlos, para poder seguir moviendo el caso por sus
   distintos estados con el tiempo (por ejemplo: Abierto → En espera → Cerrado).

**El "ID de caso"**: cada caso nuevo ahora se guarda con un identificador único (por ejemplo
`CD-280826-142233` — el prefijo indica la categoría y el resto es la fecha/hora exacta de
creación). Es lo que usa el botón para saber "actualiza ESTA fila y no otra". Esto significa que
hay que:

1. **Agregar la columna "ID caso"** en la primera fila de **las 9 pestañas** del Sheet (a
   diferencia de "Documento adjunto", que solo iba en 2 pestañas, esta va en todas — cualquier
   categoría puede necesitar cambiar de estado). El orden de la columna no importa, el bot la
   busca por nombre — igual que las demás.
2. No hace falta tocar nada más en Slack (los botones usan `chat:write`, que la app ya tiene) ni
   reinstalar la app.

Si a alguna pestaña le falta la columna "ID caso" (por ejemplo, mientras la vas agregando una por
una), el botón no rompe nada — solo responde en el hilo con un aviso `⚠️` explicando que falta esa
columna, para que se agregue y se intente de nuevo.

## Nota sobre los agentes

No hace falta una lista de nombres de agentes para que esto funcione: el bot consulta el nombre
real de quien reporta el caso directamente a la API de Slack usando su ID, en el momento en que
llena el formulario. Esto evita a propósito el mismo problema que tuvimos en Robotín cuando una
persona heredó la cuenta de Slack de otra y quedó una lista desactualizada.
