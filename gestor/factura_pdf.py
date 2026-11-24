"""Datos de una factura a partir del texto de su PDF digital.

Cada proveedor arma la factura a su manera, así que se busca por varios rótulos y formatos habituales (el formato de
ARCA «Punto de Venta / Comp. Nro», «N° 0002 - 00000160», «0003-00031812»…). Lo que no se encuentra queda en None y en
`faltantes`; lo deducido con menos seguridad va en `avisos`. Funciones puras: reciben texto, no tocan la base.
"""
import re
import unicodedata
from datetime import date

from gestor import util

CUIT_INSSJP = "30522763922"

_FECHA = r"(\d{1,2}/\d{1,2}/\d{2,4})"
_IMPORTE = r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
_LETRA_POR_CODIGO = {"1": "A", "6": "B", "11": "C", "51": "M"}
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_DESTINATARIO = re.compile(
    r"INSSJP|INSTITUTO\s+NACIONAL\s+DE\s+SERVICIOS\s+SOCIALES|INST\.?\s+NAC\.?\s+SERV|30-?52276392-?2", re.IGNORECASE)
_DOMICILIO = re.compile(r"PER[UÚ]\s*0*169\b", re.IGNORECASE)

NOMBRES = {
    "numero": "N° de factura", "fecha": "fecha de emisión", "centavos": "importe total", "cae": "CAE",
    "vto_cae": "vencimiento del CAE", "destinatario": "destinatario (INSSJP)", "domicilio": "domicilio (Perú 169)",
}


