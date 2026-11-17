"""Utilidades puras: textos, montos, fechas, períodos, facturas y números GDE. Sin base ni archivos."""
import re
import unicodedata
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import NamedTuple

# --- Textos ----------------------------------------------------------------

def normalizar_texto(s):
    """NFKD sin marcas combinantes, minúsculas y espacios colapsados."""
    descompuesto = unicodedata.normalize("NFKD", str(s))
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_marcas.lower().split())


def clave_encabezado(s):
    """Encabezado del Excel normalizado para buscar columnas por nombre: "N° O/C" → "n o c"."""
    texto = normalizar_texto(str(s).replace("º", "°"))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


# --- Montos ----------------------------------------------------------------

_DOS_DECIMALES = Decimal("0.01")


def a_decimal(valor, decimales=2):
    """int, Decimal, "1224990.01" o "1.224.990,01" → Decimal redondeado (ROUND_HALF_UP). Nunca float.

    `decimales=None` devuelve el valor exacto, sin redondear.
    """
    if isinstance(valor, bool) or isinstance(valor, float):
        raise TypeError("No se aceptan números float para montos ni cantidades.")
    if isinstance(valor, int):
        numero = Decimal(valor)
    elif isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, str):
        texto = valor.strip().replace("$", "").replace(" ", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            raise ValueError("No es un número válido: %r" % valor) from None
    else:
        raise TypeError("Tipo no soportado para un número: %s" % type(valor).__name__)
    if not numero.is_finite():
        raise ValueError("No es un número válido: %r" % valor)
    if decimales is None:
        return numero
    return numero.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def a_centavos(valor):
    """Monto → centavos int (redondeo ROUND_HALF_UP a 2 decimales)."""
    return int((a_decimal(valor) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def formato_pesos(centavos):
    """122499001 → "1.224.990,01"."""
    centavos = int(centavos)
    signo = "-" if centavos < 0 else ""
    pesos, cc = divmod(abs(centavos), 100)
    return "%s%s,%02d" % (signo, "{:,}".format(pesos).replace(",", "."), cc)


# --- Fechas ----------------------------------------------------------------

_BASE_EXCEL = date(1899, 12, 30)


def fecha_desde_texto(s):
    """dd/mm/aaaa, aaaa-mm-dd o dd.mm.aaaa → date."""
    if isinstance(s, date):
        return s
    texto = str(s).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m is not None:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", texto)
    if m is not None:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    raise ValueError("Fecha inválida: %r (se espera dd/mm/aaaa)" % s)


def fecha_desde_serial_excel(n):
    """Serial de Excel (base 1899-12-30) → date. 45971 → 2025-11-10."""
    return _BASE_EXCEL + timedelta(days=int(a_decimal(n, decimales=0)))


def iso(d):
    return d.isoformat()


def ddmmaaaa(d):
    return d.strftime("%d/%m/%Y")


def fecha_sap(d):
    return d.strftime("%d.%m.%Y")


# --- Períodos --------------------------------------------------------------

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


class Periodo(NamedTuple):
    periodo: str
    desde: date
    hasta: date


def _sumar_meses(anio, mes, delta):
    total = anio * 12 + (mes - 1) + delta
    return total // 12, total % 12 + 1


def _ultimo_dia(anio, mes):
    sig_anio, sig_mes = _sumar_meses(anio, mes, 1)
    return date(sig_anio, sig_mes, 1) - timedelta(days=1)


def periodo_de_fecha(fecha, dia_inicio=1):
    """Período al que pertenece `fecha`. dia_inicio 1 = mes calendario; otro = período que se nombra por el mes en que termina."""
    if not 1 <= dia_inicio <= 28:
        raise ValueError("dia_inicio debe estar entre 1 y 28.")
    if dia_inicio == 1:
        desde = date(fecha.year, fecha.month, 1)
        return Periodo("%04d-%02d" % (fecha.year, fecha.month), desde, _ultimo_dia(fecha.year, fecha.month))
    if fecha.day >= dia_inicio:
        anio_desde, mes_desde = fecha.year, fecha.month
    else:
        anio_desde, mes_desde = _sumar_meses(fecha.year, fecha.month, -1)
    anio_hasta, mes_hasta = _sumar_meses(anio_desde, mes_desde, 1)
    desde = date(anio_desde, mes_desde, dia_inicio)
    hasta = date(anio_hasta, mes_hasta, dia_inicio - 1)
    return Periodo("%04d-%02d" % (anio_hasta, mes_hasta), desde, hasta)


def _partes_periodo(periodo):
    m = re.fullmatch(r"(\d{4})-(\d{2})", str(periodo))
    if m is None:
        raise ValueError("Período inválido: %r (se espera AAAA-MM)" % periodo)
    return m.group(1), m.group(2)


def mm_aa(periodo):
    anio, mes = _partes_periodo(periodo)
    return "%s-%s" % (mes, anio[2:])


def mm_barra_aa(periodo):
    anio, mes = _partes_periodo(periodo)
    return "%s/%s" % (mes, anio[2:])


def mm_aaaa(periodo):
    anio, mes = _partes_periodo(periodo)
    return "%s-%s" % (mes, anio)


# --- Facturas y SAP --------------------------------------------------------

def normalizar_factura(s):
    """"0003B00031812" → (3, "B", 31812); "0002 - 00003908" → (2, None, 3908)."""
    texto = str(s).strip().upper()
    m = re.fullmatch(r"(\d+)\s*([A-Z])?\s*-?\s*(\d+)", texto)
    if m is None:
        m = re.fullmatch(r"([A-Z])\s*(\d+)\s*-\s*(\d+)", texto)
        if m is None:
            raise ValueError("Número de factura inválido: %r" % s)
        return int(m.group(2)), m.group(1), int(m.group(3))
    return int(m.group(1)), m.group(2), int(m.group(3))


def misma_factura(a, b):
    """Mismo punto de venta y número (y misma letra cuando ambas la tienen)."""
    try:
        pv_a, letra_a, num_a = normalizar_factura(a)
        pv_b, letra_b, num_b = normalizar_factura(b)
    except ValueError:
        return False
    if (pv_a, num_a) != (pv_b, num_b):
        return False
    return letra_a is None or letra_b is None or letra_a == letra_b


def sap_sin_ceros(s):
    """"0000077170" → "77170"."""
    texto = str(s).strip()
    sin_ceros = texto.lstrip("0")
    return sin_ceros if sin_ceros else ("0" if texto else "")


# --- GDE -------------------------------------------------------------------

RE_GDE = re.compile(r"^(EX|IF|PV|RM|DOCFI|NO|ME|PROSA|IFGRA|ITFCO)-\d{4}-\d{6,9}-( -)?INSSJP-[A-Z0-9]+#INSSJP$")


def normalizar_gde(s):
    """Mayúsculas, % → #, "-   -" → "- -" y sin el resto de los espacios."""
    texto = str(s).upper().replace("%", "#")
    texto = re.sub(r"-\s+-", "-\x00-", texto)
    texto = re.sub(r"\s+", "", texto)
    return texto.replace("\x00", " ")


def validar_gde(s):
    return RE_GDE.fullmatch(normalizar_gde(s)) is not None
