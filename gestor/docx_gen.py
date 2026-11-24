"""Documentos Word: certificado de validación (CV) desde la plantilla del efector y autorización .docx.

Solo stdlib (`zipfile` + `xml.etree.ElementTree`). El CV se completa EN SU LUGAR sobre la plantilla: se reescribe únicamente
`word/document.xml`; todo otro part se copia byte a byte. Los rótulos se buscan por su texto normalizado, uniendo los runs.
"""
import copy
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from gestor import util

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % NS_W
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DOCUMENTO = "word/document.xml"


class ErrorPlantilla(Exception):
    """La plantilla no tiene el rótulo o la tabla esperada."""


# --- XML -----------------------------------------------------------------------

def _namespaces(xml_bytes):
    """[(prefijo, uri)] declarados en el XML, en orden."""
    return [ns for _, ns in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",))]


def _registrar(namespaces):
    for prefijo, uri in namespaces:
        if prefijo and not re.fullmatch(r"ns\d+", prefijo):
            ET.register_namespace(prefijo, uri)


def _serializar(raiz, namespaces):
    """Serializa conservando TODAS las declaraciones del original (mc:Ignorable nombra prefijos que ET descartaría)."""
    texto = ET.tostring(raiz, encoding="unicode")
    fin = texto.index(">")
    apertura = texto[:fin]
    extra = "".join(
        ' xmlns:%s="%s"' % (prefijo, uri) for prefijo, uri in namespaces
        if prefijo and ("xmlns:%s=" % prefijo) not in apertura
    )
    if apertura.endswith("/"):
        apertura = apertura[:-1] + extra + "/"
    else:
        apertura += extra
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + apertura + texto[fin:]).encode("utf-8")


def texto_parrafo(p):
    """Texto del párrafo uniendo los `w:t` de todos sus runs (un rótulo puede estar partido)."""
    return "".join(t.text or "" for t in p.iter(W + "t"))


def _texto_celda(tc):
    return "".join(texto_parrafo(p) for p in tc.findall(W + "p"))


def poner_texto(p, texto):
    """Deja `texto` en el primer run del párrafo (conserva su formato) y vacía los demás."""
    textos = list(p.iter(W + "t"))
    if not textos:
        run = ET.SubElement(p, W + "r")
        rpr_parrafo = p.find(W + "pPr/" + W + "rPr")
        if rpr_parrafo is not None:
            run.append(copy.deepcopy(rpr_parrafo))
        textos = [ET.SubElement(run, W + "t")]
    textos[0].text = texto
    textos[0].set(XML_SPACE, "preserve")
    for t in textos[1:]:
        t.text = ""


def _poner_en_celda(tc, texto):
    parrafos = tc.findall(W + "p")
    if not parrafos:
        parrafos = [ET.SubElement(tc, W + "p")]
    poner_texto(parrafos[0], texto)
    for p in parrafos[1:]:
        for t in p.iter(W + "t"):
            t.text = ""


def _clave(texto):
    return util.normalizar_texto(texto).rstrip(" :").replace(" :", ":")


def celda_derecha_de(tabla, rotulo):
    """La celda que sigue a la que contiene `rotulo` (comparado normalizado); None si no está."""
    buscado = _clave(rotulo)
    for tr in tabla.iter(W + "tr"):
        celdas = tr.findall(W + "tc")
        for i, tc in enumerate(celdas[:-1]):
            if _clave(_texto_celda(tc)) == buscado:
                return celdas[i + 1]
    return None


def _celda(cuerpo, rotulo):
    for tabla in cuerpo.iter(W + "tbl"):
        celda = celda_derecha_de(tabla, rotulo)
        if celda is not None:
            return celda
    raise ErrorPlantilla("La plantilla del CV no tiene el rótulo «%s»." % rotulo)


def _parrafo_que_empieza(cuerpo, inicio):
    buscado = util.normalizar_texto(inicio)
    for p in cuerpo.iter(W + "p"):
        if util.normalizar_texto(texto_parrafo(p)).startswith(buscado):
            return p
    raise ErrorPlantilla("La plantilla del CV no tiene el párrafo «%s»." % inicio)


def _reemplazar_en_runs(p, viejo, nuevo):
    """Reemplaza `viejo` dentro del run que lo contiene (conserva el formato de los demás runs)."""
    for t in p.iter(W + "t"):
        if t.text and viejo in t.text:
            t.text = t.text.replace(viejo, nuevo, 1)
            t.set(XML_SPACE, "preserve")
            return
    poner_texto(p, texto_parrafo(p).replace(viejo, nuevo, 1))


def _tabla_de_renglones(cuerpo):
    for tabla in cuerpo.iter(W + "tbl"):
        filas = tabla.findall(W + "tr")
        if filas and util.normalizar_texto(_texto_celda(filas[0].findall(W + "tc")[0])) == "renglon":
            return tabla
    raise ErrorPlantilla("La plantilla del CV no tiene la tabla de renglones.")


def _completar_renglones(tabla, renglones):
    filas = tabla.findall(W + "tr")
    datos = filas[1:]
    if not datos:
        raise ErrorPlantilla("La tabla de renglones de la plantilla no tiene una fila modelo.")
    modelo = next((f for f in datos if not _texto_celda(f).strip()), datos[0])
    modelo = copy.deepcopy(modelo)
    for fila in datos:
        tabla.remove(fila)
    for renglon in renglones or [{}]:
        fila = copy.deepcopy(modelo)
        valores = [renglon.get(c, "") for c in ("renglon", "descripcion", "cantidad_oc", "cantidad_entregada", "fecha_entrega")]
        for tc, valor in zip(fila.findall(W + "tc"), valores):
            _poner_en_celda(tc, str(valor))
        tabla.append(fila)


