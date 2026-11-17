"""Lector de .xlsx sin dependencias externas: zipfile + xml.etree.ElementTree.

Devuelve los valores como TEXTO tal cual están guardados (sin convertir a float): los ceros a la izquierda y los
espacios internos se conservan; la conversión a números y fechas la hace el importador.
"""
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

_M = "{%s}" % NS_MAIN
_RE_REFERENCIA = re.compile(r"([A-Z]+)(\d+)")

MENSAJE_INVALIDO = "El archivo no es un Excel .xlsx válido."


class XlsxError(Exception):
    """El archivo no se puede leer como .xlsx."""


def _columna(referencia):
    """"A1" → 1, "AB12" → 28."""
    m = _RE_REFERENCIA.match(referencia or "")
    if m is None:
        return None
    numero = 0
    for letra in m.group(1):
        numero = numero * 26 + (ord(letra) - ord("A") + 1)
    return numero


def _texto_si(si):
    """Texto de un <si> o <is>: todos sus <t> (directos o dentro de <r>), sin la guía fonética <rPh>."""
    partes = []
    for hijo in si:
        if hijo.tag == _M + "t":
            partes.append(hijo.text or "")
        elif hijo.tag == _M + "r":
            for t in hijo.iter(_M + "t"):
                partes.append(t.text or "")
    return "".join(partes)


def _rutas_hojas(zf):
    """Rutas de las hojas en el orden del libro (xl/workbook.xml + sus relaciones)."""
    libro = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    destinos = {}
    for rel in rels.iter("{%s}Relationship" % NS_REL_PKG):
        destino = rel.get("Target") or ""
        if destino.startswith("/"):
            ruta = destino.lstrip("/")
        else:
            ruta = posixpath.normpath(posixpath.join("xl", destino))
        destinos[rel.get("Id")] = ruta
    rutas = []
    hojas = libro.find(_M + "sheets")
    if hojas is not None:
        for hoja in hojas.findall(_M + "sheet"):
            rid = hoja.get("{%s}id" % NS_REL_DOC)
            if rid in destinos:
                rutas.append(destinos[rid])
    return rutas


def _cadenas_compartidas(zf):
    try:
        datos = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    raiz = ET.fromstring(datos)
    return [_texto_si(si) for si in raiz.findall(_M + "si")]


def _valor_celda(c, cadenas):
    tipo = c.get("t")
    if tipo == "inlineStr":
        es = c.find(_M + "is")
        return _texto_si(es) if es is not None else None
    v = c.find(_M + "v")
    if v is None or v.text is None:
        return None
    if tipo == "s":
        return cadenas[int(v.text)]
    return v.text  # "str", "b", "e", "n" y numéricas: el texto tal cual


def _filas_de_hoja(raiz, cadenas):
    datos_hoja = raiz.find(_M + "sheetData")
    if datos_hoja is None:
        return []
    filas = []
    for row in datos_hoja.findall(_M + "row"):
        fila = []
        for c in row.findall(_M + "c"):
            columna = _columna(c.get("r"))
            if columna is None:
                columna = len(fila) + 1
            while len(fila) < columna - 1:
                fila.append(None)
            valor = _valor_celda(c, cadenas)
            if len(fila) == columna - 1:
                fila.append(valor)
            else:
                fila[columna - 1] = valor
        filas.append(fila)
    return filas


def leer_filas(origen):
    """Filas de la primera hoja con al menos una <row>, cada una como lista de texto o None.

    `origen`: ruta, archivo binario abierto o bytes con el contenido.
    """
    if isinstance(origen, (bytes, bytearray)):
        origen = io.BytesIO(origen)
    try:
        with zipfile.ZipFile(origen) as zf:
            cadenas = _cadenas_compartidas(zf)
            for ruta in _rutas_hojas(zf):
                try:
                    raiz = ET.fromstring(zf.read(ruta))
                except KeyError:
                    continue
                if raiz.find("%ssheetData/%srow" % (_M, _M)) is not None:
                    return _filas_de_hoja(raiz, cadenas)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, IndexError, EOFError):
        raise XlsxError(MENSAJE_INVALIDO) from None
    raise XlsxError(MENSAJE_INVALIDO)


def leer_tabla(origen):
    """(encabezados, filas): la primera fila son los encabezados; cada fila siguiente es un dict encabezado → valor."""
    filas = leer_filas(origen)
    encabezados = [(valor or "").strip() for valor in filas[0]]
    tabla = []
    for fila in filas[1:]:
        tabla.append({
            encabezado: (fila[i] if i < len(fila) else None)
            for i, encabezado in enumerate(encabezados)
        })
    return encabezados, tabla
