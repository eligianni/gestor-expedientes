"""Texto de un PDF digital, solo con la biblioteca estándar (sin OCR).

Lee los objetos del archivo (también los de flujos de objetos y actualizaciones incrementales, como las firmas de GDE),
descomprime los contenidos, decodifica las fuentes (ToUnicode, WinAnsi, Differences) y arma el texto de cada página por
posición: los fragmentos de una misma altura forman una línea y las columnas se separan con espacios, parecido a
`pdftotext -layout`. Las coordenadas son geometría de la página (float); nunca montos.
"""
import hashlib
import math
import re
import unicodedata
import zlib

__all__ = ("PdfError", "paginas", "texto_de_pdf")


class PdfError(Exception):
    """El archivo no es un PDF legible o no tiene texto."""


# --- Objetos -----------------------------------------------------------------

class Nombre(str):
    """/Nombre de PDF (sin la barra)."""


class Operador(str):
    """Palabra clave u operador de un flujo de contenido."""


class Ref:
    __slots__ = ("num", "gen")

    def __init__(self, num, gen):
        self.num, self.gen = num, gen

    def __repr__(self):
        return "Ref(%d, %d)" % (self.num, self.gen)


class Flujo:
    __slots__ = ("dic", "crudo")

    def __init__(self, dic, crudo):
        self.dic, self.crudo = dic, crudo


_BLANCOS = b" \t\r\n\f\x00"
_DELIMITADORES = b"()<>[]{}/%"
_RE_NUMERO = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_RE_PALABRA = re.compile(rb"[^ \t\r\n\f\x00()<>\[\]{}/%]+")
_ESCAPES = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f",
            ord("("): b"(", ord(")"): b")", ord("\\"): b"\\"}


class _Lector:
    """Tokenizador de la sintaxis de PDF sobre bytes."""

    def __init__(self, datos, pos=0):
        self.datos, self.pos = datos, pos

    def saltar_blancos(self):
        datos, n = self.datos, len(self.datos)
        while self.pos < n:
            c = datos[self.pos]
            if c in _BLANCOS:
                self.pos += 1
            elif c == 0x25:  # % comentario
                fin = datos.find(b"\n", self.pos)
                fin2 = datos.find(b"\r", self.pos)
                candidatos = [x for x in (fin, fin2) if x != -1]
                self.pos = min(candidatos) + 1 if candidatos else n
            else:
                break

    def token(self):
        """Siguiente token: valores simples, Operador, o marcadores '<<' '>>' '[' ']'. None al final."""
        self.saltar_blancos()
        datos = self.datos
        if self.pos >= len(datos):
            return None
        c = datos[self.pos]
        if c == 0x28:  # (
            return self._literal()
        if c == 0x3C:  # <
            if datos[self.pos + 1:self.pos + 2] == b"<":
                self.pos += 2
                return Operador("<<")
            return self._hexa()
        if c == 0x3E:  # >
            if datos[self.pos + 1:self.pos + 2] == b">":
                self.pos += 2
                return Operador(">>")
            self.pos += 1
            return self.token()
        if c in (0x5B, 0x5D, 0x7B, 0x7D):  # [ ] { }
            self.pos += 1
            return Operador(chr(c))
        if c == 0x2F:  # /
            m = _RE_PALABRA.match(datos, self.pos + 1)
            crudo = m.group(0) if m is not None else b""
            self.pos += 1 + len(crudo)
            return Nombre(re.sub(rb"#([0-9A-Fa-f]{2})", lambda x: bytes([int(x.group(1), 16)]), crudo).decode("latin-1"))
        m = _RE_PALABRA.match(datos, self.pos)
        if m is None:
            self.pos += 1
            return self.token()
        palabra = m.group(0)
        self.pos = m.end()
        if _RE_NUMERO.fullmatch(palabra):
            return float(palabra) if b"." in palabra else int(palabra)
        if palabra == b"true":
            return True
        if palabra == b"false":
            return False
        if palabra == b"null":
            return None
        return Operador(palabra.decode("latin-1"))

    def _literal(self):
        datos, n = self.datos, len(self.datos)
        self.pos += 1
        salida = bytearray()
        nivel = 1
        while self.pos < n:
            c = datos[self.pos]
            self.pos += 1
            if c == 0x5C:  # barra invertida
                if self.pos >= n:
                    break
                e = datos[self.pos]
                self.pos += 1
                if e in _ESCAPES:
                    salida += _ESCAPES[e]
                elif 0x30 <= e <= 0x37:
                    octal = bytes([e])
                    while len(octal) < 3 and self.pos < n and 0x30 <= datos[self.pos] <= 0x37:
                        octal += bytes([datos[self.pos]])
                        self.pos += 1
                    salida.append(int(octal, 8) & 0xFF)
                elif e == 0x0D:
                    if datos[self.pos:self.pos + 1] == b"\n":
                        self.pos += 1
                elif e == 0x0A:
                    pass
                else:
                    salida.append(e)
            elif c == 0x28:
                nivel += 1
                salida.append(c)
            elif c == 0x29:
                nivel -= 1
                if nivel == 0:
                    break
                salida.append(c)
            else:
                salida.append(c)
        return bytes(salida)

    def _hexa(self):
        fin = self.datos.find(b">", self.pos)
        if fin == -1:
            fin = len(self.datos)
        hexa = re.sub(rb"[^0-9A-Fa-f]", b"", self.datos[self.pos + 1:fin])
        self.pos = fin + 1
        if len(hexa) % 2:
            hexa += b"0"
        return bytes.fromhex(hexa.decode("ascii"))

    def objeto(self, primero=None):
        """Lee un objeto completo (dic, lista, Ref, valor). `primero` es un token ya leído."""
        t = self.token() if primero is None else primero
        if isinstance(t, Operador):
            if t == "<<":
                dic = {}
                while True:
                    clave = self.token()
                    if clave is None or clave == ">>":
                        return dic
                    if not isinstance(clave, Nombre):
                        continue
                    dic[str(clave)] = self.objeto()
            if t == "[":
                lista = []
                while True:
                    s = self.token()
                    if s is None or s == "]":
                        return _juntar_refs(lista)
                    lista.append(self.objeto(s))
        if isinstance(t, int) and not isinstance(t, bool):
            guardada = self.pos
            gen = self.token()
            if isinstance(gen, int) and not isinstance(gen, bool):
                r = self.token()
                if r == "R":
                    return Ref(t, gen)
            self.pos = guardada
        return t


