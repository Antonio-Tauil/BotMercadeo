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


def construir_blocks_formulario(categoria):
    """Arma los blocks del modal (paso 2) para la categoría dada, según FORM_SPECS."""
    blocks = []
    for clave, etiqueta, _validador, multilinea in FORM_SPECS[categoria]:
        blocks.append(_bloque_input(clave, etiqueta, multilinea))
    if categoria == "Otros":
        from config import ETIQUETAS_MANUALES
        blocks.append({
            "type": "input",
            "block_id": "Etiqueta",
            "label": {"type": "plain_text", "text": "¿Cuál de estas 4 categorías se parece más a este caso?"},
            "element": {
                "type": "static_select",
                "action_id": "valor",
                "options": [{"text": {"type": "plain_text", "text": e}, "value": e} for e in ETIQUETAS_MANUALES],
            },
        })
    return blocks


def specs_validacion(categoria):
    """Lista [(block_id, tipo_validador), ...] para pasar a la validación genérica."""
    specs = [(clave, validador) for clave, _e, validador, _m in FORM_SPECS[categoria]]
    if categoria == "Otros":
        specs.append(("Etiqueta", "requerido"))
    return specs
