"""Lectura de la orden de compra desde el texto de su PDF digital (el que firma GDE).

Puro: recibe texto (extraído con gestor.pdf_texto o pegado desde el visor de PDF) y devuelve un dict. De la OC salen el
objeto de la contratación, la cabecera (número, fechas, vigencia, procedimiento, expediente, proveedor, GDE del PDF) y
los renglones con sus subrenglones. Los subrenglones son los que traen la medida real de los servicios mensuales
(renglón 1 UP = 3 MES × $ 1.224.990,00), que el z_compras2 no muestra.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from gestor import util

__all__ = ("leer_oc", "objeto_sugerido", "articulo_sugerido", "OcIlegible")


class OcIlegible(Exception):
    """El texto no parece una orden de compra de SAP."""


_MONTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_CANTIDAD = r"\d{1,3}(?:\.\d{3})*,\d{1,3}"
_GDE = r"[A-Z]{2,6}-\d{4}-\d+-\s*-?\s*[A-Z0-9]+-[A-Z0-9]+#[A-Z0-9]+"

RE_RENGLON = re.compile(
    r"^\s*(?P<pos>\d{4})\s+(?P<cantidad>%s)\s+(?P<unidad>[A-Za-zÁÉÍÓÚÑ0-9]{1,6})\s+(?P<desc>.*?)"
    r"(?:\s+(?P<monto1>%s))?(?:\s+(?P<monto2>%s))?\s*$" % (_CANTIDAD, _MONTO, _MONTO))
RE_SUBRENGLON = re.compile(
    r"^\s*(?P<pos>\d{2,3})\s+(?P<cantidad>%s)\s+(?P<unidad>[A-Za-zÁÉÍÓÚÑ0-9]{1,6})\s+(?P<desc>.*?)"
    r"(?:\s+(?P<monto1>%s))?(?:\s+(?P<monto2>%s))?\s*$" % (_CANTIDAD, _MONTO, _MONTO))
RE_MONTO_SOLO = re.compile(r"^\s*(%s)\s*$" % _MONTO)
RE_SOLPED = re.compile(r"Sol\.?\s*Ped\.?\s*:\s*(\d+)\s*-\s*Pos\.?\s*:\s*(\d+)", re.IGNORECASE)
RE_PAGINA = re.compile(r"P[áa]gina\s+\d+\s+de\s+\d+", re.IGNORECASE)
RE_CODIGO = re.compile(r"^(\d{5,10})\s*-\s*(.*)$")
RE_ENCABEZADO_SECCION = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ./]{2,45}:")

# Frases donde termina el núcleo del objeto (lo que va en la autorización de pago).
_CORTES_OBJETO = (
    ", por el t", " por el t", ", con destino", " con destino", ", para el ", " para el hospital", " para el laboratorio",
    ", mediante", " mediante modalidad", ", con opci", ", con modalidad", " con modalidad", ", con equipo",
    ", en el marco", ", en los t", " bajo la modalidad",
)
_ARTICULOS = {
    "servicio": "al", "mantenimiento": "al", "alquiler": "al", "suministro": "al", "arrendamiento": "al",
    "abono": "al", "adquisición": "a la", "adquisicion": "a la", "provisión": "a la", "provision": "a la",
    "contratación": "a la", "contratacion": "a la", "locación": "a la", "locacion": "a la", "compra": "a la",
    "reparación": "a la", "reparacion": "a la", "insumos": "a los", "servicios": "a los", "trabajos": "a los",
    "determinaciones": "a las", "prestaciones": "a las", "obras": "a las",
}


def _cantidad(texto):
    """"2.000,00" → "2000"; "3,00" → "3" (texto de Decimal, como en la base)."""
    return _texto_decimal(util.a_decimal(texto, decimales=None))


def _texto_decimal(numero):
    """Decimal → texto sin ceros de más ni notación científica: Decimal("3.00") → "3"."""
    texto = format(numero, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto


def _centavos(texto):
    return util.a_centavos(texto) if texto else None


def _fecha(texto):
    if not texto:
        return None
    try:
        return util.iso(util.fecha_desde_texto(texto))
    except (ValueError, TypeError):
        return None


def _espacios(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def _gde(texto):
    if not texto:
        return ""
    normalizado = util.normalizar_gde(texto)
    return normalizado if util.validar_gde(normalizado) else ""


def _buscar(patron, texto, flags=0):
    m = re.search(patron, texto, flags)
    return m.group(1).strip() if m is not None and m.group(1) is not None else ""


def objeto_sugerido(completo):
    """Núcleo del objeto en minúscula, como va después de «correspondiente al/a la» en la autorización."""
    texto = _espacios(completo).rstrip(".").strip()
    if not texto:
        return ""
    minuscula = texto.lower()
    corte = min((minuscula.find(c) for c in _CORTES_OBJETO if minuscula.find(c) > 0), default=-1)
    if corte > 0:
        texto = texto[:corte]
    texto = texto.strip(" ,.;")
    letras = [c for c in texto if c.isalpha()]
    if letras and sum(1 for c in letras if c.isupper()) / len(letras) > 0.6:
        texto = texto.lower()
    return texto[:1].lower() + texto[1:]


def articulo_sugerido(objeto):
    """«al», «a la», «a los» o «a las» según la primera palabra del objeto."""
    palabra = (objeto or "").split(" ", 1)[0].lower().strip(",.")
    if palabra in _ARTICULOS:
        return _ARTICULOS[palabra]
    if palabra.endswith("ión") or palabra.endswith("ion") or palabra.endswith("a"):
        return "a la"
    if palabra.endswith("as"):
        return "a las"
    if palabra.endswith("s"):
        return "a los"
    return "al"


def _objeto_completo(lineas):
    """Párrafo que sigue a «Objeto de (la) Contratación:» (en la misma línea o en las siguientes)."""
    patron = re.compile(r"objeto\s+de\s+(?:la\s+)?contrataci[oó]n\s*:\s*(.*)$", re.IGNORECASE)
    for i, linea in enumerate(lineas):
        m = patron.search(linea)
        if m is None:
            continue
        partes = [m.group(1).strip()] if m.group(1).strip() else []
        for siguiente in lineas[i + 1:i + 20]:
            texto = siguiente.strip()
            if not texto:
                if partes and " ".join(partes).rstrip().endswith("."):
                    break
                continue
            if RE_ENCABEZADO_SECCION.match(siguiente) or len(partes) >= 8:
                break
            partes.append(texto)
        return _espacios(" ".join(partes))
    return ""


def _seccion_detalle(lineas):
    inicio = next((i for i, l in enumerate(lineas) if "DETALLE DE LA ORDEN" in l.upper()), None)
    if inicio is None:
        return []
    fin = next((i for i in range(inicio + 1, len(lineas)) if re.search(r"Importe\s+Total", lineas[i], re.IGNORECASE)),
               len(lineas))
    return lineas[inicio + 1:fin]


def _armar_item(m):
    desc = _espacios(m.group("desc"))
    codigo = ""
    mc = RE_CODIGO.match(desc)
    if mc is not None:
        codigo, desc = mc.group(1), _espacios(mc.group(2))
    montos = [x for x in (m.group("monto1"), m.group("monto2")) if x]
    cantidad = _cantidad(m.group("cantidad"))
    precio = importe = None
    if len(montos) == 2:
        precio, importe = _centavos(montos[0]), _centavos(montos[1])
    elif len(montos) == 1:
        precio = _centavos(montos[0])
        if Decimal(cantidad) == 1:
            importe = precio
    return {
        "pos": int(m.group("pos")), "cantidad": cantidad, "unidad": m.group("unidad").upper(), "codigo": codigo,
        "descripcion": desc, "precio_centavos": precio, "importe_centavos": importe,
    }


def _importe(cantidad, precio):
    return int((Decimal(cantidad) * precio).to_integral_value(rounding=ROUND_HALF_UP))


def _renglones(lineas, avisos):
    renglones = []
    actual = None
    sub = None
    for crudo in lineas:
        linea = RE_PAGINA.sub(" ", crudo)
        m = RE_RENGLON.match(linea)
        if m is not None:
            actual = _armar_item(m)
            actual.update({"sol_ped": "", "pos_sol_ped": "", "subrenglones": []})
            renglones.append(actual)
            sub = None
            continue
        if actual is None:
            continue
        m = RE_SOLPED.search(linea)
        if m is not None:
            actual["sol_ped"], actual["pos_sol_ped"] = m.group(1), str(int(m.group(2)))
            continue
        m = RE_SUBRENGLON.match(linea)
        if m is not None:
            sub = _armar_item(m)
            actual["subrenglones"].append(sub)
            continue
        m = RE_MONTO_SOLO.match(linea)
        if m is not None:
            destino = sub if sub is not None and sub["importe_centavos"] is None else actual
            if destino["importe_centavos"] is None:
                destino["importe_centavos"] = _centavos(m.group(1))
    for r in renglones:
        for item in [r] + r["subrenglones"]:
            if item["precio_centavos"] is not None and item["importe_centavos"] is None:
                item["importe_centavos"] = _importe(item["cantidad"], item["precio_centavos"])
        if r["precio_centavos"] is not None and r["importe_centavos"] is not None:
            if _importe(r["cantidad"], r["precio_centavos"]) != r["importe_centavos"]:
                avisos.append("Renglón %d: %s × $ %s no da el total $ %s." % (
                    r["pos"], r["cantidad"], util.formato_pesos(r["precio_centavos"]),
                    util.formato_pesos(r["importe_centavos"])))
        r["desglose"] = _desglose(r, avisos)
    return renglones


def _desglose(renglon, avisos):
    """Desglose del renglón según sus subrenglones (cantidad, unidad y precio), o None si no tiene."""
    subs = renglon["subrenglones"]
    if not subs:
        return None
    unidades = {s["unidad"] for s in subs}
    precios = {s["precio_centavos"] for s in subs}
    if len(unidades) != 1 or len(precios) != 1 or None in precios:
        avisos.append("Renglón %d: los subrenglones tienen distinta unidad o precio; revisá el desglose a mano."
                      % renglon["pos"])
        return None
    cantidad = sum((Decimal(s["cantidad"]) for s in subs), Decimal(0))
    precio = subs[0]["precio_centavos"]
    desglose = {"cantidad": _texto_decimal(cantidad), "unidad": subs[0]["unidad"],
                "precio_centavos": precio}
    if desglose["cantidad"] == renglon["cantidad"] and desglose["unidad"] == renglon["unidad"]:
        return None
    if renglon["importe_centavos"] is not None and _importe(cantidad, precio) != renglon["importe_centavos"]:
        avisos.append("Renglón %d: el subrenglón (%s %s × $ %s) no suma el total del renglón $ %s." % (
            renglon["pos"], desglose["cantidad"], desglose["unidad"], util.formato_pesos(precio),
            util.formato_pesos(renglon["importe_centavos"])))
    return desglose


def leer_oc(texto):
    """Datos de la OC desde el texto del PDF. Lanza OcIlegible si no encuentra el número ni renglones."""
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    lineas = texto.split("\n")
    avisos = []

    numero = _buscar(r"N[uú]mero\s*:\s*(45\d{8})\b", texto) or _buscar(r"\bOC\s*N[.°º\s]*\s*(45\d{8})\b", texto)
    renglones = _renglones(_seccion_detalle(lineas), avisos)
    if not numero and not renglones:
        raise OcIlegible("El texto no parece una orden de compra de SAP: no se encontró el número de OC ni renglones.")
    if not renglones:
        avisos.append("No se encontraron renglones en el detalle de la OC.")

    procedimiento = texto
    m = re.search(r"PROCEDIMIENTO DE SELECCI", texto, re.IGNORECASE)
    if m is not None:
        procedimiento = texto[m.end():m.end() + 1500]
    ca = ""
    mca = re.search(r"N[uú]mero\s*:\s*0*(\d+)\s*-\s*(\d{4})\b", procedimiento)
    if mca is not None:
        ca = "%d-%s" % (int(mca.group(1)), mca.group(2))

    gde_pdf = _gde(_buscar(r"N[uú]mero\s*:\s*(IF-\d{4}-\d+-[A-Z0-9]+-[A-Z0-9]+#[A-Z0-9]+)", texto))
    if not gde_pdf:
        candidatos = re.findall(r"\bIF-\d{4}-\d+-[A-Z0-9]+-[A-Z0-9]+#[A-Z0-9]+", texto)
        if candidatos:
            gde_pdf = _gde(max(set(candidatos), key=candidatos.count))

    objeto_completo = _objeto_completo(lineas)
    objeto = objeto_sugerido(objeto_completo)
    if not objeto_completo:
        avisos.append("No se encontró el objeto de la contratación en el PDF.")

    total = _centavos(_buscar(r"Importe\s+Total\s*:\s*(?:ARS|\$)?\s*(%s)" % _MONTO, texto))
    suma = sum(r["importe_centavos"] or 0 for r in renglones)
    if total is not None and renglones and suma != total:
        avisos.append("La suma de los renglones ($ %s) no coincide con el importe total de la OC ($ %s)." % (
            util.formato_pesos(suma), util.formato_pesos(total)))

    return {
        "numero": numero,
        "fecha_oc": _fecha(_buscar(r"Fecha\s*:\s*(\d{2}/\d{2}/\d{4})", texto)),
        "vig_desde": _fecha(_buscar(r"Desde\s*:\s*(\d{2}/\d{2}/\d{4})", texto)),
        "vig_hasta": _fecha(_buscar(r"Hasta\s*:\s*(\d{2}/\d{2}/\d{4})", texto)),
        "prorroga": _espacios(_buscar(r"Opci[oó]n\s+a\s+Pr[oó]rroga\s*:\s*([^\n]*)", texto)),
        "procedimiento": _espacios(_buscar(r"Tipo\s*:[ \t]*([^\n]*?)(?:[ \t]{2,}|[ \t]*Ejercicio|$)", procedimiento,
                                           re.MULTILINE)),
        "ca": ca,
        "expediente_contratacion": _gde(_buscar(r"expediente\s+GDE\s*:\s*(%s)" % _GDE, texto, re.IGNORECASE)),
        "acto_adjudicacion": _gde(_buscar(r"Acto\s+de\s+Adjudicaci[oó]n\s*:\s*(%s)" % _GDE, texto, re.IGNORECASE)),
        "sap": util.sap_sin_ceros(_buscar(r"Proveedor\s+N[º°o.]*\s*:?\s*(\d+)", texto)),
        "razon_social": _espacios(_buscar(r"Señores\s*:\s*(.+?)(?:[ \t]{2,}|$)", texto, re.MULTILINE)),
        "cuit": _buscar(r"C\.U\.I\.T\.\s*:\s*(\d{2}-?\d{8}-?\d)", texto.split("DATOS DEL ADJUDICATARIO", 1)[-1]),
        "gde_pdf_oc": gde_pdf,
        "objeto_completo": objeto_completo,
        "objeto": objeto,
        "objeto_articulo": articulo_sugerido(objeto),
        "importe_total_centavos": total,
        "renglones": renglones,
        "avisos": avisos,
    }
