"""Reglas de negocio sobre la base (OC, renglones; expedientes desde el paso 9).

Toda escritura va dentro de `db.transaccion`, con control de versión y evento de auditoría.
"""
import json
from decimal import Decimal, InvalidOperation

from gestor import db, util

EFECTORES = ("HBI", "CASPH")
TIPOS_OC = ("SERVICIO", "BIEN", "PROVISION")
ARTICULOS = ("al", "a la", "a los", "a las")

CAMPOS_EDITABLES_OC = (
    "objeto", "objeto_articulo", "concepto_corto", "dia_inicio_periodo", "comodato", "centralizada",
    "tipo", "ca", "expediente_contratacion", "gde_pdf_oc", "leyenda_cv", "extras_cv", "doc_requerida_central",
    "vig_desde", "vig_hasta", "prorroga", "excluida", "motivo_exclusion",
)
CAMPOS_EDITABLES_RENGLON = (
    "desglose_cantidad", "desglose_unidad", "desglose_precio_centavos", "consumo_previo",
    "es_correctivo", "revisar_desglose", "revisar_importe",
)
# Campos que se cargan al dar de alta una OC manual (además de los editables).
CAMPOS_ALTA_OC = ("numero", "efector", "sap", "razon_social", "fecha_oc", "renglones")
CAMPOS_ALTA_RENGLON = (
    "pos", "codigo", "descripcion", "cantidad", "unidad", "precio_centavos", "importe_centavos", "partida",
) + CAMPOS_EDITABLES_RENGLON

_JSON_OC = ("campos_manuales", "extras_cv", "doc_requerida_central")
_JSON_RENGLON = ("campos_manuales", "crudo")


class ErrorValidacion(Exception):
    """Dato inválido (HTTP 400). El mensaje se muestra tal cual a la usuaria."""


class ErrorNegocio(Exception):
    """Regla de negocio que impide la operación (HTTP 422)."""


class NoEncontrado(Exception):
    """El registro pedido no existe (HTTP 404)."""


# --- Validación de valores -------------------------------------------------

def _texto(valor, nombre):
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ErrorValidacion("El campo %s debe ser texto." % nombre)
    return valor.strip()


def _bandera(valor, nombre):
    if isinstance(valor, (bool, int)) and valor in (0, 1):
        return 1 if valor else 0
    raise ErrorValidacion("El campo %s debe ser 0 o 1." % nombre)


def _entero(valor, nombre, minimo=None):
    if isinstance(valor, bool):
        raise ErrorValidacion("El campo %s debe ser un número entero." % nombre)
    try:
        numero = int(str(valor).strip()) if not isinstance(valor, int) else valor
    except ValueError:
        raise ErrorValidacion("El campo %s debe ser un número entero." % nombre) from None
    if minimo is not None and numero < minimo:
        raise ErrorValidacion("El campo %s no puede ser menor que %d." % (nombre, minimo))
    return numero