def _juntar_refs(lista):
    return lista  # las Ref ya se arman en objeto() al leer cada elemento


# --- Filtros -----------------------------------------------------------------

def _flate(datos):
    try:
        return zlib.decompress(datos)
    except zlib.error:
        pass
    for wbits in (15, -15):
        try:
            d = zlib.decompressobj(wbits)
            return d.decompress(datos)
        except zlib.error:
            continue
    return b""


def _ascii_hex(datos):
    hexa = re.sub(rb"[^0-9A-Fa-f]", b"", datos.split(b">")[0])
    if len(hexa) % 2:
        hexa += b"0"
    return bytes.fromhex(hexa.decode("ascii"))


def _ascii85(datos):
    datos = re.sub(rb"\s", b"", datos)
    if datos.startswith(b"<~"):
        datos = datos[2:]
    fin = datos.find(b"~>")
    if fin != -1:
        datos = datos[:fin]
    salida = bytearray()
    grupo = []
    for c in datos:
        if c == ord("z") and not grupo:
            salida += b"\x00\x00\x00\x00"
            continue
        grupo.append(c - 33)
        if len(grupo) == 5:
            valor = 0
            for g in grupo:
                valor = valor * 85 + g
            salida += (valor & 0xFFFFFFFF).to_bytes(4, "big")
            grupo = []
    if grupo:
        faltan = 5 - len(grupo)
        grupo += [84] * faltan
        valor = 0
        for g in grupo:
            valor = valor * 85 + g
        salida += (valor & 0xFFFFFFFF).to_bytes(4, "big")[:4 - faltan]
    return bytes(salida)


def _lzw(datos, cambio_temprano=1):
    salida = bytearray()
    tabla = [bytes([i]) for i in range(256)] + [b"", b""]
    ancho, bits, nbits, anterior = 9, 0, 0, None
    for byte in datos:
        bits = (bits << 8) | byte
        nbits += 8
        while nbits >= ancho:
            nbits -= ancho
            codigo = (bits >> nbits) & ((1 << ancho) - 1)
            if codigo == 256:
                tabla = tabla[:258]
                ancho, anterior = 9, None
                continue
            if codigo == 257:
                return bytes(salida)
            if anterior is None:
                entrada = tabla[codigo] if codigo < len(tabla) else b""
            elif codigo < len(tabla):
                entrada = tabla[codigo]
                tabla.append(anterior + entrada[:1])
            else:
                entrada = anterior + anterior[:1]
                tabla.append(entrada)
            salida += entrada
            anterior = entrada
            if len(tabla) + cambio_temprano >= (1 << ancho) and ancho < 12:
                ancho += 1
    return bytes(salida)


def _run_length(datos):
    salida = bytearray()
    i = 0
    while i < len(datos):
        n = datos[i]
        if n == 128:
            break
        if n < 128:
            salida += datos[i + 1:i + 2 + n]
            i += n + 2
        else:
            salida += datos[i + 1:i + 2] * (257 - n)
            i += 2
    return bytes(salida)