# --- Frases ----------------------------------------------------------------------

def frase_validacion(remitos, periodo_texto):
    """1 remito → "Se valida con remito A correspondiente al período P."; varios → "remitos A, B y C correspondientes"."""
    remitos = [r for r in remitos if r]
    if len(remitos) == 1:
        return "Se valida con remito %s correspondiente al período %s." % (remitos[0], periodo_texto)
    lista = "%s y %s" % (", ".join(remitos[:-1]), remitos[-1])
    return "Se valida con remitos %s correspondientes al período %s." % (lista, periodo_texto)


def fecha_larga(fecha):
    """date → "17 de Agosto del 2026" (como la plantilla: mes con mayúscula inicial)."""
    return "%d de %s del %04d" % (fecha.day, util.MESES[fecha.month - 1].capitalize(), fecha.year)


# --- CV --------------------------------------------------------------------------

ANCHO_FECHA = 3098  # twips: entra «24 de Septiembre del 2026» en un renglón


def _ensanchar_fecha(cuerpo):
    """La celda de la fecha es angosta en la plantilla: se ensancha corriendo la tabla a la izquierda (mismo borde derecho)."""
    for tabla in cuerpo.iter(W + "tbl"):
        if celda_derecha_de(tabla, "Buenos Aires,") is None:
            continue
        columnas = tabla.findall(W + "tblGrid/" + W + "gridCol")
        if len(columnas) != 2:
            return
        actual = int(columnas[1].get(W + "w") or 0)
        extra = ANCHO_FECHA - actual
        if extra <= 0:
            return
        columnas[1].set(W + "w", str(ANCHO_FECHA))
        sangria = tabla.find(W + "tblPr/" + W + "tblInd")
        if sangria is not None:
            sangria.set(W + "w", str(max(0, int(sangria.get(W + "w") or 0) - extra)))
        for fila in tabla.findall(W + "tr"):
            celdas = fila.findall(W + "tc")
            if len(celdas) == 2:
                ancho = celdas[1].find(W + "tcPr/" + W + "tcW")
                if ancho is not None:
                    ancho.set(W + "w", str(ANCHO_FECHA))
        return


def generar_cv(ruta_plantilla, datos):
    """Completa la plantilla del CV con `datos` (textos ya formateados) y devuelve el .docx en bytes.

    `datos`: fecha (date), proveedor, sap, expediente, ca, oc, vigencia, rubro, entrega, periodo_texto, objeto,
    renglones [{renglon, descripcion, cantidad_oc, cantidad_entregada, fecha_entrega}], observacion, remitos [números].
    """
    with zipfile.ZipFile(ruta_plantilla) as plantilla:
        partes = [(info, plantilla.read(info.filename)) for info in plantilla.infolist()]
    original = dict((info.filename, contenido) for info, contenido in partes)
    if DOCUMENTO not in original:
        raise ErrorPlantilla("La plantilla no tiene word/document.xml.")
    namespaces = _namespaces(original[DOCUMENTO])
    _registrar(namespaces)
    raiz = ET.fromstring(original[DOCUMENTO])
    cuerpo = raiz.find(W + "body")

    _poner_en_celda(_celda(cuerpo, "Buenos Aires,"), fecha_larga(datos["fecha"]))
    _ensanchar_fecha(cuerpo)
    for rotulo, clave in (("Proveedor:", "proveedor"), ("N° SAP:", "sap"), ("N° Expediente:", "expediente"),
                          ("N° C.A. :", "ca"), ("Orden de Compra:", "oc"), ("Vigencia de la OC :", "vigencia"),
                          ("Rubro:", "rubro"), ("Entrega:", "entrega"), ("Período:", "periodo_texto")):
        _poner_en_celda(_celda(cuerpo, rotulo), datos.get(clave) or "")

    objeto = _parrafo_que_empieza(cuerpo, "Objeto de Contratación:")
    _reemplazar_en_runs(objeto, "_____________", datos.get("objeto") or "")

    _completar_renglones(_tabla_de_renglones(cuerpo), datos.get("renglones") or [])

    if datos.get("observacion"):
        observaciones = _parrafo_que_empieza(cuerpo, "Observaciones:")
        poner_texto(observaciones, "Observaciones: " + datos["observacion"])

    poner_texto(_parrafo_que_empieza(cuerpo, "Se valida con remito"),
                frase_validacion(datos.get("remitos") or [], datos["periodo_texto"]))

    nuevo_documento = _serializar(raiz, namespaces)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zout:
        for info, contenido in partes:
            zout.writestr(info, nuevo_documento if info.filename == DOCUMENTO else contenido)
    return salida.getvalue()


# --- Autorización ----------------------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>'
)


def _escapar(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generar_autorizacion_docx(referencia, cuerpo):
    """.docx mínimo: referencia en negrita y cuerpo justificado (un párrafo por línea)."""
    parrafos = ['<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % _escapar(referencia)]
    for linea in cuerpo.split("\n"):
        parrafos.append('<w:p><w:pPr><w:jc w:val="both"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                        % _escapar(linea))
    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<w:document xmlns:w="%s"><w:body>%s<w:sectPr/></w:body></w:document>' % (NS_W, "".join(parrafos))
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zout.writestr("_rels/.rels", _RELS)
        zout.writestr("word/document.xml", documento)
    return salida.getvalue()
