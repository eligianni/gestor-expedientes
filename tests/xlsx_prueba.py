"""Libros .xlsx de varias hojas armados a mano, para los tests (texto y números tal cual)."""
import io
import zipfile
from xml.sax.saxutils import escape


def _celda(ref, valor):
    if valor is None:
        return ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return '<c r="%s"><v>%s</v></c>' % (ref, valor)
    return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, escape(str(valor)))


def _col(n):
    letras = ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def xlsx_con_hojas(hojas):
    """Bytes de un .xlsx con varias hojas: [(nombre, filas)]."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zf:
        tipos = "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-'
                        'officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(len(hojas)))
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.'
                    'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/'
                    'vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/'
                    'xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
                    'officedocument.spreadsheetml.sheet.main+xml"/>%s</Types>' % tipos)
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                    'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                    '</Relationships>')
        hojas_xml = "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(n), i + 1, i + 1)
                            for i, (n, _) in enumerate(hojas))
        zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.'
                    'openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships"><sheets>%s</sheets></workbook>' % hojas_xml)
        rels = "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                       'relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(hojas)))
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http:'
                    '//schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>' % rels)
        for i, (_, filas) in enumerate(hojas):
            xml_filas = "".join('<row r="%d">%s</row>' % (n, "".join(_celda("%s%d" % (_col(c), n), v)
                                                                      for c, v in enumerate(fila, start=1)))
                                for n, fila in enumerate(filas, start=1))
            zf.writestr("xl/worksheets/sheet%d.xml" % (i + 1), '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns='
                        '"http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>'
                        % xml_filas)
    return salida.getvalue()
