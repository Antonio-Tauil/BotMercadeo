"""
formularios_casos.py — Define los campos de cada uno de los 9 tipos de caso (tabla 7.2 del
documento de requerimientos) y arma los bloques del modal de Slack para cada uno.

Cada campo es: (clave, etiqueta visible, tipo_validador, multilinea).
'clave' es también el nombre de columna que se usará al guardar en el Sheet — por eso debe
coincidir (ignorando mayúsculas/tildes) con el encabezado real de la hoja "Casos".
"""

# Campos comunes que llevan casi todos los formularios
NOMBRE = ("Nombre", "Nombre", "requerido", False)
CEDULA = ("Cedula", "Cédula", "cedula", False)
EMPRESA = ("Empresa", "Empresa", "requerido", False)
TELEFONO = ("Telefono", "Número de teléfono", "telefono", False)
CORREO = ("Correo", "Correo electrónico", "correo", False)
DESCRIPCION = ("Descripcion", "Descripción", "requerido", True)

# Categorías donde el agente debe adjuntar un documento (foto/PDF/Word) desde el modal de
# Slack — ver ARCHIVO_BLOCK_ID y construir_blocks_formulario() más abajo.
CATEGORIAS_CON_DOCUMENTO = {"Carga de Documentos", "Envío de Contrato"}
ARCHIVO_BLOCK_ID = "Documento"
TIPOS_DE_ARCHIVO_PERMITIDOS = ["pdf", "jpg", "jpeg", "png", "doc", "docx"]
MAX_ARCHIVOS_POR_CASO = 5  # Slack permite subir varios de una vez desde el mismo botón

FORM_SPECS = {
    "Conciliación": [
        NOMBRE, CEDULA, EMPRESA, TELEFONO,
        ("Banco emisor", "Banco emisor", "requerido", False),
        ("Referencia", "Referencia", "requerido", False),
        ("Monto", "Monto", "monto", False),
        ("Fecha de pago", "Fecha de pago (DD/MM/AAAA)", "fecha", False),
        ("Cuotas pagadas", "Cuotas pagadas", "requerido", False),
    ],
    "Liquidación": [NOMBRE, CEDULA, EMPRESA, TELEFONO, DESCRIPCION],
    "Carga de Documentos": [NOMBRE, CEDULA, EMPRESA, DESCRIPCION],
    "Envío de Contrato": [NOMBRE, CEDULA, EMPRESA, CORREO],
    "Acceso": [NOMBRE, CEDULA, TELEFONO, EMPRESA, CORREO],
    "Registro": [NOMBRE, CEDULA, EMPRESA, DESCRIPCION],
    "FAQ": [NOMBRE, CEDULA, TELEFONO, EMPRESA, DESCRIPCION],
    "Baja de Nivel": [NOMBRE, CEDULA, EMPRESA, TELEFONO, DESCRIPCION],
    "Otros": [NOMBRE, CEDULA, EMPRESA, DESCRIPCION],
}


def _bloque_input(block_id, label, multilinea):
    elemento = {
        "type": "plain_text_input",
        "action_id": "valor",
        "multiline": multilinea,
    }
    return {
        "type": "input",
        "block_id": block_id,
        "label": {"type": "plain_text", "text": label},
        "element": elemento,
    }


def _bloque_archivo():
    """Campo de tipo 'file_input': agrega al modal el botón nativo de Slack para adjuntar
    uno o varios archivos (arrastrar o seleccionar varios de una vez) antes de enviar el
    caso. Requiere que la app tenga los scopes 'files:read' y 'files:write' (ver
    README_SETUP.md)."""
    return {
        "type": "input",
        "block_id": ARCHIVO_BLOCK_ID,
        "label": {"type": "plain_text", "text": f"Documentos adjuntos (hasta {MAX_ARCHIVOS_POR_CASO})"},
        "element": {
            "type": "file_input",
            "action_id": "valor",
            "filetypes": TIPOS_DE_ARCHIVO_PERMITIDOS,
            "max_files": MAX_ARCHIVOS_POR_CASO,
        },
    }


def construir_blocks_formulario(categoria):
    """Arma los blocks del modal (paso 2) para la categoría dada, según FORM_SPECS.

    Cada categoría (incluida 'Otros') ya tiene su propia etiqueta fija, mapeada 1:1 en
    config.ETIQUETA_POR_CATEGORIA — el agente ya no elige ninguna etiqueta a mano.
    """
    blocks = []
    for clave, etiqueta, _validador, multilinea in FORM_SPECS[categoria]:
        blocks.append(_bloque_input(clave, etiqueta, multilinea))
    if categoria in CATEGORIAS_CON_DOCUMENTO:
        blocks.append(_bloque_archivo())
    return blocks


def specs_validacion(categoria):
    """Lista [(block_id, tipo_validador), ...] para pasar a la validación genérica."""
    return [(clave, validador) for clave, _e, validador, _m in FORM_SPECS[categoria]]
