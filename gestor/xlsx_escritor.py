"""Escritor .xlsx mínimo (zipfile + XML a mano): una hoja, título, encabezados en negrita y montos con formato."""
import io
import re
import zipfile
from datetime import date
from xml.sax.saxutils import escape

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# Estilos: 0 normal, 1 negrita (encabezados y título), 2 número #,##0.00 (montos).
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_RE_NOMBRE_HOJA = re.compile(r"[\[\]:*?/\\]")
# Caracteres de control que XML 1.0 no admite.
_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def letra_columna(numero):
    """1 → "A", 28 → "AB"."""
    letras = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(ord("A") + resto) + letras
    return letras


def valor_monto(centavos):
    """Centavos int → texto numérico para la celda: 122499000 → "1224990.00"."""
    centavos = int(centavos)
    signo = "-" if centavos < 0 else ""
    pesos, cc = divmod(abs(centavos), 100)
    return "%s%d.%02d" % (signo, pesos, cc)


def titulo_con_fecha(titulo, hoy=None):
    hoy = hoy or date.today()
    return "%s — Emitido el %s" % (titulo, hoy.strftime("%d/%m/%Y"))


def _texto_xml(valor):
    return escape(_RE_CONTROL.sub("", str(valor)))


def _celda(referencia, valor, moneda=False, estilo=0):
    if valor is None or valor == "":
        return ""
    if moneda and isinstance(valor, int) and not isinstance(valor, bool):
        return '<c r="%s" s="2"><v>%s</v></c>' % (referencia, valor_monto(valor))
    if isinstance(valor, int) and not isinstance(valor, bool):
        return '<c r="%s"%s><v>%d</v></c>' % (referencia, ' s="%d"' % estilo if estilo else "", valor)
    texto = _texto_xml(valor)
    espacio = ' xml:space="preserve"' if texto != texto.strip() else ""
    return '<c r="%s" t="inlineStr"%s><is><t%s>%s</t></is></c>' % (
        referencia, ' s="%d"' % estilo if estilo else "", espacio, texto)


def hoja_xml(titulo, encabezados, filas, columnas_moneda=()):
    """XML de la hoja: fila 1 título, fila 2 encabezados en negrita, después los datos."""
    moneda = set(columnas_moneda)
    partes = ['<row r="1">%s</row>' % _celda("A1", titulo, estilo=1)]
    partes.append('<row r="2">%s</row>' % "".join(
        _celda("%s2" % letra_columna(i), e, estilo=1) for i, e in enumerate(encabezados, start=1)))
    for n, fila in enumerate(filas, start=3):
        celdas = "".join(
            _celda("%s%d" % (letra_columna(i), n), valor, moneda=(encabezados[i - 1] in moneda) if i <= len(encabezados) else False)
            for i, valor in enumerate(fila, start=1))
        partes.append('<row r="%d">%s</row>' % (n, celdas))
    anchos = "".join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i, i, max(10, min(60, len(str(e)) + 4)))
                     for i, e in enumerate(encabezados, start=1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + ("<cols>%s</cols>" % anchos if anchos else "")
            + "<sheetData>%s</sheetData></worksheet>" % "".join(partes))


def contenido_xlsx(nombre_hoja, titulo, encabezados, filas, columnas_moneda=()):
    """Bytes del .xlsx."""
    nombre = _RE_NOMBRE_HOJA.sub(" ", nombre_hoja or "Hoja1").strip()[:31] or "Hoja1"
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("xl/workbook.xml", _WORKBOOK % escape(nombre, {'"': "&quot;"}))
        zf.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        zf.writestr("xl/styles.xml", _STYLES)
        zf.writestr("xl/worksheets/sheet1.xml", hoja_xml(titulo, list(encabezados), filas, columnas_moneda))
    return salida.getvalue()


def escribir_xlsx(destino, nombre_hoja, titulo, encabezados, filas, columnas_moneda=()):
    """Escribe el .xlsx en `destino` (ruta o archivo binario abierto) y devuelve los bytes escritos."""
    contenido = contenido_xlsx(nombre_hoja, titulo, encabezados, filas, columnas_moneda)
    if hasattr(destino, "write"):
        destino.write(contenido)
    else:
        with open(destino, "wb") as archivo:
            archivo.write(contenido)
    return contenido