def _decimal_texto(valor, nombre, permitir_vacio=False):
    """Cantidad → texto de Decimal (sin float). Acepta "3.600,5", "3600.5", 3600."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if permitir_vacio:
            return None
        raise ErrorValidacion("Falta el campo %s." % nombre)
    if isinstance(valor, float):
        valor = repr(valor)
    try:
        numero = util.a_decimal(valor, decimales=None)
    except (TypeError, ValueError, InvalidOperation):
        raise ErrorValidacion("El campo %s debe ser un número." % nombre) from None
    if numero < 0:
        raise ErrorValidacion("El campo %s no puede ser negativo." % nombre)
    texto = format(numero, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


def _fecha(valor, nombre, permitir_vacio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if permitir_vacio:
            return None
        raise ErrorValidacion("Falta la fecha %s." % nombre)
    try:
        return util.iso(util.fecha_desde_texto(valor))
    except (ValueError, TypeError):
        raise ErrorValidacion("La fecha %s no es válida (usá dd/mm/aaaa)." % nombre) from None


def _gde(valor, nombre):
    texto = _texto(valor, nombre)
    if not texto:
        return ""
    normalizado = util.normalizar_gde(texto)
    if not util.validar_gde(normalizado):
        raise ErrorValidacion("El número GDE %s no es válido: %s" % (nombre, texto))
    return normalizado


def _validar_campo_oc(campo, valor):
    if campo == "dia_inicio_periodo":
        try:
            dia = _entero(valor, "día de inicio del período")
        except ErrorValidacion:
            raise ErrorValidacion("El día de inicio del período debe estar entre 1 y 28.") from None
        if not 1 <= dia <= 28:
            raise ErrorValidacion("El día de inicio del período debe estar entre 1 y 28.")
        return dia
    if campo == "objeto_articulo":
        if valor not in ARTICULOS:
            raise ErrorValidacion("El artículo del objeto debe ser «al», «a la», «a los» o «a las».")
        return valor
    if campo == "tipo":
        if valor not in TIPOS_OC:
            raise ErrorValidacion("El tipo de OC debe ser SERVICIO, BIEN o PROVISION.")
        return valor
    if campo in ("comodato", "centralizada", "excluida"):
        return _bandera(valor, campo)
    if campo in ("expediente_contratacion", "gde_pdf_oc"):
        return _gde(valor, "de expediente" if campo == "expediente_contratacion" else "del PDF de la OC")
    if campo in ("vig_desde", "vig_hasta", "prorroga"):
        return _fecha(valor, {"vig_desde": "de inicio de vigencia", "vig_hasta": "de fin de vigencia",
                              "prorroga": "de prórroga"}[campo])
    if campo == "extras_cv":
        if not isinstance(valor, dict):
            raise ErrorValidacion("Los datos extra del CV deben ser pares nombre → valor.")
        return valor
    if campo == "doc_requerida_central":
        if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
            raise ErrorValidacion("La documentación requerida debe ser una lista de textos.")
        return [v.strip() for v in valor if v.strip()]
    return _texto(valor, campo)


def _validar_campo_renglon(campo, valor):
    if campo == "desglose_cantidad":
        texto = _decimal_texto(valor, "cantidad del desglose", permitir_vacio=True)
        if texto is not None and Decimal(texto) == 0:
            raise ErrorValidacion("La cantidad del desglose debe ser mayor que 0.")
        return texto
    if campo == "desglose_unidad":
        texto = _texto(valor, "unidad del desglose").upper()
        return texto or None
    if campo == "desglose_precio_centavos":
        if valor is None or valor == "":
            return None
        return _entero(valor, "precio del desglose", minimo=0)
    if campo == "consumo_previo":
        return _decimal_texto(valor if valor not in (None, "") else "0", "consumo previo")
    if campo in ("es_correctivo", "revisar_desglose", "revisar_importe"):
        return _bandera(valor, campo)
    raise ErrorValidacion("El campo %s no se puede editar." % campo)


def _validar_cambios(cambios, editables, validar):
    if not isinstance(cambios, dict) or not cambios:
        raise ErrorValidacion("No hay cambios para guardar.")
    desconocidos = [c for c in cambios if c not in editables]
    if desconocidos:
        raise ErrorValidacion("No se puede editar: %s." % ", ".join(sorted(desconocidos)))
    return {campo: validar(campo, valor) for campo, valor in cambios.items()}


def _version(version):
    if isinstance(version, bool) or not isinstance(version, int):
        raise ErrorValidacion("Falta la versión del registro.")
    return version


# --- Lectura ---------------------------------------------------------------

def _decodificar(fila, columnas_json):
    if fila is None:
        return None
    for columna in columnas_json:
        if columna in fila and isinstance(fila[columna], str):
            try:
                fila[columna] = json.loads(fila[columna])
            except ValueError:
                pass
    return fila


def _leer_oc(con, numero):
    oc = db.leer_fila(con, "oc", {"numero": str(numero)})
    if oc is None:
        raise NoEncontrado("No existe la OC %s." % numero)
    return oc


def listar_oc(con, efector=None, texto="", incluir_excluidas=False):
    """OC con su proveedor, filtradas por efector, texto (sin tildes ni mayúsculas) y exclusión."""
    sql = (
        "SELECT oc.numero, oc.efector, oc.sap, p.razon_social, oc.objeto, oc.tipo, oc.comodato, oc.centralizada, "
        "oc.vig_desde, oc.vig_hasta, oc.excluida, oc.origen, oc.cerrada_sap, oc.version, "
        "(SELECT COUNT(*) FROM renglon r WHERE r.oc = oc.numero) AS renglones, "
        "(SELECT COALESCE(SUM(r.importe_centavos), 0) FROM renglon r WHERE r.oc = oc.numero) AS importe_centavos "
        "FROM oc JOIN proveedor p ON p.sap = oc.sap"
    )
    condiciones, parametros = [], []
    if efector in EFECTORES:
        condiciones.append("oc.efector = ?")
        parametros.append(efector)
    if not incluir_excluidas:
        condiciones.append("oc.excluida = 0")
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY oc.numero DESC"
    filas = [dict(fila) for fila in con.execute(sql, parametros)]
    buscado = util.normalizar_texto(texto or "")
    if buscado:
        filas = [
            f for f in filas
            if buscado in util.normalizar_texto(" ".join(str(f[c] or "") for c in ("numero", "sap", "razon_social", "objeto")))
        ]
    return filas


def ficha_oc(con, numero):
    """OC + proveedor + renglones + expedientes."""
    oc = _decodificar(_leer_oc(con, numero), _JSON_OC)
    proveedor = db.leer_fila(con, "proveedor", {"sap": oc["sap"]})
    renglones = [
        _decodificar(dict(fila), _JSON_RENGLON)
        for fila in con.execute("SELECT * FROM renglon WHERE oc = ? ORDER BY pos", (oc["numero"],))
    ]
    expedientes = [
        dict(fila)
        for fila in con.execute(
            "SELECT id, tipo, periodo, estado, factura, version FROM expediente WHERE oc = ? ORDER BY periodo, id",
            (oc["numero"],),
        )
    ]
    return {"oc": oc, "proveedor": proveedor, "renglones": renglones, "expedientes": expedientes}


# --- Escritura -------------------------------------------------------------

def _con_manuales(actual, campos):
    manuales = json.loads(actual.get("campos_manuales") or "[]")
    for campo in campos:
        if campo not in manuales:
            manuales.append(campo)
    return sorted(manuales)


def _validar_vigencia(desde, hasta):
    if desde and hasta and hasta < desde:
        raise ErrorValidacion("El fin de la vigencia no puede ser anterior al inicio.")


def actualizar_oc(con, numero, version, cambios):
    """Edita campos manuales de la OC (quedan marcados en campos_manuales) y devuelve la ficha."""
    version = _version(version)
    validos = _validar_cambios(cambios, CAMPOS_EDITABLES_OC, _validar_campo_oc)
    with db.transaccion(con):
        actual = _leer_oc(con, numero)
        _validar_vigencia(validos.get("vig_desde", actual["vig_desde"]), validos.get("vig_hasta", actual["vig_hasta"]))
        validos["campos_manuales"] = _con_manuales(actual, [c for c in validos if c != "campos_manuales"])
        db.actualizar_con_version(con, "oc", {"numero": actual["numero"]}, version, validos)
    return ficha_oc(con, numero)


def _renglon_desde_datos(numero, datos, pos_por_defecto):
    if not isinstance(datos, dict):
        raise ErrorValidacion("Cada renglón debe ser un objeto con sus datos.")
    desconocidos = [c for c in datos if c not in CAMPOS_ALTA_RENGLON]
    if desconocidos:
        raise ErrorValidacion("Campos desconocidos en el renglón: %s." % ", ".join(sorted(desconocidos)))
    pos = _entero(datos.get("pos", pos_por_defecto), "posición", minimo=1)
    descripcion = _texto(datos.get("descripcion"), "descripción")
    if not descripcion:
        raise ErrorValidacion("Falta la descripción del renglón %d." % pos)
    cantidad = _decimal_texto(datos.get("cantidad", "1"), "cantidad")
    precio = _entero(datos.get("precio_centavos", 0), "precio", minimo=0)
    if "importe_centavos" in datos and datos["importe_centavos"] not in (None, ""):
        importe = _entero(datos["importe_centavos"], "importe", minimo=0)
    else:
        importe = int((Decimal(cantidad) * precio).to_integral_value())
    fila = {
        "oc": numero,
        "pos": pos,
        "codigo": _texto(datos.get("codigo"), "código"),
        "descripcion": descripcion,
        "cantidad": cantidad,
        "unidad": _texto(datos.get("unidad"), "unidad").upper(),
        "precio_centavos": precio,
        "importe_centavos": importe,
        "partida": _texto(datos.get("partida"), "partida"),
        "sap_por_entregar": cantidad,
    }
    for campo in CAMPOS_EDITABLES_RENGLON:
        if campo in datos:
            fila[campo] = _validar_campo_renglon(campo, datos[campo])
    if fila.get("desglose_cantidad") is not None:
        fila["sap_por_entregar"] = fila["desglose_cantidad"]
    fila["campos_manuales"] = sorted(c for c in CAMPOS_EDITABLES_RENGLON if c in datos)
    return fila


def crear_oc_manual(con, datos):
    """Alta de una OC cargada a mano (origen MANUAL) con sus renglones; todos sus campos quedan como manuales."""
    if not isinstance(datos, dict):
        raise ErrorValidacion("Faltan los datos de la OC.")
    desconocidos = [c for c in datos if c not in CAMPOS_ALTA_OC + CAMPOS_EDITABLES_OC]
    if desconocidos:
        raise ErrorValidacion("Campos desconocidos: %s." % ", ".join(sorted(desconocidos)))
    numero = util.sap_sin_ceros(_texto(datos.get("numero"), "número de OC"))
    if not numero.isdigit():
        raise ErrorValidacion("El número de OC debe tener solo dígitos.")
    efector = datos.get("efector")
    if efector not in EFECTORES:
        raise ErrorValidacion("Elegí el efector (HBI o CASPH).")
    sap = util.sap_sin_ceros(_texto(datos.get("sap"), "SAP"))
    if not sap.isdigit():
        raise ErrorValidacion("El número SAP del proveedor debe tener solo dígitos.")
    razon_social = _texto(datos.get("razon_social"), "razón social")

    oc = {"numero": numero, "efector": efector, "sap": sap, "origen": "MANUAL",
          "fecha_oc": _fecha(datos.get("fecha_oc"), "de la OC")}
    for campo in CAMPOS_EDITABLES_OC:
        if campo in datos:
            oc[campo] = _validar_campo_oc(campo, datos[campo])
    _validar_vigencia(oc.get("vig_desde"), oc.get("vig_hasta"))
    oc["campos_manuales"] = sorted(c for c in CAMPOS_EDITABLES_OC + ("fecha_oc",) if c in datos)

    renglones_datos = datos.get("renglones") or []
    if not isinstance(renglones_datos, list):
        raise ErrorValidacion("Los renglones deben ser una lista.")
    renglones = [_renglon_desde_datos(numero, r, i + 1) for i, r in enumerate(renglones_datos)]
    posiciones = [r["pos"] for r in renglones]
    if len(set(posiciones)) != len(posiciones):
        raise ErrorValidacion("Hay posiciones repetidas en los renglones.")

    with db.transaccion(con):
        if db.leer_fila(con, "oc", {"numero": numero}) is not None:
            raise ErrorNegocio("La OC %s ya existe." % numero)
        if db.leer_fila(con, "proveedor", {"sap": sap}) is None:
            if not razon_social:
                raise ErrorValidacion("Falta la razón social del proveedor %s." % sap)
            db.insertar(con, "proveedor", {"sap": sap, "razon_social": razon_social})
        db.insertar(con, "oc", oc)
        for renglon in renglones:
            db.insertar(con, "renglon", renglon)
    return ficha_oc(con, numero)


def agregar_renglon(con, numero, datos):
    """Agrega un renglón a una OC cargada a mano."""
    with db.transaccion(con):
        oc = _leer_oc(con, numero)
        if oc["origen"] != "MANUAL":
            raise ErrorNegocio("Solo se pueden agregar renglones a una OC cargada a mano.")
        maximo = con.execute("SELECT COALESCE(MAX(pos), 0) FROM renglon WHERE oc = ?", (oc["numero"],)).fetchone()[0]
        renglon = _renglon_desde_datos(oc["numero"], datos, maximo + 1)
        if db.leer_fila(con, "renglon", {"oc": oc["numero"], "pos": renglon["pos"]}) is not None:
            raise ErrorNegocio("La posición %d ya existe en la OC %s." % (renglon["pos"], oc["numero"]))
        db.insertar(con, "renglon", renglon)
    return ficha_oc(con, numero)


def actualizar_renglon(con, numero, pos, version, cambios):
    """Edita desglose, consumo previo y banderas de un renglón (quedan como campos manuales)."""
    version = _version(version)
    validos = _validar_cambios(cambios, CAMPOS_EDITABLES_RENGLON, _validar_campo_renglon)
    pos = _entero(pos, "posición", minimo=1)
    with db.transaccion(con):
        oc = _leer_oc(con, numero)
        actual = db.leer_fila(con, "renglon", {"oc": oc["numero"], "pos": pos})
        if actual is None:
            raise NoEncontrado("No existe la posición %d de la OC %s." % (pos, oc["numero"]))
        desglose = [validos.get(c, actual[c]) for c in ("desglose_cantidad", "desglose_unidad", "desglose_precio_centavos")]
        if any(v is not None for v in desglose) and not all(v is not None for v in desglose):
            raise ErrorValidacion("El desglose necesita cantidad, unidad y precio (o los tres vacíos).")
        validos["campos_manuales"] = _con_manuales(actual, [c for c in validos if c != "campos_manuales"])
        db.actualizar_con_version(con, "renglon", {"oc": oc["numero"], "pos": pos}, version, validos)
    return ficha_oc(con, numero)
