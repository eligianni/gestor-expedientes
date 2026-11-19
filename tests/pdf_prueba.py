"""PDF de prueba armados a mano (sin bibliotecas) con las variantes que aparecen en los PDF de GDE.

`pdf_desde_texto(texto)` ubica cada tramo de texto (separado por 2+ espacios) en su columna, como el PDF original:
- `fuente="winansi"`: Helvetica simple con /Widths y /Differences para las vocales con tilde.
- `fuente="cid"`: Type0 Identity-H con CMap ToUnicode (como Skia o iText).
- `envolver=True`: la página dibuja un XObject de formulario (así importa GEDO el PDF de SAP).
- `flujo_objetos=True`: las fuentes van dentro de un /ObjStm.
- `actualizacion=True`: agrega una actualización incremental que reemplaza el contenido de la primera página
  (como el sellado de firma); el lector debe usar la última versión.
"""
import re
import zlib

TAM = 7
ANCHO = 600  # milésimas de em: cada carácter mide 4,2 pt con cuerpo 7
X0, Y0, INTERLINEA, LINEAS_POR_PAGINA = 20, 820, 10, 78

_ACENTOS = {"á": "aacute", "é": "eacute", "í": "iacute", "ó": "oacute", "ú": "uacute", "ñ": "ntilde",
            "Á": "Aacute", "É": "Eacute", "Í": "Iacute", "Ó": "Oacute", "Ú": "Uacute", "Ñ": "Ntilde"}


def _cadena_literal(datos):
    return b"(" + datos.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _codificar(texto, fuente):
    if fuente == "cid":
        return b"<" + "".join("%04X" % ord(c) for c in texto).encode("ascii") + b">"
    return _cadena_literal(texto.encode("cp1252", errors="replace"))


def _contenido(lineas, fuente):
    partes = [b"BT", b"/F1 %d Tf" % TAM]
    y_anterior = None
    for i, linea in enumerate(lineas):
        y = Y0 - i * INTERLINEA
        for m in re.finditer(r"\S+(?: \S+)*", linea):
            x = X0 + m.start() * TAM * ANCHO / 1000
            if y_anterior is None:
                partes.append(b"1 0 0 1 %.2f %d Tm" % (x, y))
            else:
                partes.append(b"1 0 0 1 %.2f %d Tm" % (x, y))
            y_anterior = y
            tramo = m.group(0)
            # Partido en dos con un ajuste TJ, como hacen los generadores al cortar palabras por kerning.
            mitad = len(tramo) // 2
            partes.append(b"[" + _codificar(tramo[:mitad], fuente) + b" 0 " + _codificar(tramo[mitad:], fuente) + b"] TJ")
    partes.append(b"ET")
    return b"\n".join(partes)


def _flujo(dic, datos, comprimir=True):
    if comprimir:
        datos = zlib.compress(datos)
        dic = dic + b" /Filter /FlateDecode"
    return b"<<" + dic + b" /Length %d>>\nstream\n" % len(datos) + datos + b"\nendstream"


def _tounicode(caracteres):
    entradas = b"\n".join(b"<%04X> <%04X>" % (ord(c), ord(c)) for c in sorted(caracteres))
    return (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n1 begincodespacerange <0000> <FFFF> "
            b"endcodespacerange\n%d beginbfchar\n" % len(caracteres) + entradas + b"\nendbfchar\nendcmap end end")


def pdf_desde_texto(texto, fuente="winansi", envolver=False, flujo_objetos=False, actualizacion=False):
    paginas = []
    for bloque in texto.split("\f"):
        lineas = bloque.split("\n")
        for i in range(0, max(1, len(lineas)), LINEAS_POR_PAGINA):
            paginas.append(lineas[i:i + LINEAS_POR_PAGINA])

    objetos = {}
    # 1 catálogo, 2 páginas, 3 fuente (y 4, 5 para la CID), a partir de 10 las páginas.
    objetos[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    caracteres = set(c for c in texto if c not in "\n\f")
    if fuente == "cid":
        objetos[3] = b"<< /Type /Font /Subtype /Type0 /BaseFont /Arial /Encoding /Identity-H /DescendantFonts [4 0 R] " \
                     b"/ToUnicode 5 0 R >>"
        objetos[4] = b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Arial /DW %d /W [32 [%d]] >>" % (ANCHO, ANCHO)
        objetos[5] = _flujo(b"", _tounicode(caracteres))
    else:
        diferencias = b" ".join(b"%d /%s" % (ord(c.encode("cp1252")), n.encode("ascii")) for c, n in sorted(_ACENTOS.items()))
        objetos[3] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 32 /LastChar 255 /Widths ["
                      + b" ".join([b"%d" % ANCHO] * 224) + b"] /Encoding << /Type /Encoding /BaseEncoding "
                      b"/WinAnsiEncoding /Differences [" + diferencias + b"] >> >>")
    recursos = b"<< /Font << /F1 3 0 R >> >>"
    kids = []
    for n, lineas in enumerate(paginas):
        pagina, contenido = 10 + n * 3, 11 + n * 3
        kids.append(b"%d 0 R" % pagina)
        datos = _contenido(lineas, fuente)
        if envolver:
            forma = 12 + n * 3
            objetos[forma] = _flujo(b"/Type /XObject /Subtype /Form /BBox [0 0 595 842] /Resources " + recursos, datos)
            objetos[contenido] = _flujo(b"", b"q 1 0 0 1 0 0 cm /X1 Do Q")
            objetos[pagina] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /X1 %d 0 R >> >> "
                               b"/Contents %d 0 R >>" % (forma, contenido))
        else:
            objetos[contenido] = _flujo(b"", datos)
            objetos[pagina] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources %s /Contents %d 0 R >>" % (
                recursos, contenido)
    objetos[2] = b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >>" % len(kids)

    contenido_real = objetos[11]
    if actualizacion:
        objetos[11] = _flujo(b"", b"BT /F1 7 Tf 1 0 0 1 20 800 Tm (" + b"VERSION VIEJA" + b") Tj ET")

    en_flujo = [3, 4] if flujo_objetos and fuente == "cid" else ([3] if flujo_objetos else [])
    salida = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    for num in sorted(objetos):
        if num in en_flujo:
            continue
        salida += b"%d 0 obj\n" % num + objetos[num] + b"\nendobj\n"
    if en_flujo:
        cabecera = b""
        cuerpo = b""
        for num in en_flujo:
            cabecera += b"%d %d " % (num, len(cuerpo))
            cuerpo += objetos[num] + b"\n"
        salida += b"90 0 obj\n" + _flujo(b"/Type /ObjStm /N %d /First %d" % (len(en_flujo), len(cabecera)),
                                         cabecera + cuerpo) + b"\nendobj\n"
    salida += b"xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Root 1 0 R /Size 100 >>\nstartxref\n0\n%%EOF\n"
    if actualizacion:
        salida += b"11 0 obj\n" + contenido_real + b"\nendobj\n"
        salida += b"xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Root 1 0 R /Size 100 /Prev 0 >>\nstartxref\n0\n%%EOF\n"
    return bytes(salida)
