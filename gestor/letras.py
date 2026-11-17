"""Importe en letras, en MAYÚSCULAS sin tildes salvo MILLÓN (como los documentos originales)."""
from gestor import util

_UNIDADES = ("", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE")
_DIEZ_A_DIECINUEVE = (
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE",
    "DIECISEIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE",
)
_DECENAS = ("", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_CENTENAS = (
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
)


def _hasta_99(n):
    if n < 10:
        return _UNIDADES[n]
    if n < 20:
        return _DIEZ_A_DIECINUEVE[n - 10]
    decena, unidad = divmod(n, 10)
    if unidad == 0:
        return _DECENAS[decena]
    if decena == 2:
        return "VEINTI" + _UNIDADES[unidad]
    return "%s Y %s" % (_DECENAS[decena], _UNIDADES[unidad])


def _hasta_999(n):
    if n == 100:
        return "CIEN"
    centena, resto = divmod(n, 100)
    partes = [_CENTENAS[centena]] if centena else []
    if resto:
        partes.append(_hasta_99(resto))
    return " ".join(partes)


def _hasta_999999(n):
    miles, resto = divmod(n, 1000)
    partes = []
    if miles == 1:
        partes.append("MIL")
    elif miles > 1:
        partes.append(_hasta_999(miles) + " MIL")
    if resto:
        partes.append(_hasta_999(resto))
    return " ".join(partes)


def numero_a_letras(n):
    """Entero ≥ 0 en letras: 1224990 → "UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA"."""
    n = int(n)
    if n < 0:
        raise ValueError("El importe no puede ser negativo.")
    if n == 0:
        return "CERO"
    millones, resto = divmod(n, 1000000)
    partes = []
    if millones == 1:
        partes.append("UN MILLÓN")
    elif millones > 1:
        partes.append(numero_a_letras(millones) + " MILLONES")
    if resto:
        partes.append(_hasta_999999(resto))
    return " ".join(partes)


def letras_con_centavos(centavos):
    """122499000 → "UN MILLÓN DOSCIENTOS VEINTICUATRO MIL NOVECIENTOS NOVENTA CON 00/100"."""
    pesos, cc = divmod(int(centavos), 100)
    return "%s CON %02d/100" % (numero_a_letras(pesos), cc)


def importe_en_letras(centavos):
    """"PESOS <letras> CON <cc>/100 CENTAVOS ($ <1.224.990,00>-)"."""
    return "PESOS %s CENTAVOS ($ %s-)" % (letras_con_centavos(centavos), util.formato_pesos(centavos))