def _fecha(texto):
    """dd/mm/aa o dd/mm/aaaa → ISO; None si no es una fecha válida."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", texto or "")
    if m is None:
        return None
    anio = int(m.group(3))
    if anio < 100:
        anio += 2000
    try:
        return date(anio, int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def _centavos(texto):
    try:
        return util.a_centavos(texto)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _sin_firmas_gde(texto):
    """Si el PDF viene de GDE, la hoja adicional de firmas no es parte de la factura."""
    corte = re.search(r"Hoja\s+Adicional\s+de\s+Firmas", texto, re.IGNORECASE)
    return texto[:corte.start()] if corte else texto


def _numero(texto):
    m = re.search(r"Punto\s+de\s+Venta\s*:?\s*(\d{1,5})\s+Comp\.?\s*N(?:ro|°|º)\.?\s*:?\s*(\d{1,8})", texto, re.IGNORECASE)
    if m is None:
        m = re.search(r"(?<![\w-])(\d{4,5})\s*-\s*(\d{8})(?![\w-])", texto)
    if m is None:
        return None
    # Tal como figura en la factura (el punto de venta puede tener 4 o 5 dígitos); el número, siempre 8.
    return m.group(1).zfill(4), m.group(2).zfill(8)


def _letra(texto):
    m = re.search(r"\bFACTURA\s+([ABCM])\b", texto)
    if m is None:
        m = re.search(r"(?<![\w.])([ABCM])[ \t]{2,}FACTURA\b|(?<![\w.])([ABCM])\s+FACTURA\b", texto)
        if m is not None:
            return m.group(1) or m.group(2)
    if m is not None:
        return m.group(1)
    m = re.search(r"C[OÓ]D(?:IGO)?\.?\s*N?[°º]?\s*0*(\d{1,2})\b", texto, re.IGNORECASE)
    if m is not None:
        return _LETRA_POR_CODIGO.get(m.group(1))
    return None


def _fecha_emision(texto):
    m = re.search(r"Fecha\s+(?:de\s+)?Emisi[oó]n\s*:?\s*" + _FECHA, texto, re.IGNORECASE)
    if m is not None:
        return _fecha(m.group(1))
    for m in re.finditer(_FECHA, texto):
        previo = texto[max(0, m.start() - 40):m.start()]
        if re.search(r"vto|venc|inicio|actividad", previo, re.IGNORECASE):
            continue
        fecha = _fecha(m.group(1))
        if fecha:
            return fecha
    return None


def _cae(texto):
    m = re.search(r"C\.?A\.?E\.?\s*(?:N[°ºro.]*)?\s*:?\s*(\d{14})\b", texto, re.IGNORECASE)
    return m.group(1) if m else None


def _vto_cae(texto):
    m = re.search(r"C\.?A\.?E\.?[^\n]{0,60}?(?:Vto|Venc)[^0-9\n]{0,25}" + _FECHA, texto, re.IGNORECASE)
    if m is None:
        m = re.search(r"(?:Vto|Venc\w*)\.?\s*(?:de\s+)?(?:del\s+)?C\.?A\.?E\.?\s*:?\s*" + _FECHA, texto, re.IGNORECASE)
    return _fecha(m.group(1)) if m else None


def _importe_total(texto, avisos):
    m = re.search(r"Importe\s+Total\s*:?\s*\$?\s*" + _IMPORTE, texto, re.IGNORECASE)
    if m is None:
        totales = re.findall(r"\bTOTAL\b[^\d\n]{0,25}\$?\s*" + _IMPORTE, texto, re.IGNORECASE)
        if totales:
            return _centavos(totales[-1])
        importes = [c for c in (_centavos(x) for x in re.findall(r"(?<![\d.,])" + _IMPORTE + r"(?![\d,])", texto)) if c]
        if not importes:
            return None
        avisos.append("El importe total no tiene rótulo en la factura: se tomó el mayor importe. Revisalo.")
        return max(importes)
    return _centavos(m.group(1))


def _cuit_emisor(texto):
    for m in re.finditer(r"(?<!\d)(\d{2})-?(\d{8})-?(\d)(?!\d)", texto):
        cuit = "".join(m.groups())
        if cuit != CUIT_INSSJP:
            return cuit
    return None


def _periodo(texto):
    m = re.search(r"Per[ií]odo\s+Facturado\s+Desde\s*:?\s*" + _FECHA + r"\s+Hasta\s*:?\s*" + _FECHA, texto, re.IGNORECASE)
    if m is not None:
        return _fecha(m.group(1)), _fecha(m.group(2))
    m = re.search(r"Per[ií]odo\s*:?\s*(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})", texto, re.IGNORECASE)
    if m is not None:
        mes, anio = _MESES[m.group(1).lower()], int(m.group(2))
        siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
        return date(anio, mes, 1).isoformat(), date.fromordinal(siguiente.toordinal() - 1).isoformat()
    return None, None


def leer_factura(texto, destinatario="INSSJP", domicilio="PERU 169"):
    """Datos de la factura con los nombres de `datos.factura` del expediente, más `letra`, `cuit_emisor`, `faltantes`, `avisos`."""
    texto = _sin_firmas_gde(unicodedata.normalize("NFC", texto or ""))
    avisos = []
    numero = _numero(texto)
    letra = _letra(texto)
    if numero is None:
        numero_texto = None
    elif letra:
        numero_texto = numero[0] + letra + numero[1]
    else:
        numero_texto = numero[0] + "-" + numero[1]
        avisos.append("No figura la letra de la factura (A, B o C): verificala en el PDF.")
    desde, hasta = _periodo(texto)
    oc = re.search(r"(?<!\d)(45\d{8})(?!\d)", texto)
    datos = {
        "numero": numero_texto,
        "letra": letra,
        "fecha": _fecha_emision(texto),
        "centavos": _importe_total(texto, avisos),
        "cae": _cae(texto),
        "vto_cae": _vto_cae(texto),
        "destinatario": destinatario if _DESTINATARIO.search(texto) else None,
        "domicilio": domicilio if _DOMICILIO.search(texto) else None,
        "periodo_desde": desde,
        "periodo_hasta": hasta,
        "cuit_emisor": _cuit_emisor(texto),
        "menciona": {"oc": oc.group(1)} if oc else {},
    }
    datos["faltantes"] = [nombre for clave, nombre in NOMBRES.items() if not datos.get(clave)]
    datos["avisos"] = avisos
    return datos
