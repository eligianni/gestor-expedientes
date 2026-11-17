"""Comprobantes: parser del texto pegado del SII (Sistema de Autogestión de Comprobantes Electrónicos) y CAE.

Funciones puras: reciben texto y devuelven datos; no tocan la base ni archivos.
"""
import re
import unicodedata

from gestor import util

# (clave del resultado, rótulo como se muestra, patrón del rótulo tolerante a tildes)
ROTULOS = (
    ("cae", "CAE", r"CAE"),
    ("fecha_emision", "Fecha de emisión", r"Fecha\s+de\s+emisi[oó]n"),
    ("periodo", "Período", r"Per[ií]odo"),
    ("monto_centavos", "Monto", r"Monto"),
    ("tipo_comprobante", "Tipo de Comprobante", r"Tipo\s+de\s+Comprobante"),
    ("nro_comprobante", "Nro Comprobante", r"Nro\.?\s+Comprobante"),
    ("razon_social", "Razón Social", r"Raz[oó]n\s+Social"),
    ("cuit", "CUIT", r"CUIT"),
    ("sap", "Nro SAP", r"Nro\.?\s+SAP"),
    ("area", "Área", r"[AÁ]rea"),
    ("tipo_servicio", "Tipo de Servicio", r"Tipo\s+de\s+Servicio"),
    ("concepto", "Concepto", r"Concepto"),
    ("orden_compra", "Orden de Compra", r"Orden\s+de\s+Compra"),
    ("cod_tramite", "Cod. Trámite", r"Cod\.?\s*Tr[aá]mite"),
)

_RE_CAE = re.compile(r"\d{14}")


def _valor_rotulo(texto, patron):
    m = re.search(r"(?:^|(?<=\s))" + patron + r"[ \t]*:[ \t]*([^\r\n]*)", texto, re.IGNORECASE | re.MULTILINE)
    if m is None:
        return None
    valor = m.group(1).strip()
    return valor or None


def _fecha_iso(valor):
    try:
        return util.iso(util.fecha_desde_texto(valor))
    except (ValueError, TypeError):
        return None


def _periodo(valor):
    texto = valor.strip()
    if re.fullmatch(r"\d{4}-\d{2}", texto):
        return texto
    m = re.fullmatch(r"(\d{1,2})[/-](\d{4})", texto)
    if m is not None:
        return "%s-%02d" % (m.group(2), int(m.group(1)))
    return None


def _nro_comprobante(valor):
    try:
        pv, _, numero = util.normalizar_factura(valor)
    except ValueError:
        return None
    return "%04d-%08d" % (pv, numero)


def _letra(tipo):
    ultima = (tipo or "").split()[-1:] or [""]
    return ultima[0].upper() if re.fullmatch(r"[A-Za-z]", ultima[0]) else None


def analizar_texto_sii(texto):
    """Extrae por rótulo los datos de la factura cargada en el SII. Lo que no aparece queda en None y en `faltantes`."""
    texto = unicodedata.normalize("NFC", texto or "")
    crudos = {}
    faltantes = []
    for clave, nombre, patron in ROTULOS:
        valor = _valor_rotulo(texto, patron)
        crudos[clave] = valor
        if valor is None:
            faltantes.append(nombre)

    def convertir(clave, funcion):
        valor = crudos[clave]
        return funcion(valor) if valor is not None else None

    def centavos(valor):
        try:
            return util.a_centavos(valor)
        except (TypeError, ValueError, ArithmeticError):
            return None

    return {
        "cae": convertir("cae", lambda v: re.sub(r"\s", "", v)),
        "fecha_emision": convertir("fecha_emision", _fecha_iso),
        "periodo": convertir("periodo", _periodo),
        "monto_centavos": convertir("monto_centavos", centavos),
        "tipo_comprobante": convertir("tipo_comprobante", lambda v: " ".join(v.upper().split())),
        "nro_comprobante": convertir("nro_comprobante", _nro_comprobante),
        "letra": _letra(crudos["tipo_comprobante"]),
        "razon_social": crudos["razon_social"],
        "cuit": crudos["cuit"],
        "sap": convertir("sap", util.sap_sin_ceros),
        "area": crudos["area"],
        "tipo_servicio": crudos["tipo_servicio"],
        "concepto": crudos["concepto"],
        "orden_compra": convertir("orden_compra", util.sap_sin_ceros),
        "cod_tramite": crudos["cod_tramite"],
        "faltantes": faltantes,
    }


def cae_valido(cae):
    """El CAE tiene exactamente 14 dígitos."""
    return isinstance(cae, str) and _RE_CAE.fullmatch(cae.strip()) is not None


def vencimiento_cae_ok(fecha_emision, vto):
    """True si el vencimiento del CAE no es anterior a la emisión; None si no hay vencimiento cargado."""
    if vto in (None, ""):
        return None
    if fecha_emision in (None, ""):
        return None
    return util.fecha_desde_texto(vto) >= util.fecha_desde_texto(fecha_emision)