def _predictor(datos, parametros):
    predictor = int(parametros.get("Predictor", 1) or 1)
    if predictor < 10:
        return datos
    columnas = int(parametros.get("Columns", 1) or 1)
    colores = int(parametros.get("Colors", 1) or 1)
    bpc = int(parametros.get("BitsPerComponent", 8) or 8)
    bpp = max(1, colores * bpc // 8)
    fila_len = (columnas * colores * bpc + 7) // 8
    salida = bytearray()
    anterior = bytearray(fila_len)
    i = 0
    while i + fila_len < len(datos) + 1 and i < len(datos):
        tipo = datos[i]
        fila = bytearray(datos[i + 1:i + 1 + fila_len])
        fila += bytes(fila_len - len(fila))
        for j in range(fila_len):
            izq = fila[j - bpp] if j >= bpp else 0
            arr = anterior[j]
            diag = anterior[j - bpp] if j >= bpp else 0
            if tipo == 1:
                fila[j] = (fila[j] + izq) & 0xFF
            elif tipo == 2:
                fila[j] = (fila[j] + arr) & 0xFF
            elif tipo == 3:
                fila[j] = (fila[j] + (izq + arr) // 2) & 0xFF
            elif tipo == 4:
                p = izq + arr - diag
                pa, pb, pc = abs(p - izq), abs(p - arr), abs(p - diag)
                fila[j] = (fila[j] + (izq if pa <= pb and pa <= pc else arr if pb <= pc else diag)) & 0xFF
        salida += fila
        anterior = fila
        i += fila_len + 1
    return bytes(salida)



# --- Descifrado (PDF con «contraseña de propietario» pero que se abre sin contraseña) -------------------------------
# Muchos PDF (ARCA, SII) vienen cifrados solo para restringir permisos: la contraseña para abrirlos es vacía. Se
# descifran con el manejador estándar: RC4 (40/128 bits), AES-128 (AESV2) y AES-256 (AESV3, R5/R6). Todo en Python puro.

_RELLENO = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")


def _rc4(clave, datos):
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + clave[i % len(clave)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    i = j = 0
    salida = bytearray(len(datos))
    for k, byte in enumerate(datos):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        salida[k] = byte ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(salida)


def _xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a, b):
    resultado = 0
    while b:
        if b & 1:
            resultado ^= a
        a = _xtime(a)
        b >>= 1
    return resultado


def _cajas():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inversa = [0] * 256
    for i, v in enumerate(sbox):
        inversa[v] = i
    return sbox, inversa


_SBOX, _SBOX_INV = _cajas()


def _expandir(clave):
    nk = len(clave) // 4
    rondas = nk + 6
    w = [list(clave[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (rondas + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(rondas + 1)]


def _aes_bloque(claves, bloque, descifrar):
    estado = [b ^ k for b, k in zip(bloque, claves[-1 if descifrar else 0])]
    rondas = len(claves) - 1
    filas = (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)
    filas_inv = (0, 13, 10, 7, 4, 1, 14, 11, 8, 5, 2, 15, 12, 9, 6, 3)
    for r in range(1, rondas + 1):
        if descifrar:
            estado = [_SBOX_INV[estado[i]] for i in filas_inv]
            estado = [b ^ k for b, k in zip(estado, claves[rondas - r])]
            if r != rondas:
                nuevo = []
                for c in range(4):
                    a = estado[4 * c:4 * c + 4]
                    nuevo += [_mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9),
                              _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13),
                              _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11),
                              _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)]
                estado = nuevo
        else:
            estado = [_SBOX[estado[i]] for i in filas]
            if r != rondas:
                nuevo = []
                for c in range(4):
                    a = estado[4 * c:4 * c + 4]
                    nuevo += [_xtime(a[0]) ^ _xtime(a[1]) ^ a[1] ^ a[2] ^ a[3],
                              a[0] ^ _xtime(a[1]) ^ _xtime(a[2]) ^ a[2] ^ a[3],
                              a[0] ^ a[1] ^ _xtime(a[2]) ^ _xtime(a[3]) ^ a[3],
                              _xtime(a[0]) ^ a[0] ^ a[1] ^ a[2] ^ _xtime(a[3])]
                estado = nuevo
            estado = [b ^ k for b, k in zip(estado, claves[r])]
    return bytes(estado)


def aes_cbc(clave, iv, datos, descifrar=True):
    """AES-CBC sin relleno (128 o 256 bits). `datos` debe tener largo múltiplo de 16."""
    claves = _expandir(clave)
    salida = bytearray()
    previo = iv
    for i in range(0, len(datos) - len(datos) % 16, 16):
        bloque = datos[i:i + 16]
        if descifrar:
            salida += bytes(a ^ b for a, b in zip(_aes_bloque(claves, bloque, True), previo))
            previo = bloque
        else:
            previo = _aes_bloque(claves, bytes(a ^ b for a, b in zip(bloque, previo)), False)
            salida += previo
    return bytes(salida)


def _aes_descifrar(clave, datos):
    """AESV2/AESV3: los primeros 16 bytes son el IV; al final, relleno PKCS#5."""
    if len(datos) < 32:
        return b""
    plano = aes_cbc(clave, datos[:16], datos[16:])
    relleno = plano[-1] if plano else 0
    return plano[:-relleno] if 0 < relleno <= 16 else plano


def _hash_r6(contrasena, sal, extra):
    """Algoritmo 2.B (PDF 2.0) para AES-256 revisión 6."""
    k = hashlib.sha256(contrasena + sal + extra).digest()
    ronda = 0
    while True:
        k1 = (contrasena + k + extra) * 64
        e = aes_cbc(k[:16], k[16:32], k1, descifrar=False)
        modulo = int.from_bytes(e[:16], "big") % 3
        k = (hashlib.sha256, hashlib.sha384, hashlib.sha512)[modulo](e).digest()
        ronda += 1
        if ronda >= 64 and e[-1] <= ronda - 32:
            return k[:32]


class _Descifrador:
    """Descifra cadenas y flujos con la contraseña de usuario vacía; `ok` es False si hace falta una contraseña."""

    def __init__(self, encrypt, id0):
        self.ok = False
        self.v = int(encrypt.get("V") or 0)
        self.r = int(encrypt.get("R") or 0)
        o, u = bytes(encrypt.get("O") or b""), bytes(encrypt.get("U") or b"")
        self.metodo_flujos = self.metodo_cadenas = "RC4"
        if self.v >= 4:
            filtros = encrypt.get("CF") if isinstance(encrypt.get("CF"), dict) else {}

            def metodo(nombre):
                if nombre == "Identity":
                    return "Identity"
                cfm = (filtros.get(nombre) or {}).get("CFM") if isinstance(filtros.get(nombre), dict) else None
                return {"AESV2": "AESV2", "AESV3": "AESV3", "None": "Identity"}.get(cfm, "RC4")

            self.metodo_flujos = metodo(encrypt.get("StmF", "Identity"))
            self.metodo_cadenas = metodo(encrypt.get("StrF", "Identity"))
        self.cifra_metadatos = encrypt.get("EncryptMetadata", True) is not False
        if self.r >= 5:
            if self.r == 6:
                if _hash_r6(b"", u[32:40], b"") != u[:32]:
                    return
                intermedia = _hash_r6(b"", u[40:48], b"")
            else:
                if hashlib.sha256(u[32:40]).digest() != u[:32]:
                    return
                intermedia = hashlib.sha256(u[40:48]).digest()
            self.clave = aes_cbc(intermedia, bytes(16), bytes(encrypt.get("UE") or b"")[:32])
            self.ok = True
            return
        largo = 5 if self.r == 2 else int(encrypt.get("Length") or 40) // 8
        p = int(encrypt.get("P") or 0) & 0xFFFFFFFF
        base = _RELLENO + o[:32] + p.to_bytes(4, "little") + id0
        if self.r >= 4 and not self.cifra_metadatos:
            base += b"\xff\xff\xff\xff"
        clave = hashlib.md5(base).digest()
        if self.r >= 3:
            for _ in range(50):
                clave = hashlib.md5(clave[:largo]).digest()
        self.clave = clave[:largo]
        if self.r == 2:
            self.ok = _rc4(self.clave, _RELLENO) == u[:32]
        else:
            prueba = _rc4(self.clave, hashlib.md5(_RELLENO + id0).digest())
            for i in range(1, 20):
                prueba = _rc4(bytes(b ^ i for b in self.clave), prueba)
            self.ok = prueba == u[:16]

    def _clave_objeto(self, num, gen, aes):
        if self.r >= 5:
            return self.clave
        extra = num.to_bytes(3, "little") + gen.to_bytes(2, "little") + (b"sAlT" if aes else b"")
        return hashlib.md5(self.clave + extra).digest()[:min(len(self.clave) + 5, 16)]

    def descifrar(self, datos, num, gen, flujo):
        metodo = self.metodo_flujos if flujo else self.metodo_cadenas
        if metodo == "Identity" or not datos:
            return datos
        if metodo in ("AESV2", "AESV3"):
            return _aes_descifrar(self._clave_objeto(num, gen, True), datos)
        return _rc4(self._clave_objeto(num, gen, False), datos)

class _Documento:
    def __init__(self, datos):
        if not datos.lstrip()[:5].startswith(b"%PDF") and b"%PDF-" not in datos[:1024]:
            raise PdfError("El archivo no es un PDF.")
        self.datos = datos
        self.objetos = {}
        self._cache = {}
        self._leer_objetos()

    # Objetos sueltos ("n g obj … endobj"); los posteriores (actualizaciones incrementales) reemplazan a los anteriores.
    def _leer_objetos(self):
        datos = self.datos
        definiciones = {}
        generaciones = {}
        for m in re.finditer(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b", datos):
            num = int(m.group(1))
            generaciones[num] = int(m.group(2))
            lector = _Lector(datos, m.end())
            try:
                valor = lector.objeto()
                if isinstance(valor, dict):
                    guardada = lector.pos
                    siguiente = lector.token()
                    if siguiente == "stream":
                        valor = Flujo(valor, self._datos_flujo(valor, lector.pos))
                    else:
                        lector.pos = guardada
            except (IndexError, ValueError):
                continue
            definiciones[num] = (m.start(), valor)
        self.objetos = {num: valor for num, (_, valor) in definiciones.items()}
        self._leer_trailers()
        self._descifrar(definiciones, generaciones)
        # Flujos de objetos (PDF 1.5+): sus objetos valen si el flujo es posterior a la definición suelta.
        for num, (posicion, valor) in sorted(definiciones.items(), key=lambda x: x[1][0]):
            if isinstance(valor, Flujo) and valor.dic.get("Type") == "ObjStm":
                for interno, objeto in self._objetos_de_flujo(valor):
                    previo = definiciones.get(interno)
                    if previo is None or previo[0] < posicion:
                        definiciones[interno] = (posicion, objeto)
                        self.objetos[interno] = objeto

    def _leer_trailers(self):
        self.trailers = []
        for m in re.finditer(rb"trailer\s*<<", self.datos):
            try:
                self.trailers.append(_Lector(self.datos, m.end() - 2).objeto())
            except (IndexError, ValueError):
                continue
        for valor in self.objetos.values():
            if isinstance(valor, Flujo) and valor.dic.get("Type") == "XRef":
                self.trailers.append(valor.dic)

    def _descifrar(self, definiciones, generaciones):
        """Si el PDF está cifrado, descifra cadenas y flujos (objetos sueltos) con la contraseña vacía."""
        self.con_contrasena = False
        trailer = next((t for t in self.trailers if isinstance(t, dict) and t.get("Encrypt") is not None), None)
        if trailer is None:
            return
        ref = trailer.get("Encrypt")
        encrypt = self.resolver(ref)
        ids = self.resolver(trailer.get("ID"))
        id0 = bytes(ids[0]) if isinstance(ids, list) and ids and isinstance(ids[0], bytes) else b""
        if not isinstance(encrypt, dict) or self.resolver(encrypt.get("Filter")) != "Standard":
            self.con_contrasena = True
            return
        descifrador = _Descifrador({k: self.resolver(v) for k, v in encrypt.items()}, id0)
        if not descifrador.ok:
            self.con_contrasena = True
            return
        excluido = ref.num if isinstance(ref, Ref) else None

        def recorrer(valor, num, gen):
            if isinstance(valor, bytes) and not isinstance(valor, (Nombre, Operador)):
                return descifrador.descifrar(valor, num, gen, False)
            if isinstance(valor, dict):
                return {k: recorrer(v, num, gen) for k, v in valor.items()}
            if isinstance(valor, list):
                return [recorrer(v, num, gen) for v in valor]
            return valor

        for num, (posicion, valor) in list(definiciones.items()):
            if num == excluido or valor is encrypt:
                continue
            gen = generaciones.get(num, 0)
            if isinstance(valor, Flujo):
                tipo = valor.dic.get("Type")
                if tipo == "XRef" or (tipo == "Metadata" and not descifrador.cifra_metadatos):
                    continue
                nuevo = Flujo(recorrer(valor.dic, num, gen), descifrador.descifrar(valor.crudo, num, gen, True))
            else:
                nuevo = recorrer(valor, num, gen)
            definiciones[num] = (posicion, nuevo)
            self.objetos[num] = nuevo

    def _datos_flujo(self, dic, pos):
        datos = self.datos
        if datos[pos:pos + 2] == b"\r\n":
            pos += 2
        elif datos[pos:pos + 1] in (b"\n", b"\r"):
            pos += 1
        largo = dic.get("Length")
        if isinstance(largo, int) and not isinstance(largo, bool) and largo >= 0:
            cola = datos[pos + largo:pos + largo + 20].lstrip(_BLANCOS)
            if cola.startswith(b"endstream"):
                return datos[pos:pos + largo]
        fin = datos.find(b"endstream", pos)
        if fin == -1:
            return datos[pos:]
        crudo = datos[pos:fin]
        if crudo.endswith(b"\r\n"):
            return crudo[:-2]
        if crudo.endswith(b"\n") or crudo.endswith(b"\r"):
            return crudo[:-1]
        return crudo

    def _objetos_de_flujo(self, flujo):
        datos = self.decodificar(flujo)
        try:
            cantidad = int(flujo.dic.get("N", 0))
            primero = int(flujo.dic.get("First", 0))
        except (TypeError, ValueError):
            return []
        lector = _Lector(datos)
        pares = []
        for _ in range(cantidad):
            num, desplazamiento = lector.token(), lector.token()
            if not isinstance(num, int) or not isinstance(desplazamiento, int):
                break
            pares.append((num, desplazamiento))
        objetos = []
        for num, desplazamiento in pares:
            try:
                objetos.append((num, _Lector(datos, primero + desplazamiento).objeto()))
            except (IndexError, ValueError):
                continue
        return objetos

    def resolver(self, valor, profundidad=0):
        while isinstance(valor, Ref) and profundidad < 32:
            valor = self.objetos.get(valor.num)
            profundidad += 1
        return valor

    def r(self, dic, clave, defecto=None):
        if not isinstance(dic, dict):
            return defecto
        valor = self.resolver(dic.get(clave))
        return defecto if valor is None else valor

    def decodificar(self, flujo):
        clave = id(flujo)
        if clave in self._cache:
            return self._cache[clave]
        filtros = self.r(flujo.dic, "Filter")
        parametros = self.r(flujo.dic, "DecodeParms")
        if not isinstance(filtros, list):
            filtros = [] if filtros is None else [filtros]
        if not isinstance(parametros, list):
            parametros = [parametros] * len(filtros)
        datos = flujo.crudo
        for i, filtro in enumerate(filtros):
            filtro = self.resolver(filtro)
            param = self.resolver(parametros[i]) if i < len(parametros) else None
            param = param if isinstance(param, dict) else {}
            if filtro in ("FlateDecode", "Fl"):
                datos = _predictor(_flate(datos), param)
            elif filtro in ("ASCIIHexDecode", "AHx"):
                datos = _ascii_hex(datos)
            elif filtro in ("ASCII85Decode", "A85"):
                datos = _ascii85(datos)
            elif filtro in ("LZWDecode", "LZW"):
                datos = _predictor(_lzw(datos, int(param.get("EarlyChange", 1))), param)
            elif filtro in ("RunLengthDecode", "RL"):
                datos = _run_length(datos)
            else:  # imágenes (DCT, JPX, CCITT, JBIG2): no tienen texto
                datos = b""
                break
        self._cache[clave] = datos
        return datos

    def cifrado(self):
        """True solo si hace falta una contraseña para abrirlo (los cifrados con contraseña vacía ya se descifraron)."""
        return self.con_contrasena

    def raiz(self):
        for trailer in reversed(self.trailers):
            raiz = self.resolver(trailer.get("Root")) if isinstance(trailer, dict) else None
            if isinstance(raiz, dict):
                return raiz
        for valor in self.objetos.values():
            if isinstance(valor, dict) and valor.get("Type") == "Catalog":
                return valor
        return None

    def paginas(self):
        """[(dic de página, recursos heredados)] en orden."""
        raiz = self.raiz()
        salida = []
        vistos = set()

        def recorrer(nodo, recursos, profundidad):
            nodo_id = id(nodo)
            if not isinstance(nodo, dict) or nodo_id in vistos or profundidad > 64:
                return
            vistos.add(nodo_id)
            propios = self.r(nodo, "Resources")
            recursos = propios if isinstance(propios, dict) else recursos
            hijos = self.r(nodo, "Kids")
            if nodo.get("Type") == "Page" or (hijos is None and "Contents" in nodo):
                salida.append((nodo, recursos or {}))
                return
            for hijo in hijos or []:
                recorrer(self.resolver(hijo), recursos, profundidad + 1)

        if raiz is not None:
            recorrer(self.r(raiz, "Pages"), {}, 0)
        if not salida:  # sin árbol válido: todas las páginas sueltas en orden de número de objeto
            for num in sorted(self.objetos):
                valor = self.objetos[num]
                if isinstance(valor, dict) and valor.get("Type") == "Page":
                    salida.append((valor, self.r(valor, "Resources", {})))
        return salida


# --- Fuentes -------------------------------------------------------------------

_GLIFOS = {
    "space": " ", "exclam": "!", "quotedbl": '"', "numbersign": "#", "dollar": "$", "percent": "%", "ampersand": "&",
    "quotesingle": "'", "quoteright": "’", "quoteleft": "‘", "parenleft": "(", "parenright": ")", "asterisk": "*",
    "plus": "+", "comma": ",", "hyphen": "-", "minus": "-", "period": ".", "slash": "/", "colon": ":", "semicolon": ";",
    "less": "<", "equal": "=", "greater": ">", "question": "?", "at": "@", "bracketleft": "[", "backslash": "\\",
    "bracketright": "]", "asciicircum": "^", "underscore": "_", "grave": "`", "braceleft": "{", "bar": "|",
    "braceright": "}", "asciitilde": "~", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "degree": "°", "ordmasculine": "º", "ordfeminine": "ª",
    "endash": "–", "emdash": "—", "quotedblleft": "“", "quotedblright": "”", "quotedblbase": "„", "bullet": "•",
    "periodcentered": "·", "exclamdown": "¡", "questiondown": "¿", "guillemotleft": "«", "guillemotright": "»",
    "section": "§", "paragraph": "¶", "copyright": "©", "registered": "®", "trademark": "™", "Euro": "€",
    "ellipsis": "…", "nbspace": " ", "sfthyphen": "-", "germandbls": "ß", "AE": "Æ", "ae": "æ", "Oslash": "Ø",
    "oslash": "ø", "dotlessi": "ı", "fi": "fi", "fl": "fl", "multiply": "×", "divide": "÷", "plusminus": "±",
    "onehalf": "½", "onequarter": "¼", "threequarters": "¾", "mu": "µ", "cent": "¢", "sterling": "£", "yen": "¥",
}
_DIACRITICOS = {"acute": "́", "grave": "̀", "dieresis": "̈", "circumflex": "̂", "tilde": "̃",
                "cedilla": "̧", "ring": "̊", "caron": "̌"}


def _glifo(nombre):
    if nombre in _GLIFOS:
        return _GLIFOS[nombre]
    if len(nombre) == 1 and nombre.isalpha():
        return nombre
    m = re.fullmatch(r"uni([0-9A-Fa-f]{4})+", nombre)
    if m is not None:
        hexa = nombre[3:]
        return "".join(chr(int(hexa[i:i + 4], 16)) for i in range(0, len(hexa), 4))
    m = re.fullmatch(r"u([0-9A-Fa-f]{4,6})", nombre)
    if m is not None:
        return chr(int(m.group(1), 16))
    for sufijo, marca in _DIACRITICOS.items():
        if nombre.endswith(sufijo) and len(nombre) == len(sufijo) + 1:
            return unicodedata.normalize("NFC", nombre[0] + marca)
    return None


def _decodificar_utf16(datos):
    if len(datos) % 2:
        datos = b"\x00" + datos
    try:
        return datos.decode("utf-16-be")
    except UnicodeDecodeError:
        return ""


def _leer_cmap(datos):
    """(mapa código→texto, largos de código posibles) de un CMap ToUnicode."""
    mapa = {}
    largos = set()
    lector = _Lector(datos)
    pila = []
    while True:
        t = lector.token()
        if t is None:
            break
        if t == "begincodespacerange":
            while True:
                a = lector.token()
                if a is None or a == "endcodespacerange":
                    break
                lector.token()
                if isinstance(a, bytes):
                    largos.add(len(a))
        elif t == "beginbfchar":
            while True:
                a = lector.token()
                if a is None or a == "endbfchar":
                    break
                b = lector.token()
                if isinstance(a, bytes) and isinstance(b, bytes):
                    mapa[a] = _decodificar_utf16(b)
                    largos.add(len(a))
        elif t == "beginbfrange":
            while True:
                a = lector.token()
                if a is None or a == "endbfrange":
                    break
                b = lector.token()
                destino = lector.objeto()
                if not isinstance(a, bytes) or not isinstance(b, bytes):
                    continue
                largos.add(len(a))
                inicio, fin = int.from_bytes(a, "big"), int.from_bytes(b, "big")
                if fin - inicio > 65535:
                    continue
                for i, codigo in enumerate(range(inicio, fin + 1)):
                    clave = codigo.to_bytes(len(a), "big")
                    if isinstance(destino, list):
                        if i < len(destino) and isinstance(destino[i], bytes):
                            mapa[clave] = _decodificar_utf16(destino[i])
                    elif isinstance(destino, bytes) and destino:
                        base = int.from_bytes(destino, "big") + i
                        mapa[clave] = _decodificar_utf16(base.to_bytes(len(destino), "big"))
        else:
            pila.append(t)
    return mapa, largos


class _Fuente:
    def __init__(self, doc, dic):
        dic = dic if isinstance(dic, dict) else {}
        self.subtipo = doc.r(dic, "Subtype")
        self.compuesta = self.subtipo == "Type0"
        self.anchos = {}
        self.ancho_defecto = 1000 if self.compuesta else 500
        self.escala = 1.0
        self.unicode, largos = {}, set()
        tounicode = doc.r(dic, "ToUnicode")
        if isinstance(tounicode, Flujo):
            self.unicode, largos = _leer_cmap(doc.decodificar(tounicode))
        self.largos = sorted(largos) or ([2] if self.compuesta else [1])
        if self.compuesta:
            descendientes = doc.r(dic, "DescendantFonts") or []
            cid = doc.resolver(descendientes[0]) if descendientes else {}
            self.ancho_defecto = doc.r(cid, "DW", 1000)
            self._anchos_cid(doc, doc.r(cid, "W") or [])
            self.codificacion = {}
        else:
            primero = doc.r(dic, "FirstChar", 0)
            anchos = doc.r(dic, "Widths") or []
            for i, w in enumerate(anchos):
                w = doc.resolver(w)
                if isinstance(w, (int, float)) and not isinstance(w, bool):
                    self.anchos[int(primero) + i] = w
            if self.subtipo == "Type3":
                matriz = doc.r(dic, "FontMatrix") or [0.001]
                try:
                    self.escala = float(matriz[0]) * 1000
                except (TypeError, ValueError, IndexError):
                    self.escala = 1.0
            descriptor = doc.r(dic, "FontDescriptor")
            faltante = doc.r(descriptor, "MissingWidth", 0) if isinstance(descriptor, dict) else 0
            if faltante:
                self.ancho_defecto = faltante
            elif self.anchos:
                validos = [w for w in self.anchos.values() if w]
                self.ancho_defecto = sum(validos) / len(validos) if validos else 500
            self.codificacion = self._codificacion(doc, doc.r(dic, "Encoding"))

    def _anchos_cid(self, doc, w):
        i = 0
        while i < len(w):
            inicio = doc.resolver(w[i])
            siguiente = doc.resolver(w[i + 1]) if i + 1 < len(w) else None
            if isinstance(siguiente, list):
                for j, ancho in enumerate(siguiente):
                    ancho = doc.resolver(ancho)
                    if isinstance(ancho, (int, float)):
                        self.anchos[int(inicio) + j] = ancho
                i += 2
            else:
                fin = siguiente
                ancho = doc.resolver(w[i + 2]) if i + 2 < len(w) else None
                if isinstance(inicio, int) and isinstance(fin, int) and isinstance(ancho, (int, float)) and fin - inicio < 65536:
                    for c in range(inicio, fin + 1):
                        self.anchos[c] = ancho
                i += 3

    def _codificacion(self, doc, codificacion):
        base = "cp1252"
        diferencias = []
        if isinstance(codificacion, str):
            base = "mac_roman" if codificacion == "MacRomanEncoding" else "cp1252"
        elif isinstance(codificacion, dict):
            nombre = doc.r(codificacion, "BaseEncoding")
            base = "mac_roman" if nombre == "MacRomanEncoding" else "cp1252"
            diferencias = doc.r(codificacion, "Differences") or []
        tabla = {}
        for c in range(256):
            try:
                tabla[c] = bytes([c]).decode(base)
            except UnicodeDecodeError:
                tabla[c] = bytes([c]).decode("latin-1")
        codigo = 0
        for item in diferencias:
            item = doc.resolver(item)
            if isinstance(item, int) and not isinstance(item, bool):
                codigo = item
            elif isinstance(item, str):
                texto = _glifo(item)
                if texto is not None and 0 <= codigo < 256:
                    tabla[codigo] = texto
                codigo += 1
        return tabla

    def codigos(self, datos):
        """[(código int, bytes)] del texto mostrado."""
        salida = []
        i = 0
        largos = self.largos
        while i < len(datos):
            elegido = None
            if len(largos) > 1 and self.unicode:
                for n in largos:
                    if datos[i:i + n] in self.unicode:
                        elegido = n
                        break
            n = elegido or largos[0]
            trozo = datos[i:i + n]
            salida.append((int.from_bytes(trozo, "big"), trozo))
            i += n
        return salida

    def texto(self, codigo, crudo):
        if crudo in self.unicode:
            return self.unicode[crudo]
        if self.compuesta:
            return ""
        return self.codificacion.get(codigo, "")

    def ancho(self, codigo):
        return self.anchos.get(codigo, self.ancho_defecto) * self.escala / 1000.0


# --- Contenido de páginas ------------------------------------------------------

def _multiplicar(a, b):
    return (
        a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
    )


_IDENTIDAD = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class _Fragmento:
    __slots__ = ("x0", "x1", "y", "alto", "texto")

    def __init__(self, x0, x1, y, alto, texto):
        self.x0, self.x1, self.y, self.alto, self.texto = x0, x1, y, alto, texto


def _numero(valor, defecto=0.0):
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    return defecto


def _matriz(valores):
    if len(valores) != 6 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores):
        return None
    return tuple(float(v) for v in valores)


class _Interprete:
    def __init__(self, doc):
        self.doc = doc
        self.fragmentos = []
        self._fuentes = {}

    def fuente(self, dic):
        clave = id(dic)
        if clave not in self._fuentes:
            self._fuentes[clave] = _Fuente(self.doc, dic)
        return self._fuentes[clave]

    def ejecutar(self, datos, recursos, ctm, profundidad=0):
        if profundidad > 12:
            return
        doc = self.doc
        fuentes = doc.r(recursos, "Font", {})
        xobjetos = doc.r(recursos, "XObject", {})
        pila = []
        estado = {"ctm": ctm, "Tc": 0.0, "Tw": 0.0, "Tz": 1.0, "TL": 0.0, "Ts": 0.0, "fuente": None, "tam": 0.0}
        tm = tlm = _IDENTIDAD
        operandos = []
        lector = _Lector(datos)
        while True:
            try:
                t = lector.token()
            except (IndexError, ValueError):
                break
            if t is None:
                break
            if not isinstance(t, Operador) or t in ("<<", "["):
                try:
                    operandos.append(lector.objeto(t) if isinstance(t, Operador) else t)
                except (IndexError, ValueError):
                    break
                continue
            op = str(t)
            if op == "BI":
                fin = re.search(rb"\sEI(?=[\s]|$)", datos[lector.pos:])
                lector.pos = lector.pos + fin.end() if fin is not None else len(datos)
            elif op == "q":
                pila.append(dict(estado))
            elif op == "Q":
                if pila:
                    estado = pila.pop()
            elif op == "cm":
                m = _matriz(operandos[-6:])
                if m is not None:
                    estado["ctm"] = _multiplicar(m, estado["ctm"])
            elif op == "BT":
                tm = tlm = _IDENTIDAD
            elif op == "Tf" and len(operandos) >= 2:
                nombre = operandos[-2]
                estado["fuente"] = self.fuente(doc.r(fuentes, nombre)) if isinstance(nombre, str) else None
                estado["tam"] = _numero(operandos[-1])
            elif op in ("Tc", "Tw", "TL", "Ts") and operandos:
                estado[op] = _numero(operandos[-1])
            elif op == "Tz" and operandos:
                estado["Tz"] = _numero(operandos[-1], 100.0) / 100.0
            elif op in ("Td", "TD") and len(operandos) >= 2:
                tx, ty = _numero(operandos[-2]), _numero(operandos[-1])
                if op == "TD":
                    estado["TL"] = -ty
                tlm = _multiplicar((1.0, 0.0, 0.0, 1.0, tx, ty), tlm)
                tm = tlm
            elif op == "Tm":
                m = _matriz(operandos[-6:])
                if m is not None:
                    tm = tlm = m
            elif op == "T*":
                tlm = _multiplicar((1.0, 0.0, 0.0, 1.0, 0.0, -estado["TL"]), tlm)
                tm = tlm
            elif op in ("Tj", "'", '"', "TJ"):
                if op in ("'", '"'):
                    if op == '"' and len(operandos) >= 3:
                        estado["Tw"], estado["Tc"] = _numero(operandos[-3]), _numero(operandos[-2])
                    tlm = _multiplicar((1.0, 0.0, 0.0, 1.0, 0.0, -estado["TL"]), tlm)
                    tm = tlm
                if operandos:
                    elementos = operandos[-1] if op == "TJ" and isinstance(operandos[-1], list) else [operandos[-1]]
                    tm = self._mostrar(elementos, estado, tm)
            elif op == "Do" and operandos:
                xobjeto = doc.r(xobjetos, operandos[-1]) if isinstance(operandos[-1], str) else None
                if isinstance(xobjeto, Flujo) and xobjeto.dic.get("Subtype") == "Form":
                    matriz = _matriz([doc.resolver(v) for v in (doc.r(xobjeto.dic, "Matrix") or [])]) or _IDENTIDAD
                    propios = doc.r(xobjeto.dic, "Resources")
                    self.ejecutar(doc.decodificar(xobjeto), propios if isinstance(propios, dict) else recursos,
                                  _multiplicar(matriz, estado["ctm"]), profundidad + 1)
            operandos = []

    def _mostrar(self, elementos, estado, tm):
        fuente, tam = estado["fuente"], estado["tam"]
        if fuente is None:
            return tm
        th = estado["Tz"]
        for elemento in elementos:
            if isinstance(elemento, (int, float)) and not isinstance(elemento, bool):
                tm = _multiplicar((1.0, 0.0, 0.0, 1.0, -elemento / 1000.0 * tam * th, 0.0), tm)
                continue
            if not isinstance(elemento, bytes):
                continue
            trm = _multiplicar(_multiplicar((tam * th, 0.0, 0.0, tam, 0.0, estado["Ts"]), tm), estado["ctm"])
            texto = []
            avance = 0.0
            for codigo, crudo in fuente.codigos(elemento):
                texto.append(fuente.texto(codigo, crudo))
                espacio = estado["Tw"] if len(crudo) == 1 and codigo == 32 else 0.0
                avance += (fuente.ancho(codigo) * tam + estado["Tc"] + espacio) * th
            fin = _multiplicar((1.0, 0.0, 0.0, 1.0, avance, 0.0), tm)
            trm_fin = _multiplicar(_multiplicar((tam * th, 0.0, 0.0, tam, 0.0, estado["Ts"]), fin), estado["ctm"])
            alto = math.hypot(trm[2], trm[3]) or abs(tam) or 1.0
            cadena = "".join(texto)
            if cadena.strip():
                x0, x1 = trm[4], trm_fin[4]
                if x1 < x0:
                    x0, x1 = x1, x0
                self.fragmentos.append(_Fragmento(x0, x1, trm[5], alto, cadena))
            tm = fin
        return tm


def _contenido_pagina(doc, pagina):
    contenido = doc.r(pagina, "Contents")
    partes = contenido if isinstance(contenido, list) else [contenido]
    datos = []
    for parte in partes:
        parte = doc.resolver(parte)
        if isinstance(parte, Flujo):
            datos.append(doc.decodificar(parte))
    return b"\n".join(datos)


def _armar_lineas(fragmentos):
    """Agrupa fragmentos por altura y los ubica en columnas de caracteres (como pdftotext -layout)."""
    if not fragmentos:
        return []
    anchos = sorted((f.x1 - f.x0) / len(f.texto) for f in fragmentos if len(f.texto) > 0 and f.x1 > f.x0)
    ancho_letra = anchos[len(anchos) // 2] if anchos else 5.0
    ancho_letra = max(ancho_letra, 0.5)
    altos = sorted(f.alto for f in fragmentos)
    alto_tipico = altos[len(altos) // 2]

    # Quita duplicados exactos (negrita simulada dibujando dos veces el mismo texto).
    vistos = set()
    unicos = []
    for f in fragmentos:
        clave = (f.texto, round(f.x0), round(f.y))
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(f)

    unicos.sort(key=lambda f: (-f.y, f.x0))
    lineas = []
    for f in unicos:
        if lineas and abs(lineas[-1]["y"] - f.y) <= 0.4 * min(lineas[-1]["alto"], f.alto):
            lineas[-1]["fragmentos"].append(f)
        else:
            lineas.append({"y": f.y, "alto": f.alto, "fragmentos": [f]})

    minimo = min(f.x0 for f in unicos)
    salida = []
    anterior_y = None
    for linea in lineas:
        if anterior_y is not None and anterior_y - linea["y"] > 1.9 * alto_tipico:
            salida.append("")
        anterior_y = linea["y"]
        texto = ""
        fin_anterior = None
        for f in sorted(linea["fragmentos"], key=lambda f: f.x0):
            columna = int(round((f.x0 - minimo) / ancho_letra))
            separado = fin_anterior is None or f.x0 - fin_anterior > 0.1 * f.alto
            if separado and columna > len(texto):
                texto += " " * (columna - len(texto))
            elif separado and texto and not texto.endswith(" "):
                texto += " "
            texto += f.texto
            fin_anterior = f.x1
        salida.append(texto.rstrip())
    return salida


def paginas(datos):
    """Lista con el texto de cada página del PDF (bytes)."""
    if not isinstance(datos, (bytes, bytearray)):
        raise PdfError("El archivo no es un PDF.")
    doc = _Documento(bytes(datos))
    if doc.cifrado():
        raise PdfError("El PDF pide una contraseña para abrirlo; no se puede leer su texto. Abrilo, guardalo como PDF "
                       "nuevo (Imprimir → Guardar como PDF) y subí ese.")
    resultado = []
    for pagina, recursos in doc.paginas():
        interprete = _Interprete(doc)
        interprete.ejecutar(_contenido_pagina(doc, pagina), recursos, _IDENTIDAD)
        resultado.append("\n".join(_armar_lineas(interprete.fragmentos)))
    if not resultado:
        raise PdfError("No se encontraron páginas en el PDF.")
    if not any(p.strip() for p in resultado):
        raise PdfError("El PDF no tiene texto (parece escaneado). Usá el PDF digital de la OC o pegá su texto.")
    return resultado


def _texto_pdf(valor):
    """Cadena de texto de PDF (bytes UTF-16 con BOM o PDFDocEncoding ≈ cp1252) → str."""
    if isinstance(valor, str):
        return valor
    if not isinstance(valor, bytes):
        return ""
    if valor.startswith(b"\xfe\xff"):
        return _decodificar_utf16(valor[2:])
    try:
        return valor.decode("cp1252")
    except UnicodeDecodeError:
        return valor.decode("latin-1")


def campos_formulario(datos):
    """[(nombre, valor)] de los campos de texto del PDF (los de GDE llevan el número del documento y las páginas)."""
    doc = _Documento(bytes(datos))
    salida = []
    for num in sorted(doc.objetos):
        valor = doc.objetos[num]
        if not isinstance(valor, dict) or "V" not in valor:
            continue
        tipo = doc.r(valor, "FT") or doc.r(doc.r(valor, "Parent"), "FT")
        contenido = doc.r(valor, "V")
        if tipo != "Tx" or not isinstance(contenido, (bytes, str)):
            continue
        texto = " ".join(_texto_pdf(contenido).split())
        if texto:
            salida.append((_texto_pdf(doc.r(valor, "T")) or "campo", texto))
    return salida


def texto_de_pdf(datos):
    """Texto de todo el PDF; las páginas van separadas por un salto de página (\\f).

    Si el PDF tiene campos de formulario con texto (GDE pone ahí el número del documento), van al final, como una
    página más con una línea «nombre: valor» por campo.
    """
    texto = "\f".join(paginas(datos))
    campos = campos_formulario(datos)
    if campos:
        texto += "\f" + "\n".join("%s: %s" % (nombre, valor) for nombre, valor in campos)
    return texto
