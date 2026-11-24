"""Reglas de negocio sobre la base (OC, renglones; expedientes desde el paso 9).

Toda escritura va dentro de `db.transaccion`, con control de versión y evento de auditoría.
"""
import copy
import getpass
import json
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from gestor import controles, db, textos, util

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
        "oc.vig_desde, oc.vig_hasta, oc.excluida, oc.origen, oc.cerrada_sap, oc.version, oc.concepto_corto, "
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
    # Renglones de otro centro (recepciones que a veces no llevan factura del efector).
    parametros_base = db.leer_parametros(con)
    otros = {}
    for r in con.execute("SELECT r.oc, r.crudo, oc.efector FROM renglon r JOIN oc ON oc.numero = r.oc"):
        centro = centro_de_renglon({"crudo": r["crudo"]})
        if centro and centro not in CENTROS_CENTRALES and centro not in centros_propios(parametros_base, r["efector"]):
            otros[r["oc"]] = otros.get(r["oc"], 0) + 1
    con_pdf = ocs_con_pdf(con)
    for f in filas:
        f["renglones_otro_centro"] = otros.get(f["numero"], 0)
        f["pdf_cargado"] = f["numero"] in con_pdf
    buscado = util.normalizar_texto(texto or "")
    if buscado:
        filas = [
            f for f in filas
            if buscado in util.normalizar_texto(" ".join(str(f[c] or "") for c in ("numero", "sap", "razon_social", "objeto")))
        ]
    return filas


# Centro físico propio de cada efector cuando la tabla config no lo tiene (CASPH no tiene `centros` cargados por defecto).
CENTROS_PROPIOS_POR_DEFECTO = {"HBI": ["1900"], "CASPH": ["1300"]}


def centros_propios(parametros, efector):
    """Centros SAP propios del efector: los de Configuración o, si no hay, los de siempre (1900 HBI, 1300 CASPH)."""
    datos = (parametros.get("efectores") or {}).get(efector) or {}
    valores = [str(c).strip() for c in datos.get("centros") or [] if str(c).strip()]
    return set(valores or CENTROS_PROPIOS_POR_DEFECTO.get(efector, []))


def centro_de_renglon(renglon):
    """Centro SAP del renglón según la fila del z_compras2 que lo trajo ("" si se cargó a mano)."""
    crudo = renglon.get("crudo")
    if isinstance(crudo, str):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            crudo = {}
    for encabezado, valor in (crudo or {}).items():
        if util.clave_encabezado(encabezado) == "centro":
            return str(valor or "").strip()
    return ""


CENTROS_CENTRALES = ("0010",)  # Nivel Central: sus renglones son de una OC centralizada


def marcar_otro_centro(renglones, propios):
    """Agrega a cada renglón `centro`, `central` (1 si es del centro de Nivel Central: centralizada) y `otro_centro`
    (1 si es de otro centro que no es del efector ni de Nivel Central: se recibe y a veces no lleva factura)."""
    for r in renglones:
        r["centro"] = centro_de_renglon(r)
        r["central"] = 1 if r["centro"] in CENTROS_CENTRALES else 0
        r["otro_centro"] = 1 if r["centro"] and not r["central"] and r["centro"] not in propios else 0
    return renglones


def ficha_oc(con, numero):
    """OC + proveedor + renglones (marcados si son de otro centro) + expedientes."""
    oc = _decodificar(_leer_oc(con, numero), _JSON_OC)
    proveedor = db.leer_fila(con, "proveedor", {"sap": oc["sap"]})
    renglones = marcar_otro_centro([
        _decodificar(dict(fila), _JSON_RENGLON)
        for fila in con.execute("SELECT * FROM renglon WHERE oc = ? ORDER BY pos", (oc["numero"],))
    ], centros_propios(db.leer_parametros(con), oc["efector"]))
    expedientes = [
        _resumen_expediente_oc(dict(fila))
        for fila in con.execute(
            "SELECT id, tipo, periodo, estado, factura, version, datos FROM expediente WHERE oc = ? ORDER BY periodo, id",
            (oc["numero"],),
        )
    ]
    return {"oc": oc, "proveedor": proveedor, "renglones": renglones, "expedientes": expedientes,
            "pdf_oc": ultimo_pdf_oc(con, oc["numero"])}


def _resumen_expediente_oc(fila):
    """Fila de «Expedientes de esta OC»: importe de la factura y de dónde sale su consumo."""
    datos = _datos_de(fila)
    factura = datos.get("factura") if isinstance(datos.get("factura"), dict) else {}
    centavos = factura.get("centavos")
    fila.pop("datos", None)
    fila["importe_centavos"] = centavos if isinstance(centavos, int) and not isinstance(centavos, bool) else None
    fila["consumo_remitos"] = bool(_cantidades_de_remitos(datos))
    manual = datos.get("consumo_manual") if isinstance(datos.get("consumo_manual"), dict) else {}
    fila["consumo_manual"] = {str(k): str(v) for k, v in manual.items()}
    return fila


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


# --- PDF de la OC --------------------------------------------------------------
# El PDF digital de la OC (el firmado en GDE) trae bien el objeto, las cantidades y los subrenglones que el z_compras2
# muestra mal (servicios medidos en meses, renglones con subrenglones). Se lee, se compara con la base y la usuaria
# elige qué aplicar; lo aplicado queda como campo manual para que la próxima importación no lo pise.

CAMPOS_OC_PDF = ("objeto", "objeto_articulo", "ca", "expediente_contratacion", "gde_pdf_oc", "vig_desde", "vig_hasta",
                 "dia_inicio_periodo", "centralizada")
# Se resuelven solos con reglas fijas: vienen tildados aunque el dato se haya editado a mano.
CAMPOS_OC_PDF_AUTOMATICOS = ("objeto_articulo", "dia_inicio_periodo", "gde_pdf_oc", "centralizada")
# En los bienes no hay períodos: la vigencia y el día de inicio no se toman del PDF.
CAMPOS_SIN_PERIODO = ("vig_desde", "vig_hasta", "dia_inicio_periodo")
CAMPOS_RENGLON_PDF = ("codigo", "descripcion", "cantidad", "unidad", "precio_centavos", "importe_centavos",
                      "desglose_cantidad", "desglose_unidad", "desglose_precio_centavos")
ETIQUETAS_PDF = {
    "objeto": "Objeto", "objeto_articulo": "Artículo del objeto", "ca": "CA (licitación-año)",
    "expediente_contratacion": "Expediente de contratación", "gde_pdf_oc": "N° GDE del PDF de la OC",
    "vig_desde": "Vigencia desde", "vig_hasta": "Vigencia hasta", "dia_inicio_periodo": "Día de inicio del período",
    "centralizada": "Es centralizada (UOC: Nivel central)",
    "codigo": "Código", "descripcion": "Descripción",
    "cantidad": "Cantidad", "unidad": "Unidad", "precio_centavos": "Precio unitario", "importe_centavos": "Importe",
    "desglose_cantidad": "Desglose: cantidad", "desglose_unidad": "Desglose: unidad",
    "desglose_precio_centavos": "Desglose: precio",
}
FUENTE_PDF = "pdf_oc"


def _iguales(campo, a, b):
    if campo in ("cantidad", "desglose_cantidad"):
        if a in (None, "") or b in (None, ""):
            return a in (None, "") and b in (None, "")
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except InvalidOperation:
            return False
    return (a if a != "" else None) == (b if b != "" else None)


def _propuesta_renglon(leido):
    desglose = leido.get("desglose") or {}
    return {
        "codigo": leido.get("codigo") or "",
        "descripcion": leido.get("descripcion") or "",
        "cantidad": leido.get("cantidad"),
        "unidad": leido.get("unidad") or "",
        "precio_centavos": leido.get("precio_centavos"),
        "importe_centavos": leido.get("importe_centavos"),
        "desglose_cantidad": desglose.get("cantidad"),
        "desglose_unidad": desglose.get("unidad"),
        "desglose_precio_centavos": desglose.get("precio_centavos"),
    }


_PATRON_PDF = '%"fuente": "pdf_oc"%'


def ocs_con_pdf(con):
    """Números de OC que tienen cargado su PDF."""
    numeros = set()
    for fila in con.execute("SELECT clave FROM evento WHERE tabla = 'oc' AND accion = 'IMPORTACION' AND despues LIKE ?",
                            (_PATRON_PDF,)):
        try:
            numeros.add(str(json.loads(fila["clave"]).get("numero")))
        except (ValueError, AttributeError):
            continue
    return numeros


def ultimo_pdf_oc(con, numero):
    """Última carga del PDF de la OC ({fecha, usuario, archivo}) o None."""
    fila = con.execute(
        "SELECT fecha, usuario, despues FROM evento WHERE tabla = 'oc' AND accion = 'IMPORTACION' AND clave = ? "
        "AND despues LIKE ? ORDER BY id DESC LIMIT 1",
        (json.dumps({"numero": str(numero)}, ensure_ascii=False, sort_keys=True), _PATRON_PDF),
    ).fetchone()
    if fila is None:
        return None
    try:
        despues = json.loads(fila["despues"] or "{}")
    except ValueError:
        despues = {}
    if despues.get("fuente") != FUENTE_PDF:
        return None
    return {"fecha": fila["fecha"], "usuario": fila["usuario"], "archivo": despues.get("archivo") or ""}


def comparar_oc_pdf(con, numero, leido):
    """Compara lo leído del PDF (gestor.oc_pdf.leer_oc) con la OC de la base. No escribe nada."""
    ficha = ficha_oc(con, numero)
    oc = ficha["oc"]
    if leido.get("numero") and leido["numero"] != oc["numero"]:
        raise ErrorNegocio("El PDF es de la OC %s, no de la %s." % (leido["numero"], oc["numero"]))
    avisos = list(leido.get("avisos") or [])
    if leido.get("sap") and leido["sap"] != oc["sap"]:
        avisos.append("El proveedor del PDF (SAP %s, %s) no es el de la OC en la base (SAP %s)." % (
            leido["sap"], leido.get("razon_social") or "", oc["sap"]))
    manuales_oc = set(oc.get("campos_manuales") or [])
    campos_oc = []
    for campo in CAMPOS_OC_PDF:
        pdf = leido.get(campo)
        if pdf in (None, "") or (oc["tipo"] == "BIEN" and campo in CAMPOS_SIN_PERIODO):
            continue
        actual = oc.get(campo)
        campos_oc.append({"campo": campo, "etiqueta": ETIQUETAS_PDF[campo], "actual": actual, "pdf": pdf,
                          "distinto": not _iguales(campo, actual, pdf), "manual": campo in manuales_oc,
                          "automatico": campo in CAMPOS_OC_PDF_AUTOMATICOS})

    actuales = {r["pos"]: r for r in ficha["renglones"]}
    renglones = []
    for r in leido.get("renglones") or []:
        actual = actuales.get(r["pos"])
        propuesta = _propuesta_renglon(r)
        diferencias = []
        for campo in CAMPOS_RENGLON_PDF:
            valor_actual = actual.get(campo) if actual is not None else None
            if actual is not None and campo in ("codigo", "descripcion") and valor_actual:
                continue  # el texto del z_compras2 se respeta; solo se completa si falta
            if propuesta[campo] in (None, "") and campo not in ("desglose_cantidad", "desglose_unidad",
                                                               "desglose_precio_centavos"):
                continue
            if actual is None or not _iguales(campo, valor_actual, propuesta[campo]):
                diferencias.append({"campo": campo, "etiqueta": ETIQUETAS_PDF[campo], "actual": valor_actual,
                                    "pdf": propuesta[campo]})
        if actual is not None and actual.get("desglose_cantidad") is not None and propuesta["desglose_cantidad"] is None:
            # El PDF no trae subrenglones: no se borra un desglose cargado (puede ser manual o inferido a propósito).
            diferencias = [d for d in diferencias if not d["campo"].startswith("desglose_")]
        renglones.append({
            "pos": r["pos"], "existe": actual is not None, "version": actual["version"] if actual is not None else None,
            "descripcion": (actual or {}).get("descripcion") or propuesta["descripcion"],
            "propuesta": propuesta, "diferencias": diferencias, "subrenglones": r.get("subrenglones") or [],
            "sol_ped": r.get("sol_ped") or "",
        })
    en_pdf = {r["pos"] for r in leido.get("renglones") or []}
    for pos in sorted(set(actuales) - en_pdf):
        avisos.append("El renglón %d está en la base (z_compras2) pero no en el PDF de la OC." % pos)
    cabecera = {k: v for k, v in leido.items() if k not in ("renglones", "avisos")}
    return {"oc": {"numero": oc["numero"], "version": oc["version"], "origen": oc["origen"]}, "leido": cabecera,
            "campos_oc": campos_oc, "renglones": renglones, "avisos": avisos,
            "ultimo_pdf": ultimo_pdf_oc(con, oc["numero"])}


def crear_oc_desde_pdf(con, datos, archivo="", leido=None):
    """Alta de una OC con los datos del PDF confirmados por la usuaria (ventana «Nueva OC»).

    Es una OC cargada a mano (origen MANUAL) con todos sus datos como manuales —también cantidad, unidad, precio y
    desglose de los renglones—, así la importación del z_compras2 no los pisa; y queda registrada la carga del PDF.
    """
    ficha = crear_oc_manual(con, datos)
    numero = ficha["oc"]["numero"]
    with db.transaccion(con):
        for fila in con.execute("SELECT * FROM renglon WHERE oc = ? ORDER BY pos", (numero,)).fetchall():
            fila = dict(fila)
            presentes = [c for c in CAMPOS_RENGLON_PDF if fila.get(c) not in (None, "")]
            manuales = _con_manuales(fila, presentes)
            if manuales != json.loads(fila.get("campos_manuales") or "[]"):
                db.actualizar_con_version(con, "renglon", {"oc": numero, "pos": fila["pos"]}, fila["version"],
                                          {"campos_manuales": manuales})
        db.registrar_evento(con, "IMPORTACION", "oc", {"numero": numero}, None, {
            "fuente": FUENTE_PDF, "archivo": _texto(archivo, "archivo"), "alta": True,
            "leido": leido if isinstance(leido, dict) else {},
        })
    return ficha_oc(con, numero)


def _validar_campo_renglon_pdf(campo, valor):
    if campo in ("codigo", "descripcion"):
        return _texto(valor, ETIQUETAS_PDF[campo].lower())
    if campo == "unidad":
        return _texto(valor, "unidad").upper()
    if campo == "cantidad":
        return _decimal_texto(valor, "cantidad")
    if campo in ("precio_centavos", "importe_centavos"):
        return _entero(valor, ETIQUETAS_PDF[campo].lower(), minimo=0)
    return _validar_campo_renglon(campo, valor)


def _por_entregar(cantidad, desglose_cantidad, entregado):
    """sap_por_entregar y exceso_sap medidos en la unidad del desglose cuando lo hay (como la importación)."""
    base = Decimal(desglose_cantidad if desglose_cantidad is not None else (cantidad or "0"))
    entregado = Decimal(entregado or "0")
    resto = max(Decimal(0), base - entregado)
    texto = format(resto, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto, 1 if entregado > base else 0


def aplicar_oc_pdf(con, numero, datos):
    """Aplica lo elegido del PDF: campos de la OC y de los renglones (quedan como manuales) y deja constancia.

    `datos`: {"version", "oc": {campo: valor}, "renglones": [{"pos", "version" (None si es nuevo), "cambios"}],
    "archivo", "leido"} — `leido` es la cabecera que devolvió la comparación, para la auditoría.
    """
    if not isinstance(datos, dict):
        raise ErrorValidacion("Faltan los datos a aplicar.")
    version = _version(datos.get("version"))
    cambios_oc = datos.get("oc") or {}
    if not isinstance(cambios_oc, dict):
        raise ErrorValidacion("Los campos de la OC deben ser un objeto.")
    desconocidos = [c for c in cambios_oc if c not in CAMPOS_OC_PDF]
    if desconocidos:
        raise ErrorValidacion("No se puede tomar del PDF: %s." % ", ".join(sorted(desconocidos)))
    validos_oc = {campo: _validar_campo_oc(campo, valor) for campo, valor in cambios_oc.items()}

    renglones = datos.get("renglones") or []
    if not isinstance(renglones, list):
        raise ErrorValidacion("Los renglones deben ser una lista.")
    validos_renglones = []
    for item in renglones:
        if not isinstance(item, dict):
            raise ErrorValidacion("Cada renglón debe ser un objeto con sus datos.")
        pos = _entero(item.get("pos"), "posición", minimo=1)
        cambios = item.get("cambios") or {}
        if not isinstance(cambios, dict):
            raise ErrorValidacion("Los cambios del renglón %d deben ser un objeto." % pos)
        desconocidos = [c for c in cambios if c not in CAMPOS_RENGLON_PDF]
        if desconocidos:
            raise ErrorValidacion("No se puede tomar del PDF en el renglón %d: %s." % (pos, ", ".join(sorted(desconocidos))))
        if not cambios:
            continue
        version_renglon = item.get("version")
        if version_renglon is not None:
            version_renglon = _version(version_renglon)
        validos_renglones.append((pos, version_renglon, {c: _validar_campo_renglon_pdf(c, v) for c, v in cambios.items()}))

    archivo = _texto(datos.get("archivo"), "archivo")
    leido = datos.get("leido") if isinstance(datos.get("leido"), dict) else {}

    with db.transaccion(con):
        actual = _leer_oc(con, numero)
        if validos_oc:
            _validar_vigencia(validos_oc.get("vig_desde", actual["vig_desde"]), validos_oc.get("vig_hasta", actual["vig_hasta"]))
            validos_oc["campos_manuales"] = _con_manuales(actual, list(validos_oc))
            db.actualizar_con_version(con, "oc", {"numero": actual["numero"]}, version, validos_oc)
        elif actual["version"] != version:
            raise db.ConflictoVersion()
        for pos, version_renglon, cambios in validos_renglones:
            fila = db.leer_fila(con, "renglon", {"oc": actual["numero"], "pos": pos})
            if fila is None:
                nuevo = {"oc": actual["numero"], "pos": pos, "codigo": "", "descripcion": "", "cantidad": "1", "unidad": "",
                         "precio_centavos": 0, "importe_centavos": 0}
                nuevo.update(cambios)
                if not nuevo["descripcion"]:
                    raise ErrorValidacion("Falta la descripción del renglón %d." % pos)
                if "importe_centavos" not in cambios:
                    nuevo["importe_centavos"] = int((Decimal(nuevo["cantidad"]) * nuevo["precio_centavos"]).to_integral_value())
                nuevo["sap_por_entregar"], nuevo["exceso_sap"] = _por_entregar(
                    nuevo["cantidad"], nuevo.get("desglose_cantidad"), "0")
                nuevo["campos_manuales"] = sorted(cambios)
                db.insertar(con, "renglon", nuevo)
                continue
            if version_renglon is None:
                raise db.ConflictoVersion()
            desglose = [cambios.get(c, fila[c]) for c in ("desglose_cantidad", "desglose_unidad", "desglose_precio_centavos")]
            if any(v is not None for v in desglose) and not all(v is not None for v in desglose):
                raise ErrorValidacion("El desglose del renglón %d necesita cantidad, unidad y precio." % pos)
            por_entregar, exceso = _por_entregar(cambios.get("cantidad", fila["cantidad"]), desglose[0], fila["sap_entregado"])
            if por_entregar != fila["sap_por_entregar"]:
                cambios["sap_por_entregar"] = por_entregar
            if exceso != fila["exceso_sap"]:
                cambios["exceso_sap"] = exceso
            if desglose[0] is not None and fila["revisar_desglose"]:
                cambios["revisar_desglose"] = 0
            cambios["campos_manuales"] = _con_manuales(fila, [c for c in cambios if c in CAMPOS_RENGLON_PDF])
            db.actualizar_con_version(con, "renglon", {"oc": actual["numero"], "pos": pos}, version_renglon, cambios)
        db.registrar_evento(con, "IMPORTACION", "oc", {"numero": actual["numero"]}, None, {
            "fuente": FUENTE_PDF, "archivo": archivo, "leido": leido,
            "campos_oc": sorted(c for c in validos_oc if c != "campos_manuales"),
            "renglones": [pos for pos, _, _ in validos_renglones],
        })
    return ficha_oc(con, numero)


# --- Expedientes -----------------------------------------------------------

TIPOS_EXPEDIENTE = ("COMUN", "CENTRALIZADA", "CORRECTIVO", "EVENTUAL")

# Estructura con la que nace todo expediente (blueprint §4, expediente.datos).
DATOS_INICIALES = {
    "remitos": [],
    "factura": {},
    "sii": {},
    "gde": {},
    "sap": {},
    "notas_aclaratorias": [],
    "checklist": {},
    "correctivo": {},
    "eventual": {},
    "centralizada": {},
    "historial": [],
}
# Claves de `datos` que se pueden reemplazar al editar (el historial lo escribe el sistema).
CLAVES_DATOS_EDITABLES = tuple(c for c in DATOS_INICIALES if c != "historial")
_TIPOS_DATOS = {clave: type(valor) for clave, valor in DATOS_INICIALES.items()}

CAMPOS_EDITABLES_EXPEDIENTE = (
    "periodo", "periodo_desde", "periodo_hasta", "periodo_manual", "motivo_pendiente", "fecha_seguimiento",
)
_RE_PERIODO = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _periodo(valor):
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str) or _RE_PERIODO.fullmatch(valor.strip()) is None:
        raise ErrorValidacion("El período debe tener la forma AAAA-MM (por ejemplo 2026-08).")
    return valor.strip()


def _validar_campo_expediente(campo, valor):
    if campo == "periodo":
        return _periodo(valor)
    if campo in ("periodo_desde", "periodo_hasta"):
        return _fecha(valor, "del período" + (" (desde)" if campo == "periodo_desde" else " (hasta)"))
    if campo == "fecha_seguimiento":
        return _fecha(valor, "de seguimiento")
    if campo == "periodo_manual":
        return _bandera(valor, "período manual")
    return _texto(valor, campo)


def _validar_datos(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacion("Los datos del expediente deben ser un objeto.")
    for clave, valor in datos.items():
        if clave not in CLAVES_DATOS_EDITABLES:
            raise ErrorValidacion("No se puede editar datos.%s." % clave)
        if not isinstance(valor, _TIPOS_DATOS[clave]):
            tipo = "una lista" if _TIPOS_DATOS[clave] is list else "un objeto"
            raise ErrorValidacion("datos.%s debe ser %s." % (clave, tipo))
    return datos


def numero_factura_normalizado(numero):
    """"0003B00031812" → "0003B00031812"; "0002 - 00003908" → "000200003908"; vacío → ""."""
    texto = numero.strip() if isinstance(numero, str) else ""
    if not texto:
        return ""
    try:
        pv, letra, nro = util.normalizar_factura(texto)
    except ValueError:
        raise ErrorValidacion("El número de factura %s no es válido." % texto) from None
    return "%04d%s%08d" % (pv, letra or "", nro)


def _entrada_historial(accion, estado):
    return {"fecha": db.ahora_utc(), "usuario": getpass.getuser(), "accion": accion, "estado": estado}


def _leer_expediente(con, id_expediente):
    try:
        id_expediente = int(id_expediente)
    except (TypeError, ValueError):
        raise NoEncontrado("No existe el expediente %s." % id_expediente) from None
    fila = db.leer_fila(con, "expediente", {"id": id_expediente})
    if fila is None:
        raise NoEncontrado("No existe el expediente %s." % id_expediente)
    return fila


def _datos_de(fila):
    datos = copy.deepcopy(DATOS_INICIALES)
    try:
        guardados = json.loads(fila.get("datos") or "{}")
    except ValueError:
        guardados = {}
    datos.update(guardados if isinstance(guardados, dict) else {})
    return datos


def obtener_expediente(con, id_expediente):
    """Expediente con `datos` decodificado y la razón social del proveedor."""
    fila = _leer_expediente(con, id_expediente)
    fila["datos"] = _datos_de(fila)
    proveedor = db.leer_fila(con, "proveedor", {"sap": fila["sap"]}) if fila["sap"] else None
    fila["razon_social"] = proveedor["razon_social"] if proveedor else ""
    fila["destinos"] = list(_transiciones(fila["tipo"]).get(fila["estado"], []))
    return fila


def crear_expediente(con, datos):
    """Alta en BORRADOR; el SAP se copia de la OC (salvo EVENTUAL, que puede no tener OC)."""
    if not isinstance(datos, dict):
        raise ErrorValidacion("Faltan los datos del expediente.")
    permitidos = ("tipo", "efector", "oc", "sap", "datos") + CAMPOS_EDITABLES_EXPEDIENTE
    desconocidos = [c for c in datos if c not in permitidos]
    if desconocidos:
        raise ErrorValidacion("Campos desconocidos: %s." % ", ".join(sorted(desconocidos)))
    tipo = datos.get("tipo", "COMUN")
    if tipo not in TIPOS_EXPEDIENTE:
        raise ErrorValidacion("El tipo de expediente debe ser COMUN, CENTRALIZADA, CORRECTIVO o EVENTUAL.")
    numero_oc = util.sap_sin_ceros(_texto(datos.get("oc"), "OC"))
    efector = datos.get("efector")
    if numero_oc:
        oc = _leer_oc(con, numero_oc)
        if efector is None:
            efector = oc["efector"]
        elif efector != oc["efector"]:
            raise ErrorValidacion("La OC %s es de %s, no de %s." % (numero_oc, oc["efector"], efector))
        sap = oc["sap"]
    elif tipo != "EVENTUAL":
        raise ErrorValidacion("Elegí la OC del expediente.")
    else:
        sap = util.sap_sin_ceros(_texto(datos.get("sap"), "SAP"))
    if efector not in EFECTORES:
        raise ErrorValidacion("Elegí el efector (HBI o CASPH).")

    contenido = copy.deepcopy(DATOS_INICIALES)
    contenido.update(copy.deepcopy(_validar_datos(datos.get("datos") or {})))
    estado_inicial = ESTADO_INICIAL.get(tipo, "BORRADOR")
    contenido["historial"] = [_entrada_historial("ALTA", estado_inicial)]
    ahora = db.ahora_utc()
    fila = {
        "tipo": tipo,
        "efector": efector,
        "oc": numero_oc or None,
        "sap": sap,
        "estado": estado_inicial,
        "datos": contenido,
        "factura": numero_factura_normalizado((contenido.get("factura") or {}).get("numero")),
        "creado": ahora,
        "actualizado": ahora,
        "usuario": getpass.getuser(),
    }
    for campo in CAMPOS_EDITABLES_EXPEDIENTE:
        if campo in datos:
            fila[campo] = _validar_campo_expediente(campo, datos[campo])
    with db.transaccion(con):
        nuevo_id = db.insertar(con, "expediente", fila)
    return obtener_expediente(con, nuevo_id)


def _no_anulado(fila):
    if fila["estado"] == "ANULADO":
        raise ErrorNegocio("El expediente está anulado.")


def actualizar_expediente(con, id_expediente, version, cambios):
    """Edita columnas de período/seguimiento y reemplaza claves de primer nivel de `datos`."""
    version = _version(version)
    if not isinstance(cambios, dict) or not cambios:
        raise ErrorValidacion("No hay cambios para guardar.")
    desconocidos = [c for c in cambios if c not in CAMPOS_EDITABLES_EXPEDIENTE + ("datos",)]
    if desconocidos:
        raise ErrorValidacion("No se puede editar: %s." % ", ".join(sorted(desconocidos)))
    columnas = {c: _validar_campo_expediente(c, v) for c, v in cambios.items() if c != "datos"}
    nuevos_datos = _validar_datos(cambios.get("datos") or {})
    if "periodo" in columnas and "periodo_manual" not in columnas:
        columnas["periodo_manual"] = 1  # cambiar el período a mano lo fija
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if columnas.get("periodo") and ("periodo_desde" not in columnas or "periodo_hasta" not in columnas):
            limites = limites_de_periodo(columnas["periodo"], _dia_inicio(con, actual))
            columnas.setdefault("periodo_desde", util.iso(limites.desde))
            columnas.setdefault("periodo_hasta", util.iso(limites.hasta))
        contenido = _datos_de(actual)
        contenido.update(copy.deepcopy(nuevos_datos))
        if "factura" in nuevos_datos:
            columnas["factura"] = numero_factura_normalizado(nuevos_datos["factura"].get("numero"))
        accion = "PERIODO_MANUAL" if columnas.get("periodo_manual") == 1 and "periodo" in columnas else "EDICION"
        contenido["historial"].append(_entrada_historial(accion, actual["estado"]))
        columnas["datos"] = contenido
        columnas["actualizado"] = db.ahora_utc()
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, columnas)
    return obtener_expediente(con, id_expediente)


# --- Remitos y período -----------------------------------------------------

_ERROR_LINEA_REMITO = 'Línea %d: se esperaba "numero;fecha[;fecha_firma]".'


def parsear_remitos_pegados(texto):
    """Una línea por remito: numero;fecha[;fecha_firma] (fechas dd/mm/aaaa). Devuelve remitos con fechas ISO."""
    remitos = []
    for numero_linea, linea in enumerate((texto or "").splitlines(), start=1):
        if not linea.strip():
            continue
        partes = [p.strip() for p in linea.split(";")]
        if len(partes) not in (2, 3) or not partes[0] or not partes[1]:
            raise ErrorValidacion(_ERROR_LINEA_REMITO % numero_linea)
        try:
            fecha = util.iso(util.fecha_desde_texto(partes[1]))
            fecha_firma = util.iso(util.fecha_desde_texto(partes[2])) if len(partes) == 3 and partes[2] else None
        except ValueError:
            raise ErrorValidacion(_ERROR_LINEA_REMITO % numero_linea) from None
        remitos.append({
            "numero": partes[0],
            "fecha": fecha,
            "fecha_firma": fecha_firma,
            "es_equipo_comodato": False,
            "aclara_periodo": False,
            "items": [],
        })
    return remitos


def fecha_base(remito):
    """Fecha que define el período: la de firma si existe, si no la del remito."""
    return remito.get("fecha_firma") or remito.get("fecha")


def _remitos_de_periodo(remitos):
    return [r for r in remitos if not r.get("es_equipo_comodato") and fecha_base(r)]


def periodo_sugerido(oc, remitos):
    """Período del remito (no de equipo) con la fecha base más reciente; None si no hay remitos."""
    candidatos = _remitos_de_periodo(remitos)
    if not candidatos:
        return None
    mas_reciente = max(fecha_base(r) for r in candidatos)
    dia = int((oc or {}).get("dia_inicio_periodo") or 1)
    return util.periodo_de_fecha(util.fecha_desde_texto(mas_reciente), dia)


def remitos_fuera_de_periodo(periodo, remitos):
    """Números de remito (no de equipo, sin aclaración de período) con fecha base fuera del período."""
    if periodo is None:
        return []
    desde, hasta = util.iso(periodo.desde), util.iso(periodo.hasta)
    return [
        r["numero"] for r in _remitos_de_periodo(remitos)
        if not r.get("aclara_periodo") and not desde <= fecha_base(r) <= hasta
    ]


def limites_de_periodo(periodo, dia_inicio=1):
    """"2026-11" con día 17 → Periodo("2026-11", 2026-10-17, 2026-11-16); con día 1 → el mes calendario."""
    anio, mes = (int(p) for p in _periodo(periodo).split("-"))
    if dia_inicio == 1:
        return util.periodo_de_fecha(util.fecha_desde_texto("%04d-%02d-01" % (anio, mes)), 1)
    # el período se nombra por el mes en que termina: su último día es dia_inicio - 1 de ese mes
    return util.periodo_de_fecha(util.fecha_desde_texto("%04d-%02d-%02d" % (anio, mes, dia_inicio - 1)), dia_inicio)


def _dia_inicio(con, expediente):
    if not expediente.get("oc"):
        return 1
    oc = db.leer_fila(con, "oc", {"numero": expediente["oc"]})
    return int(oc["dia_inicio_periodo"]) if oc else 1


def _periodo_dict(periodo):
    if periodo is None:
        return None
    return {"periodo": periodo.periodo, "desde": util.iso(periodo.desde), "hasta": util.iso(periodo.hasta)}


def _periodo_del_expediente(fila):
    if not fila.get("periodo") or not fila.get("periodo_desde") or not fila.get("periodo_hasta"):
        return None
    return util.Periodo(fila["periodo"], util.fecha_desde_texto(fila["periodo_desde"]),
                        util.fecha_desde_texto(fila["periodo_hasta"]))


MAX_REMITOS = 20


def remitos_del_formulario(remitos):
    """Remitos cargados uno por uno: [{numero, fecha, fecha_firma?, es_equipo_comodato?}] con fechas ISO o dd/mm/aaaa."""
    if not isinstance(remitos, list):
        raise ErrorValidacion("Faltan los remitos.")
    nuevos = []
    for orden, remito in enumerate(remitos, start=1):
        if not isinstance(remito, dict):
            raise ErrorValidacion("Remito %d: datos inválidos." % orden)
        numero = str(remito.get("numero") or "").strip()
        if not numero:
            raise ErrorValidacion("Remito %d: falta el número." % orden)
        try:
            fecha = util.iso(util.fecha_desde_texto(str(remito.get("fecha") or "").strip()))
        except ValueError:
            raise ErrorValidacion("Remito %s: falta la fecha o no es válida." % numero) from None
        firma = str(remito.get("fecha_firma") or "").strip()
        try:
            fecha_firma = util.iso(util.fecha_desde_texto(firma)) if firma else None
        except ValueError:
            raise ErrorValidacion("Remito %s: la fecha de firma no es válida." % numero) from None
        nuevos.append({
            "numero": numero, "fecha": fecha, "fecha_firma": fecha_firma,
            "es_equipo_comodato": _bandera(remito.get("es_equipo_comodato") or 0, "es_equipo_comodato") == 1,
            "aclara_periodo": False, "items": [],
        })
    return nuevos


def pegar_remitos(con, id_expediente, version, texto, es_equipo_comodato=False, remitos=None):
    """Agrega remitos (pegados o del formulario, uno por uno); un mismo número reemplaza al anterior (conserva sus cantidades).

    Máximo MAX_REMITOS por expediente. Si el período no es manual, lo sugiere.
    """
    version = _version(version)
    if remitos is not None:
        nuevos = remitos_del_formulario(remitos)
    else:
        nuevos = parsear_remitos_pegados(texto)
        equipo = _bandera(es_equipo_comodato if es_equipo_comodato is not None else 0, "es_equipo_comodato") == 1
        for remito in nuevos:
            remito["es_equipo_comodato"] = equipo
    if not nuevos:
        raise ErrorValidacion("Cargá al menos un remito (número y fecha).")
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        contenido = _datos_de(actual)
        por_numero = {r["numero"]: i for i, r in enumerate(contenido["remitos"])}
        for remito in nuevos:
            if remito["numero"] in por_numero:
                anterior = contenido["remitos"][por_numero[remito["numero"]]]
                if not remito["es_equipo_comodato"] and not anterior.get("es_equipo_comodato"):
                    remito["items"] = anterior.get("items") or []
                    remito["aclara_periodo"] = bool(anterior.get("aclara_periodo"))
                contenido["remitos"][por_numero[remito["numero"]]] = remito
            else:
                por_numero[remito["numero"]] = len(contenido["remitos"])
                contenido["remitos"].append(remito)
        if len(contenido["remitos"]) > MAX_REMITOS:
            raise ErrorValidacion("Un expediente puede tener hasta %d remitos (quedarían %d)."
                                  % (MAX_REMITOS, len(contenido["remitos"])))
        oc = db.leer_fila(con, "oc", {"numero": actual["oc"]}) if actual.get("oc") else None
        sugerido = periodo_sugerido(oc, contenido["remitos"])
        columnas = {}
        if sugerido is not None and not actual["periodo_manual"]:
            columnas.update(periodo=sugerido.periodo, periodo_desde=util.iso(sugerido.desde),
                            periodo_hasta=util.iso(sugerido.hasta))
        contenido["historial"].append(_entrada_historial("REMITOS", actual["estado"]))
        columnas["datos"] = contenido
        columnas["actualizado"] = db.ahora_utc()
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, columnas)
    expediente = obtener_expediente(con, id_expediente)
    expediente["periodo_sugerido"] = _periodo_dict(sugerido)
    expediente["fuera_de_periodo"] = remitos_fuera_de_periodo(
        _periodo_del_expediente(expediente), expediente["datos"]["remitos"])
    return expediente


def anular_expediente(con, id_expediente, version, motivo):
    """Pasa a ANULADO con motivo (la fila nunca se borra) y registra el evento ANULACION."""
    version = _version(version)
    motivo = motivo.strip() if isinstance(motivo, str) else ""
    if not motivo:
        raise ErrorValidacion("Indicá el motivo de la anulación.")
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        contenido = _datos_de(actual)
        contenido["historial"].append(_entrada_historial("ANULACION", "ANULADO"))
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, {
            "estado": "ANULADO",
            "motivo_anulacion": motivo,
            "datos": contenido,
            "actualizado": db.ahora_utc(),
        }, accion="ANULACION")
    return obtener_expediente(con, id_expediente)


def listar_expedientes(con, estado=None, tipo=None, periodo=None, sap=None, entrega=None, efector=None):
    """Expedientes (sin `datos`) con la razón social del proveedor, filtrados por los parámetros dados."""
    sql = (
        "SELECT e.id, e.tipo, e.efector, e.oc, e.sap, p.razon_social, e.periodo, e.periodo_desde, e.periodo_hasta, "
        "e.factura, e.estado, e.motivo_pendiente, e.fecha_seguimiento, e.entrega_id, e.creado, e.actualizado, "
        "e.usuario, e.version "
        "FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap"
    )
    condiciones, parametros = [], []
    for columna, valor in (("e.estado", estado), ("e.tipo", tipo), ("e.periodo", periodo), ("e.efector", efector)):
        if valor:
            condiciones.append("%s = ?" % columna)
            parametros.append(valor)
    if sap:
        condiciones.append("e.sap = ?")
        parametros.append(util.sap_sin_ceros(str(sap)))
    if entrega not in (None, ""):
        condiciones.append("e.entrega_id = ?")
        parametros.append(_entero(entrega, "entrega"))
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY e.periodo DESC, e.id DESC"
    filas = []
    for fila in con.execute(sql, parametros):
        dic = dict(fila)
        dic["razon_social"] = dic["razon_social"] or ""
        filas.append(dic)
    return filas


# --- Consumo y saldo -------------------------------------------------------

SIN_PERIODO = "sin_periodo"
COLUMNA_UNICA = "unica"


def _cantidad(valor):
    """Texto/int/Decimal de cantidad → Decimal exacto; vacío o inválido → 0."""
    if valor is None or valor == "":
        return Decimal(0)
    try:
        return util.a_decimal(valor if isinstance(valor, (int, Decimal)) else str(valor), decimales=None)
    except (TypeError, ValueError):
        return Decimal(0)


def _cantidad_texto(numero):
    """Decimal → texto sin ceros de más ni exponente: Decimal("8.000") → "8"."""
    if numero == 0:
        return "0"
    return format(numero.normalize(), "f")


def cantidades_del_expediente(exp):
    """Suma por posición de los ítems de los remitos que no son del equipo en comodato."""
    datos = exp.get("datos")
    if isinstance(datos, str):
        datos = _datos_de(exp)
    cantidades = _cantidades_de_remitos(datos or {})
    if cantidades:
        return cantidades
    # Meses ya facturados sin remitos cargados (p. ej. migrados): el consumo se carga a mano.
    manual = (datos or {}).get("consumo_manual")
    for pos, cantidad in (manual.items() if isinstance(manual, dict) else []):
        try:
            cantidades[int(pos)] = _cantidad(cantidad)
        except (TypeError, ValueError):
            continue
    return cantidades


def _cantidades_de_remitos(datos):
    cantidades = {}
    for remito in datos.get("remitos") or []:
        if remito.get("es_equipo_comodato"):
            continue
        for item in remito.get("items") or []:
            try:
                pos = int(item.get("pos"))
            except (TypeError, ValueError):
                continue
            cantidades[pos] = cantidades.get(pos, Decimal(0)) + _cantidad(item.get("cantidad"))
    return cantidades


def _fin_vigencia(oc):
    hasta = oc.get("vig_hasta")
    prorroga = oc.get("prorroga")
    try:
        if prorroga and (not hasta or util.fecha_desde_texto(prorroga) > util.fecha_desde_texto(hasta)):
            return prorroga
    except ValueError:
        pass
    return hasta


def periodos_de_vigencia(oc):
    """Períodos AAAA-MM de la vigencia de la OC (según su día de inicio); [] si falta el inicio o el fin."""
    desde, hasta = oc.get("vig_desde"), _fin_vigencia(oc)
    if not desde or not hasta:
        return []
    dia = int(oc.get("dia_inicio_periodo") or 1)
    primero = util.periodo_de_fecha(util.fecha_desde_texto(desde), dia).periodo
    ultimo = util.periodo_de_fecha(util.fecha_desde_texto(hasta), dia).periodo
    periodos = []
    anio, mes = (int(p) for p in primero.split("-"))
    while "%04d-%02d" % (anio, mes) <= ultimo:
        periodos.append("%04d-%02d" % (anio, mes))
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return periodos


def _validado_por_renglon(con, numero):
    """{pos: {período: cantidad}} de los expedientes no anulados de la OC."""
    resultado = {}
    filas = con.execute(
        "SELECT periodo, datos FROM expediente WHERE oc = ? AND estado <> 'ANULADO' ORDER BY periodo, id", (numero,),
    )
    for fila in filas:
        periodo = fila["periodo"] or SIN_PERIODO
        for pos, cantidad in cantidades_del_expediente({"datos": fila["datos"]}).items():
            por_periodo = resultado.setdefault(pos, {})
            por_periodo[periodo] = por_periodo.get(periodo, Decimal(0)) + cantidad
    return resultado


def _consumo(con, oc):
    renglones = [dict(f) for f in con.execute("SELECT * FROM renglon WHERE oc = ? ORDER BY pos", (oc["numero"],))]
    validados = _validado_por_renglon(con, oc["numero"])
    umbral = Decimal(str(db.leer_parametros(con).get("umbral_por_agotarse_pct", 85)))
    meses_vigencia = len(periodos_de_vigencia(oc)) or 1
    filas = []
    for r in renglones:
        con_desglose = r.get("desglose_cantidad") not in (None, "")
        cantidad_oc = _cantidad(r["desglose_cantidad"] if con_desglose else r["cantidad"])
        unidad = (r.get("desglose_unidad") if con_desglose else r.get("unidad")) or ""
        previo = _cantidad(r.get("consumo_previo"))
        por_periodo = validados.get(r["pos"], {})
        validado = sum(por_periodo.values(), Decimal(0))
        saldo = cantidad_oc - previo - validado
        if con_desglose and unidad == "MES":
            ideal = Decimal(1)
        else:
            ideal = (cantidad_oc / meses_vigencia).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if cantidad_oc > 0:
            pct = int(((previo + validado) * 100 / cantidad_oc).to_integral_value(rounding=ROUND_HALF_UP))
        else:
            pct = 0
        filas.append({
            "pos": r["pos"],
            "descripcion": r.get("descripcion") or "",
            "cantidad_oc": _cantidad_texto(cantidad_oc),
            "unidad": unidad,
            "consumo_previo": _cantidad_texto(previo),
            "validado": _cantidad_texto(validado),
            "saldo": _cantidad_texto(saldo),
            "ideal_mes": _cantidad_texto(ideal),
            "pct_consumido": pct,
            "por_agotarse": cantidad_oc > 0 and (saldo < ideal or pct >= umbral),
            "por_periodo": {p: _cantidad_texto(c) for p, c in sorted(por_periodo.items())},
        })
    return filas


def consumo_por_renglon(con, oc):
    """Cantidad de la OC, consumo previo, validado, saldo, ideal por mes y alerta de agotamiento por renglón."""
    if not isinstance(oc, dict):
        oc = _leer_oc(con, oc)
    return _consumo(con, oc)


def _grilla_desde(oc, filas):
    periodos = periodos_de_vigencia(oc)
    if not periodos:
        columnas = [COLUMNA_UNICA]
    else:
        # un consumo fuera de la vigencia (o sin período) también se muestra, en su propia columna
        con_consumo = {p for f in filas for p in f["por_periodo"]}
        columnas = sorted((set(periodos) | con_consumo) - {SIN_PERIODO})
        if SIN_PERIODO in con_consumo:
            columnas.append(SIN_PERIODO)
    resultado = []
    for f in filas:
        if columnas == [COLUMNA_UNICA]:
            celdas = {COLUMNA_UNICA: f["validado"]}
        else:
            celdas = {p: f["por_periodo"].get(p, "0") for p in columnas}
        resultado.append({
            "pos": f["pos"], "descripcion": f["descripcion"], "cantidad_oc": f["cantidad_oc"], "unidad": f["unidad"],
            "celdas": celdas, "saldo": f["saldo"], "por_agotarse": f["por_agotarse"],
        })
    return {"periodos": columnas, "filas": resultado}


def grilla(con, oc):
    """Grilla renglón × período: una columna por período de la vigencia (sin fin de vigencia → una sola, "unica")."""
    if not isinstance(oc, dict):
        oc = _leer_oc(con, oc)
    return _grilla_desde(oc, _consumo(con, oc))


def consumo_oc(con, numero):
    """Renglones con su consumo y la grilla, para GET /api/oc/<numero>/consumo."""
    oc = _leer_oc(con, numero)
    filas = _consumo(con, oc)
    return {"renglones": filas, "grilla": _grilla_desde(oc, filas)}


# --- Contexto de controles -------------------------------------------------

def contexto_controles(con, id_expediente):
    """Todo lo que los controles necesitan, leído una sola vez (los controles no leen la base)."""
    expediente = obtener_expediente(con, id_expediente)
    oc = proveedor = None
    renglones, consumo, otros_oc = [], [], []
    if expediente.get("oc"):
        ficha = ficha_oc(con, expediente["oc"])
        oc, proveedor, renglones = ficha["oc"], ficha["proveedor"], ficha["renglones"]
        consumo = _consumo(con, oc)
        otros_oc = [
            dict(f) for f in con.execute(
                "SELECT id, estado, periodo, factura FROM expediente WHERE oc = ? AND id <> ? AND estado <> 'ANULADO' "
                "ORDER BY id", (oc["numero"], expediente["id"]),
            )
        ]
    otros_proveedor = []
    if expediente.get("sap"):
        otros_proveedor = [
            {"id": f["id"], "tipo": f["tipo"], "estado": f["estado"], "periodo": f["periodo"], "factura": f["factura"],
             "fecha_factura": (_datos_de(dict(f)).get("factura") or {}).get("fecha") or ""}
            for f in con.execute(
                "SELECT id, tipo, estado, periodo, factura, datos FROM expediente WHERE sap = ? AND id <> ? "
                "AND estado <> 'ANULADO' AND factura <> '' ORDER BY id", (expediente["sap"], expediente["id"]),
            )
        ]
    return {
        "expediente": expediente,
        "oc": oc,
        "proveedor": proveedor,
        "renglones": renglones,
        "consumo": consumo,
        "parametros": db.leer_parametros(con),
        "otros_de_la_oc": otros_oc,
        "otros_del_proveedor": otros_proveedor,
    }


controles.registrar_armador(contexto_controles)


# --- Notas aclaratorias ----------------------------------------------------

def guardar_nota(con, id_expediente, version, codigo, referencia, texto):
    """Agrega o reemplaza la nota aclaratoria de un control salvable (misma clave = código + referencia)."""
    version = _version(version)
    if codigo == "importe_factura":
        raise ErrorNegocio("Un error de importe no se salva con nota aclaratoria.")
    if codigo not in controles.NOTAS:
        raise ErrorNegocio("Ese control no admite nota aclaratoria.")
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorValidacion("Escribí el texto de la nota aclaratoria.")
    if referencia is not None and not isinstance(referencia, (str, int)):
        raise ErrorValidacion("La referencia de la nota no es válida.")
    referencia = "" if referencia is None else str(referencia)
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        contenido = _datos_de(actual)
        notas = [
            n for n in contenido["notas_aclaratorias"]
            if (n.get("codigo"), "" if n.get("referencia") is None else str(n.get("referencia"))) != (codigo, referencia)
        ]
        notas.append({
            "codigo": codigo, "referencia": referencia, "texto": texto.strip(),
            "usuario": getpass.getuser(), "fecha": db.ahora_utc(),
        })
        contenido["notas_aclaratorias"] = notas
        contenido["historial"].append(_entrada_historial("NOTA_ACLARATORIA", actual["estado"]))
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, {
            "datos": contenido, "actualizado": db.ahora_utc(),
        })
    return obtener_expediente(con, id_expediente)


# --- Textos del expediente -------------------------------------------------

def contexto_textos(con, id_expediente):
    """Datos que necesitan los generadores de `gestor.textos` (que son puros)."""
    exp = obtener_expediente(con, id_expediente)
    datos = exp["datos"]
    parametros = db.leer_parametros(con)
    oc = db.leer_fila(con, "oc", {"numero": exp["oc"]}) if exp.get("oc") else None
    remitos = datos.get("remitos") or []
    equipo = next((r["numero"] for r in remitos if r.get("es_equipo_comodato")), None)
    primera = True
    if oc is not None:
        fila = con.execute(
            "SELECT COUNT(*) FROM expediente WHERE oc = ? AND id <> ? AND estado IN (%s)"
            % ", ".join("?" * len(controles.ESTADOS_VALIDADOS)),
            (oc["numero"], exp["id"]) + controles.ESTADOS_VALIDADOS,
        ).fetchone()
        primera = fila[0] == 0
    factura = datos.get("factura") or {}
    return {
        "efector": exp["efector"],
        "parametros_efector": (parametros.get("efectores") or {}).get(exp["efector"], {}),
        "sigla": ((parametros.get("efectores") or {}).get(exp["efector"]) or {}).get("sigla") or exp["efector"],
        "limite_texto_sap": int(parametros.get("limite_texto_sap", 50)),
        "destino": ((parametros.get("efectores") or {}).get(exp["efector"]) or {}).get("destino", ""),
        "nota_comodato": parametros.get("nota_comodato", ""),
        "sap": exp["sap"],
        "razon": exp.get("razon_social") or "",
        "oc": exp.get("oc") or "",
        "factura": factura.get("numero") or "",
        "centavos": factura.get("centavos"),
        "periodo": exp.get("periodo"),
        "periodo_desde": exp.get("periodo_desde"),
        "periodo_hasta": exp.get("periodo_hasta"),
        "dia_inicio": int(oc["dia_inicio_periodo"]) if oc else 1,
        "remitos": [r["numero"] for r in remitos if not r.get("es_equipo_comodato")],
        "remito_equipo": equipo,
        "fecha_base_remitos": max(
            (fecha_base(r) for r in remitos if not r.get("es_equipo_comodato") and fecha_base(r)), default=None),
        "cantidades": [
            {"pos": pos, "cantidad": _cantidad_texto(cantidad)}
            for pos, cantidad in sorted(cantidades_del_expediente(exp).items())
        ],
        "orden_remito_equipo": (datos.get("gde") or {}).get("orden_remito_equipo") or None,
        "comodato": bool(oc["comodato"]) if oc else False,
        "primera_validacion": primera,
        "tipo_oc": oc["tipo"] if oc else "",
        "objeto": oc["objeto"] if oc else "",
        "articulo": oc["objeto_articulo"] if oc else "",
        "concepto_corto": oc["concepto_corto"] if oc else "",
        "expediente": (datos.get("gde") or {}).get("expediente") or "",
        "expediente_contratacion": oc["expediente_contratacion"] if oc else "",
        "ca": oc["ca"] if oc else "",
        "tipo_expediente": exp["tipo"],
        "procedimiento": (datos.get("correctivo") or {}).get("procedimiento") or "",
        "objeto_correctivo": (datos.get("correctivo") or {}).get("objeto_correctivo") or "",
        "presupuestos": (datos.get("correctivo") or {}).get("presupuestos") or [],
        "monto_convalidado": (datos.get("correctivo") or {}).get("monto_convalidado"),
        "importe_renglon_correctivo": _importe_renglon_correctivo(con, oc["numero"]) if oc else None,
        "leyenda_cv": (oc["leyenda_cv"] or "").strip() if oc else "",
        "doc_requerida_central": _lista_json(oc["doc_requerida_central"]) if oc else [],
        "fecha_factura": factura.get("fecha") or "",
        "eventual": _eventual_para_textos(con, exp, oc, remitos) if exp["tipo"] == "EVENTUAL" else {},
    }


def textos_del_expediente(con, id_expediente):
    """Carátula y referencias GDE (los pasos 17 y 19 agregan más claves)."""
    ctx = contexto_textos(con, id_expediente)
    if ctx["tipo_expediente"] == "EVENTUAL":
        # el eventual puede no tener OC ni remitos: carátula propia y referencias opcionales
        resultado = {"caratula": textos.caratula_eventual(ctx)}
        try:
            resultado["referencias"] = textos.referencias(ctx)
        except textos.TextoIncompleto as error:
            resultado["referencias"] = []
            resultado["referencias_error"] = str(error)
        try:
            resultado["solicitud_pago_eventual"] = textos.solicitud_pago_eventual(ctx)
        except textos.TextoIncompleto as error:
            resultado["solicitud_pago_eventual_error"] = str(error)
    else:
        resultado = {"caratula": textos.caratula(ctx), "referencias": textos.referencias(ctx)}
    try:
        resultado["autorizacion"] = textos.autorizacion(ctx)
    except textos.TextoIncompleto as error:
        resultado["autorizacion_error"] = str(error)
    try:
        resultado["sap"] = textos.textos_sap(ctx, ctx["limite_texto_sap"])
    except textos.TextoIncompleto as error:
        resultado["sap_error"] = str(error)
    if ctx["comodato"] and ctx["primera_validacion"] and ctx["remito_equipo"]:
        try:
            resultado["constancia_comodato"] = textos.constancia_comodato(ctx)
        except textos.TextoIncompleto as error:
            resultado["constancia_comodato_error"] = str(error)
    if ctx["tipo_expediente"] == "CENTRALIZADA":
        try:
            resultado["nota_central"] = textos.nota_central(ctx)
        except textos.TextoIncompleto as error:
            resultado["nota_central_error"] = str(error)
    if ctx["tipo_expediente"] == "CORRECTIVO":
        resultado["correctivo"] = _resumen_correctivo(con, ctx)
        for clave, generador in (("referencia_correctivo", textos.referencia_correctivo),
                                 ("informe_economico", textos.informe_economico)):
            try:
                resultado[clave] = generador(ctx)
            except textos.TextoIncompleto as error:
                resultado[clave + "_error"] = str(error)
    return resultado


# --- Documentos Word -------------------------------------------------------

def _texto_periodo_cv(ctx):
    """"agosto 2026" (mes calendario) o "17/10/2026 al 16/11/2026" (período específico)."""
    if int(ctx.get("dia_inicio") or 1) == 1:
        anio, mes = (int(p) for p in ctx["periodo"].split("-"))
        return "%s %04d" % (util.MESES[mes - 1], anio)
    return "%s al %s" % (util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_desde"])),
                         util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_hasta"])))


def _nombre_docx(referencia):
    return textos.nombre_archivo(referencia)[:-len(".pdf")] + ".docx"


def datos_cv(con, id_expediente):
    """Datos ya formateados para `docx_gen.generar_cv`, la plantilla del efector y el nombre del archivo."""
    ctx = contexto_textos(con, id_expediente)
    if not ctx["oc"]:
        raise textos.TextoIncompleto("El expediente no tiene OC: no se puede armar el certificado de validación.")
    if not (ctx["objeto"] or "").strip():
        raise textos.TextoIncompleto("Falta el objeto de la contratación en la OC %s" % ctx["oc"])
    if not ctx["periodo"]:
        raise textos.TextoIncompleto("Falta cargar el período validado.")
    if not ctx["remitos"]:
        raise textos.TextoIncompleto("Falta cargar al menos un remito.")
    exp = obtener_expediente(con, id_expediente)
    oc = _leer_oc(con, ctx["oc"])
    renglones = {int(r["pos"]): dict(r) for r in con.execute("SELECT * FROM renglon WHERE oc = ?", (oc["numero"],))}
    cantidades = cantidades_del_expediente(exp)
    fechas = {}
    for remito in exp["datos"]["remitos"]:
        if remito.get("es_equipo_comodato") or not remito.get("fecha"):
            continue
        for item in remito.get("items") or []:
            try:
                pos = int(item.get("pos"))
            except (TypeError, ValueError):
                continue
            fecha = util.ddmmaaaa(util.fecha_desde_texto(remito["fecha"]))
            if fecha not in fechas.setdefault(pos, []):
                fechas[pos].append(fecha)
    filas, completa = [], True
    for pos, renglon in sorted(renglones.items()):
        con_desglose = renglon.get("desglose_cantidad") not in (None, "")
        cantidad_oc = _cantidad(renglon["desglose_cantidad"] if con_desglose else renglon["cantidad"])
        entregada = cantidades.get(pos, Decimal(0))
        if entregada != cantidad_oc:
            completa = False
        if entregada == 0:
            continue
        unidad = (renglon.get("desglose_unidad") if con_desglose else renglon.get("unidad")) or ""
        filas.append({
            "renglon": str(pos),
            "descripcion": renglon.get("descripcion") or "",
            "cantidad_oc": _cantidad_texto(cantidad_oc) + (" " + unidad if unidad else ""),
            "cantidad_entregada": _cantidad_texto(entregada),
            "fecha_entrega": ", ".join(fechas.get(pos, [])),
        })
    hasta = util.fecha_desde_texto(ctx["periodo_hasta"]) if ctx.get("periodo_hasta") else None
    hoy = util.fecha_desde_texto(db.ahora_utc()[:10])
    fin_vigencia = _fin_vigencia(oc)
    vigencia = "%s a %s" % (
        util.ddmmaaaa(util.fecha_desde_texto(oc["vig_desde"])) if oc.get("vig_desde") else "—",
        util.ddmmaaaa(util.fecha_desde_texto(fin_vigencia)) if fin_vigencia else "sin fin")
    if oc["tipo"] == "SERVICIO":
        entrega = "Mensual"
    else:
        entrega = "Única" if completa else "Parcial"
    referencia = textos.referencia_cv(ctx)
    datos = {
        "fecha": max(hoy, hasta) if hasta else hoy,
        "proveedor": ctx["razon"],
        "sap": ctx["sap"],
        "expediente": ctx["expediente_contratacion"],
        "ca": ctx["ca"],
        "oc": ctx["oc"],
        "vigencia": vigencia,
        "rubro": "Servicios" if oc["tipo"] == "SERVICIO" else "Bienes",
        "entrega": entrega,
        "periodo_texto": _texto_periodo_cv(ctx),
        "objeto": ctx["objeto"].strip(),
        "renglones": filas,
        "observacion": ctx["leyenda_cv"] if ctx["tipo_expediente"] == "CENTRALIZADA" else "",
        "remitos": ctx["remitos"],
    }
    plantilla = (ctx["parametros_efector"] or {}).get("plantilla_cv")
    if not plantilla:
        raise textos.TextoIncompleto("Falta la plantilla del CV de %s en la configuración." % ctx["efector"])
    return {"datos": datos, "plantilla": plantilla, "archivo": _nombre_docx(referencia)}


def datos_autorizacion(con, id_expediente):
    """Referencia, cuerpo y nombre del archivo .docx de la autorización de pago."""
    autorizacion = textos.autorizacion(contexto_textos(con, id_expediente))
    autorizacion["archivo"] = _nombre_docx(autorizacion["referencia"])
    return autorizacion


# --- Estados ---------------------------------------------------------------

TRANSICIONES_COMUN = {
    "BORRADOR": ["CONTROLADO"],
    "CONTROLADO": ["EN_FIRMA", "BORRADOR"],
    "EN_FIRMA": ["FIRMADO", "CONTROLADO"],
    "FIRMADO": ["ENVIADO"],
    "ENVIADO": ["CONTABILIZADO"],
    "CONTABILIZADO": ["CERRADO"],
}
# Correctivo: nace en RECIBIDO_MANTENIMIENTO y desde CONTROLADO sigue el flujo común (volver atrás va a PARA_FACTURAR).
TRANSICIONES_CORRECTIVO = {
    "RECIBIDO_MANTENIMIENTO": ["INFORME_ECONOMICO"],
    "INFORME_ECONOMICO": ["DEVUELTO"],
    "DEVUELTO": ["PARA_FACTURAR"],
    "PARA_FACTURAR": ["CONTROLADO"],
}
# Pago eventual: flujo propio, nace en ARMADO (la OC puede estar vencida o faltar).
TRANSICIONES_EVENTUAL = {
    "ARMADO": ["EN_DTO_ECONOMICO_CONTABLE"],
    "EN_DTO_ECONOMICO_CONTABLE": ["DEVUELTO"],
    "DEVUELTO": ["CONTABILIZADO"],
    "CONTABILIZADO": ["FINALIZADO"],
}
ESTADO_INICIAL = {"CORRECTIVO": "RECIBIDO_MANTENIMIENTO", "EVENTUAL": "ARMADO"}
ESTADOS_FINALES = ("CERRADO", "ANULADO", "FINALIZADO")


def _transiciones(tipo):
    """Flujo de estados del tipo de expediente."""
    if tipo == "EVENTUAL":
        return TRANSICIONES_EVENTUAL
    if tipo == "CORRECTIVO":
        flujo = dict(TRANSICIONES_COMUN)
        flujo["CONTROLADO"] = ["EN_FIRMA", "PARA_FACTURAR"]
        flujo.update(TRANSICIONES_CORRECTIVO)
        return flujo
    return TRANSICIONES_COMUN


def _estados_de(*flujos):
    return {e for flujo in flujos for origen, destinos in flujo.items() for e in [origen] + list(destinos)}


ESTADOS_CONOCIDOS = tuple(sorted(_estados_de(TRANSICIONES_COMUN, TRANSICIONES_CORRECTIVO, TRANSICIONES_EVENTUAL) | {"PENDIENTE", "ANULADO"}))


def _no_cumple_controlado(con, id_expediente):
    resumen = controles.controlar(con, id_expediente)["resumen"]
    sin_nota = resumen["salvable"] - resumen["salvable_con_nota"]
    if resumen["error"] or sin_nota:
        return "No se puede pasar a CONTROLADO: hay %d errores y %d salvables sin nota." % (resumen["error"], sin_nota)
    return None


def cambiar_estado(con, id_expediente, version, estado, motivo="", fecha_seguimiento=None):
    """Cambia el estado según el flujo del tipo; PENDIENTE pide motivo y fecha de seguimiento y recuerda el estado previo."""
    version = _version(version)
    if not isinstance(estado, str) or estado not in ESTADOS_CONOCIDOS:
        raise ErrorValidacion("Estado desconocido: %s." % estado)
    if estado == "ANULADO":
        raise ErrorNegocio("Para anular usá la opción Anular, que pide el motivo.")
    if estado == "ENVIADO":
        raise ErrorNegocio("Asigná el expediente a una entrega para marcarlo como enviado.")
    motivo = motivo.strip() if isinstance(motivo, str) else ""
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        previo = actual["estado"]
        cambios = {"estado": estado}
        extra = {}
        if estado == "PENDIENTE":
            if previo in ESTADOS_FINALES or previo == "PENDIENTE":
                raise ErrorNegocio("No se puede pasar de %s a PENDIENTE." % previo)
            if not motivo:
                raise ErrorValidacion("Indicá el motivo por el que queda pendiente.")
            seguimiento = _fecha(fecha_seguimiento, "de seguimiento", permitir_vacio=False)
            cambios.update(motivo_pendiente=motivo, fecha_seguimiento=seguimiento)
            extra = {"estado_previo": previo, "motivo": motivo, "fecha_seguimiento": seguimiento}
        else:
            if estado not in _transiciones(actual["tipo"]).get(previo, []):
                raise ErrorNegocio("No se puede pasar de %s a %s." % (previo, estado))
            if estado == "CONTROLADO":
                mensaje = _no_cumple_controlado(con, actual["id"])
                if mensaje:
                    raise ErrorNegocio(mensaje)
        contenido = _datos_de(actual)
        entrada = _entrada_historial("ESTADO", estado)
        entrada.update(extra)
        entrada.setdefault("desde", previo)
        contenido["historial"].append(entrada)
        cambios.update(datos=contenido, actualizado=db.ahora_utc())
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, cambios)
    return obtener_expediente(con, id_expediente)


def reanudar_expediente(con, id_expediente, version):
    """Sale de PENDIENTE y vuelve al estado que tenía antes."""
    version = _version(version)
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        if actual["estado"] != "PENDIENTE":
            raise ErrorNegocio("El expediente no está pendiente.")
        contenido = _datos_de(actual)
        previo = next((h.get("estado_previo") for h in reversed(contenido["historial"]) if h.get("estado_previo")), None)
        if previo is None:
            raise ErrorNegocio("No se encontró el estado anterior al pendiente.")
        entrada = _entrada_historial("REANUDAR", previo)
        entrada["desde"] = "PENDIENTE"
        contenido["historial"].append(entrada)
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, {
            "estado": previo, "motivo_pendiente": "", "fecha_seguimiento": None,
            "datos": contenido, "actualizado": db.ahora_utc(),
        })
    return obtener_expediente(con, id_expediente)


# --- Números GDE -----------------------------------------------------------

CLAVES_GDE = ("expediente", "caratula", "factura", "sii", "oc_pdf", "remitos", "remito_equipo", "orden_remito_equipo",
              "cv", "vale_hoja", "autorizacion", "constancia", "contabilizacion")


def _gde_valido(valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return ""
    if not isinstance(valor, str):
        raise ErrorValidacion('El número GDE "%s" no tiene un formato válido.' % valor)
    normalizado = util.normalizar_gde(valor)
    if not util.validar_gde(normalizado):
        raise ErrorValidacion('El número GDE "%s" no tiene un formato válido.' % valor.strip())
    return normalizado


def guardar_gde(con, id_expediente, version, gde):
    """Reemplaza `datos.gde` con los números normalizados; `oc_pdf` vacío se toma de la OC."""
    version = _version(version)
    if not isinstance(gde, dict):
        raise ErrorValidacion("Faltan los números GDE.")
    desconocidas = [c for c in gde if c not in CLAVES_GDE]
    if desconocidas:
        raise ErrorValidacion("No se puede cargar: %s." % ", ".join(sorted(desconocidas)))
    limpio = {}
    for clave in CLAVES_GDE:
        valor = gde.get(clave)
        if clave == "remitos":
            if valor is None:
                valor = {}
            if not isinstance(valor, dict):
                raise ErrorValidacion("Los GDE de los remitos deben ser un objeto número → GDE.")
            limpio[clave] = {str(numero): _gde_valido(g) for numero, g in valor.items() if _gde_valido(g)}
        elif clave == "orden_remito_equipo":
            limpio[clave] = None if valor in (None, "") else _entero(valor, "orden del remito del equipo", minimo=1)
        else:
            limpio[clave] = _gde_valido(valor)
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if not limpio["oc_pdf"] and actual.get("oc"):
            oc = db.leer_fila(con, "oc", {"numero": actual["oc"]})
            if oc is not None and oc.get("gde_pdf_oc"):
                limpio["oc_pdf"] = util.normalizar_gde(oc["gde_pdf_oc"])
        contenido = _datos_de(actual)
        contenido["gde"] = limpio
        contenido["historial"].append(_entrada_historial("GDE", actual["estado"]))
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, {
            "datos": contenido, "actualizado": db.ahora_utc(),
        })
    return obtener_expediente(con, id_expediente)


def guardar_consumo_manual(con, id_expediente, version, cantidades):
    """Consumo de un mes ya facturado que no tiene remitos cargados: {pos: cantidad} por renglón de la OC.

    Solo para expedientes sin cantidades en sus remitos (si las tiene, el consumo sale de ahí). Cantidad vacía o 0 no se guarda.
    """
    version = _version(version)
    if not isinstance(cantidades, dict):
        raise ErrorValidacion("Faltan las cantidades consumidas por renglón.")
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if not actual.get("oc"):
            raise ErrorNegocio("El expediente %s no tiene OC: no hay renglones para cargarle consumo." % actual["id"])
        contenido = _datos_de(actual)
        if _cantidades_de_remitos(contenido):
            raise ErrorNegocio("El expediente %s ya tiene el consumo de sus remitos; se corrige desde el paso 2." % actual["id"])
        posiciones = {f["pos"] for f in con.execute("SELECT pos FROM renglon WHERE oc = ?", (actual["oc"],))}
        limpio = {}
        for pos, valor in cantidades.items():
            try:
                pos_int = int(pos)
            except (TypeError, ValueError):
                raise ErrorValidacion("Renglón inválido: %s." % pos) from None
            if pos_int not in posiciones:
                raise ErrorValidacion("La OC %s no tiene el renglón %s." % (actual["oc"], pos_int))
            texto = str(valor if valor is not None else "").strip()
            if not texto:
                continue
            try:
                cantidad = util.a_decimal(texto, decimales=None)
            except (TypeError, ValueError):
                raise ErrorValidacion("Revisá la cantidad del renglón %s: «%s» no es un número." % (pos_int, texto)) from None
            if cantidad < 0:
                raise ErrorValidacion("La cantidad del renglón %s no puede ser negativa." % pos_int)
            if cantidad:
                limpio[str(pos_int)] = str(cantidad)
        contenido["consumo_manual"] = limpio
        contenido["historial"].append(_entrada_historial("CONSUMO_MANUAL", actual["estado"]))
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version, {
            "datos": contenido, "actualizado": db.ahora_utc(),
        })
    return obtener_expediente(con, id_expediente)


_CAMPOS_FACTURA_REVISION = ("numero", "fecha", "centavos", "cae", "vto_cae", "destinatario", "domicilio",
                            "periodo_desde", "periodo_hasta", "menciona")


def revisar_comprobantes(con, id_expediente, factura=None, sii=None, cuit_emisor=None):
    """Controles de factura y SII sobre lo leído de los PDF (o lo cargado en el paso 3), sin guardar nada.

    Corre los mismos controles del paso 4 (ámbitos factura y sii) y suma lo que solo se ve con los PDF:
    CUIT del emisor y del SII contra el proveedor, y SAP del SII contra el expediente.
    """
    ctx = contexto_controles(con, id_expediente)
    datos = copy.deepcopy(ctx["expediente"].get("datos") or {})
    if isinstance(factura, dict):
        actual = dict(datos.get("factura") or {})
        actual.update({k: v for k, v in factura.items() if k in _CAMPOS_FACTURA_REVISION})
        datos["factura"] = actual
    if isinstance(sii, dict) and sii:
        datos["sii"] = sii
    ctx["expediente"] = dict(ctx["expediente"], datos=datos)
    resultados = [r for r in controles.evaluar(ctx)["resultados"] if r["ambito"] in ("factura", "sii")]
    proveedor = ctx.get("proveedor") or {}
    cuit_proveedor = re.sub(r"\D", "", proveedor.get("cuit") or "")

    def extra(codigo, ambito, mensaje):
        resultados.append({"codigo": codigo, "nivel": "error", "ambito": ambito, "mensaje": mensaje, "referencia": None})

    if cuit_emisor and cuit_proveedor and re.sub(r"\D", "", cuit_emisor) != cuit_proveedor:
        extra("cuit_factura", "factura", "El CUIT de la factura (%s) no es el del proveedor %s (%s)."
              % (cuit_emisor, proveedor.get("razon_social") or "", proveedor.get("cuit")))
    datos_sii = datos.get("sii") or {}
    if datos_sii:
        cuit_sii = re.sub(r"\D", "", datos_sii.get("cuit") or "")
        if cuit_sii and cuit_proveedor and cuit_sii != cuit_proveedor:
            extra("cuit_sii", "sii", "El CUIT cargado en el SII (%s) no es el del proveedor (%s)."
                  % (datos_sii.get("cuit"), proveedor.get("cuit")))
        sap = ctx["expediente"].get("sap")
        if datos_sii.get("sap") and sap and util.sap_sin_ceros(datos_sii["sap"]) != util.sap_sin_ceros(sap):
            extra("sap_sii", "sii", "El N° SAP del SII (%s) no es el del proveedor del expediente (%s)." % (datos_sii["sap"], sap))
        letra_factura = None
        try:
            letra_factura = util.normalizar_factura(datos.get("factura", {}).get("numero") or "")[1]
        except ValueError:
            pass
        if letra_factura and datos_sii.get("letra") and datos_sii["letra"] != letra_factura:
            extra("letra_sii", "sii", "En el SII el comprobante es %s y la factura es letra %s."
                  % (datos_sii.get("tipo_comprobante"), letra_factura))
    errores = sum(1 for r in resultados if r["nivel"] == "error")
    return {"resultados": resultados, "errores": errores}


# --- Calendario (paso 22) ---------------------------------------------------

ESTADOS_CALENDARIO = {
    "fuera": "-", "validado": "V", "en_curso": "C", "pendiente_motivo": "M",
    "pendiente_en_plazo": "P", "atrasado": "A", "sin_iniciar": "·",
}
_ESTADO_POR_EXPEDIENTE = {
    "FIRMADO": "validado", "ENVIADO": "validado", "CONTABILIZADO": "validado", "CERRADO": "validado",
    "BORRADOR": "en_curso", "CONTROLADO": "en_curso", "EN_FIRMA": "en_curso",
    "PENDIENTE": "pendiente_motivo",
    # correctivo y pago eventual
    "RECIBIDO_MANTENIMIENTO": "en_curso", "INFORME_ECONOMICO": "en_curso", "DEVUELTO": "en_curso",
    "PARA_FACTURAR": "en_curso", "ARMADO": "en_curso", "EN_DTO_ECONOMICO_CONTABLE": "en_curso",
    "FINALIZADO": "validado",
}
_PRIORIDAD_CALENDARIO = ("validado", "en_curso", "pendiente_motivo")


def _fecha_hoy(hoy):
    if hoy in (None, ""):
        return datetime.now().date()
    try:
        return util.fecha_desde_texto(hoy)
    except ValueError:
        raise ErrorValidacion('La fecha "hoy" no es válida (se espera AAAA-MM-DD).') from None


def _expedientes_por_celda(con, anio):
    """{(oc, período): [filas]} de los expedientes no anulados del año, con el estado de su entrega."""
    filas = con.execute(
        "SELECT e.id, e.tipo, e.oc, e.periodo, e.estado, e.datos, en.estado AS estado_entrega FROM expediente e "
        "LEFT JOIN entrega en ON en.id = e.entrega_id "
        "WHERE e.oc IS NOT NULL AND e.estado <> 'ANULADO' AND e.periodo LIKE ? ORDER BY e.id",
        ("%04d-%%" % anio,),
    )
    celdas = {}
    for fila in filas:
        celdas.setdefault((fila["oc"], fila["periodo"]), []).append(dict(fila))
    return celdas


def _celda_calendario(periodo, vig_desde, vig_fin, expedientes, hoy, dias_gracia):
    celda = {"periodo": periodo.periodo, "desde": util.iso(periodo.desde), "hasta": util.iso(periodo.hasta),
             "expediente_id": None, "entrega_enviada": False, "centralizada_enviada": False}
    por_estado = {}
    for exp in expedientes:
        por_estado.setdefault(_ESTADO_POR_EXPEDIENTE.get(exp["estado"]), exp)
    celda["entrega_enviada"] = any(e["estado_entrega"] == "ENVIADA" for e in expedientes)
    celda["centralizada_enviada"] = any(e["tipo"] == "CENTRALIZADA" and centralizada_enviada(e) for e in expedientes)
    elegido = next((por_estado[e] for e in _PRIORIDAD_CALENDARIO if e in por_estado), None)
    if periodo.hasta < vig_desde or periodo.desde > vig_fin:
        estado = "fuera"
    elif elegido is not None:
        estado = _ESTADO_POR_EXPEDIENTE[elegido["estado"]]
    elif hoy < periodo.desde:
        estado = "sin_iniciar"
    elif hoy <= periodo.hasta + timedelta(days=dias_gracia):
        estado = "pendiente_en_plazo"
    else:
        estado = "atrasado"
    if elegido is not None:
        celda["expediente_id"] = elegido["id"]
    elif expedientes:
        celda["expediente_id"] = expedientes[0]["id"]
    celda.update(estado=estado, letra=ESTADOS_CALENDARIO[estado])
    return celda


def calendario(con, anio, efector=None, tipo=None, sap=None, hoy=None):
    """Una fila por OC no excluida con vigencia y 12 celdas (una por mes) con estado, letra y marcas."""
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        raise ErrorValidacion("El año del calendario no es válido.") from None
    if not 2000 <= anio <= 2100:
        raise ErrorValidacion("El año del calendario no es válido.")
    hoy = _fecha_hoy(hoy)
    parametros = db.leer_parametros(con)
    dias_gracia = int(parametros.get("dias_gracia", 10))
    dias_aviso = int(parametros.get("dias_aviso_vencimiento_oc", 60))
    sql = ("SELECT oc.*, p.razon_social FROM oc JOIN proveedor p ON p.sap = oc.sap "
           "WHERE oc.excluida = 0 AND oc.vig_desde IS NOT NULL")
    parametros_sql = []
    for columna, valor, validos in (("efector", efector, EFECTORES), ("tipo", tipo, TIPOS_OC), ("sap", sap, None)):
        if valor and (validos is None or valor in validos):
            sql += " AND oc.%s = ?" % columna
            parametros_sql.append(str(valor))
    expedientes = _expedientes_por_celda(con, anio)
    filas = []
    for oc in con.execute(sql + " ORDER BY p.razon_social, oc.numero", parametros_sql):
        oc = dict(oc)
        fin = _fin_vigencia(oc)
        if not fin:
            continue
        try:
            vig_desde, vig_fin = util.fecha_desde_texto(oc["vig_desde"]), util.fecha_desde_texto(fin)
        except ValueError:
            continue
        dia = int(oc.get("dia_inicio_periodo") or 1)
        celdas = [
            _celda_calendario(limites_de_periodo("%04d-%02d" % (anio, mes), dia), vig_desde, vig_fin,
                              expedientes.get((oc["numero"], "%04d-%02d" % (anio, mes)), []), hoy, dias_gracia)
            for mes in range(1, 13)
        ]
        if all(c["estado"] == "fuera" for c in celdas):
            continue
        filas.append({
            "oc": oc["numero"], "efector": oc["efector"], "sap": oc["sap"], "razon_social": oc["razon_social"],
            "objeto": oc["objeto"], "tipo": oc["tipo"], "vig_desde": oc["vig_desde"], "vig_hasta": fin,
            "vence_pronto": 0 <= (vig_fin - hoy).days <= dias_aviso,
            "celdas": celdas,
        })
    return {"anio": anio, "hoy": util.iso(hoy), "estados": ESTADOS_CALENDARIO, "filas": filas}


# --- Alertas de Inicio (paso 23) ---------------------------------------------

MENSAJE_BASE_CON_ERRORES = ("La base de datos tiene errores de integridad. "
                            "Restaurá la última copia de seguridad desde Configuración.")
MENSAJE_INFORME_CORRECTIVOS = "Enviar a GESP el informe mensual de correctivos del mes anterior."


def _alerta(tipo, urgencia, mensaje, oc=None, expediente_id=None, fecha=""):
    return {"tipo": tipo, "urgencia": urgencia, "mensaje": mensaje, "oc": oc, "expediente_id": expediente_id,
            "fecha": fecha or ""}


def _enumerar(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def dia_habil_del_mes(fecha):
    """Número de día hábil (lunes a viernes) de `fecha` dentro de su mes; 0 si cae sábado o domingo."""
    if fecha.weekday() >= 5:
        return 0
    return sum(1 for dia in range(1, fecha.day + 1) if fecha.replace(day=dia).weekday() < 5)


def _oc_activas(con, hoy):
    """OC no excluidas cuya vigencia no terminó (o sin fin cargado)."""
    activas = []
    for fila in con.execute("SELECT oc.*, p.razon_social FROM oc JOIN proveedor p ON p.sap = oc.sap "
                            "WHERE oc.excluida = 0 ORDER BY oc.numero"):
        oc = dict(fila)
        fin = _fin_vigencia(oc)
        try:
            if fin and util.fecha_desde_texto(fin) < hoy:
                continue
        except ValueError:
            pass
        activas.append(oc)
    return activas


def _alertas_calendario(con, hoy):
    alertas = []
    atrasados = {}
    for anio in (hoy.year - 1, hoy.year):
        datos = calendario(con, anio, hoy=util.iso(hoy))
        for fila in datos["filas"]:
            periodos = [c for c in fila["celdas"] if c["estado"] == "atrasado"]
            if periodos:
                atrasados.setdefault(fila["oc"], (fila, []))[1].extend(periodos)
            if anio == hoy.year and fila["vence_pronto"]:
                dias = (util.fecha_desde_texto(fila["vig_hasta"]) - hoy).days
                alertas.append(_alerta(
                    "oc_por_vencer", 2,
                    "La OC %s (%s) vence el %s (en %d días)." % (
                        fila["oc"], fila["razon_social"], util.ddmmaaaa(util.fecha_desde_texto(fila["vig_hasta"])), dias),
                    oc=fila["oc"], fecha=fila["vig_hasta"]))
    for numero, (fila, celdas) in atrasados.items():
        alertas.append(_alerta(
            "periodo_atrasado", 1,
            "OC %s (%s): sin expediente para %s, ya pasaron los días de gracia." % (
                numero, fila["razon_social"], _enumerar(c["periodo"] for c in celdas)),
            oc=numero, fecha=celdas[0]["hasta"]))
    return alertas


def _alertas_oc(con, hoy):
    alertas = []
    for oc in _oc_activas(con, hoy):
        agotandose = [r for r in _consumo(con, oc) if r["por_agotarse"]]
        if agotandose:
            alertas.append(_alerta(
                "renglon_por_agotarse", 2,
                "OC %s (%s): %s por agotarse (%s)." % (
                    oc["numero"], oc["razon_social"], "el renglón" if len(agotandose) == 1 else "los renglones",
                    _enumerar("%d: saldo %s %s, %d%% consumido" % (r["pos"], r["saldo"], r["unidad"], r["pct_consumido"])
                              for r in agotandose)),
                oc=oc["numero"], fecha=_fin_vigencia(oc) or ""))
        if oc["comodato"]:
            con_equipo = False
            for fila in con.execute("SELECT datos FROM expediente WHERE oc = ? AND estado <> 'ANULADO'", (oc["numero"],)):
                remitos = _datos_de(dict(fila)).get("remitos") or []
                if any(isinstance(r, dict) and r.get("es_equipo_comodato") for r in remitos):
                    con_equipo = True
                    break
            if not con_equipo:
                alertas.append(_alerta(
                    "comodato_sin_equipo", 2,
                    "OC %s (%s) con equipo en comodato: todavía no hay ningún expediente con el remito del equipo." % (
                        oc["numero"], oc["razon_social"]),
                    oc=oc["numero"], fecha=oc["vig_desde"] or ""))
    return alertas


def _descripcion_expediente(fila):
    partes = ["Expediente %d" % fila["id"]]
    if fila["oc"]:
        partes.append("OC %s" % fila["oc"])
    if fila["razon_social"]:
        partes.append(fila["razon_social"])
    if fila["periodo"]:
        partes.append("período %s" % fila["periodo"])
    return partes[0] + (" (" + ", ".join(partes[1:]) + ")" if len(partes) > 1 else "")


def _alertas_expedientes(con, hoy):
    alertas = []
    filas = con.execute(
        "SELECT e.id, e.tipo, e.oc, e.periodo, e.estado, e.motivo_pendiente, e.fecha_seguimiento, e.entrega_id, "
        "e.actualizado, p.razon_social FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap "
        "WHERE e.estado IN ('PENDIENTE', 'FIRMADO', 'INFORME_ECONOMICO', 'EN_DTO_ECONOMICO_CONTABLE') ORDER BY e.id"
    )
    for fila in filas:
        fila = dict(fila)
        nombre = _descripcion_expediente(fila)
        if fila["estado"] == "PENDIENTE" and fila["fecha_seguimiento"] and fila["fecha_seguimiento"] < util.iso(hoy):
            alertas.append(_alerta(
                "pendiente_vencido", 1,
                "%s pendiente: %s. El seguimiento era el %s." % (
                    nombre, fila["motivo_pendiente"] or "sin motivo",
                    util.ddmmaaaa(util.fecha_desde_texto(fila["fecha_seguimiento"]))),
                oc=fila["oc"], expediente_id=fila["id"], fecha=fila["fecha_seguimiento"]))
        elif fila["estado"] == "FIRMADO" and fila["entrega_id"] is None:
            alertas.append(_alerta("listo_sin_entrega", 3, "%s firmado y sin entrega asignada." % nombre,
                                   oc=fila["oc"], expediente_id=fila["id"], fecha=fila["actualizado"][:10]))
        elif (fila["tipo"], fila["estado"]) in (("CORRECTIVO", "INFORME_ECONOMICO"), ("EVENTUAL", "EN_DTO_ECONOMICO_CONTABLE")):
            alertas.append(_alerta("esperando_devolucion", 2, "%s esperando la devolución del área económica." % nombre,
                                   oc=fila["oc"], expediente_id=fila["id"], fecha=fila["actualizado"][:10]))
    return alertas


def alertas(con, hoy=None, integridad_ok=True):
    """Alertas de la pantalla Inicio, ordenadas por urgencia (1 alta … 3 baja) y después por fecha."""
    hoy = _fecha_hoy(hoy)
    lista = []
    if not integridad_ok:
        lista.append(_alerta("base_con_errores", 1, MENSAJE_BASE_CON_ERRORES))
    lista.extend(_alertas_calendario(con, hoy))
    lista.extend(_alertas_oc(con, hoy))
    lista.extend(_alertas_expedientes(con, hoy))
    if 1 <= dia_habil_del_mes(hoy) <= 5:
        lista.append(_alerta("informe_correctivos", 2, MENSAJE_INFORME_CORRECTIVOS, fecha=util.iso(hoy)))
    lista.sort(key=lambda a: (a["urgencia"], a["tipo"] != "base_con_errores", a["fecha"], a["oc"] or "",
                              a["expediente_id"] or 0))
    return lista


# --- Entregas (paso 24) -----------------------------------------------------

MENSAJE_ASIGNAR = "Solo se asignan expedientes FIRMADO del mismo efector."


def _leer_entrega(con, entrega_id):
    try:
        entrega_id = int(entrega_id)
    except (TypeError, ValueError):
        raise ErrorValidacion("El número de entrega no es válido.") from None
    fila = db.leer_fila(con, "entrega", {"id": entrega_id})
    if fila is None:
        raise NoEncontrado("No existe la entrega %d." % entrega_id)
    return fila


def _expedientes_de_entrega(con, entrega_id):
    filas = con.execute(
        "SELECT e.id, e.tipo, e.oc, e.sap, p.razon_social, e.periodo, e.factura, e.estado, e.version "
        "FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap WHERE e.entrega_id = ? ORDER BY e.id", (entrega_id,),
    )
    return [dict(f) for f in filas]


def obtener_entrega(con, entrega_id):
    entrega = _leer_entrega(con, entrega_id)
    entrega["expedientes"] = _expedientes_de_entrega(con, entrega["id"])
    return entrega


def crear_entrega(con, efector, nombre=""):
    """Alta de una entrega ABIERTA con el número correlativo siguiente del efector."""
    if efector not in EFECTORES:
        raise ErrorValidacion("Elegí el efector (HBI o CASPH).")
    nombre = _texto(nombre or "", "nombre").strip()
    with db.transaccion(con):
        fila = con.execute("SELECT COALESCE(MAX(numero), 0) AS ultimo FROM entrega WHERE efector = ?", (efector,)).fetchone()
        numero = int(fila["ultimo"]) + 1
        nuevo_id = db.insertar(con, "entrega", {
            "efector": efector, "numero": numero, "nombre": nombre or "Entrega %d" % numero, "estado": "ABIERTA",
        })
    return obtener_entrega(con, nuevo_id)


def listar_entregas(con, efector=None):
    sql = ("SELECT en.*, (SELECT COUNT(*) FROM expediente e WHERE e.entrega_id = en.id) AS expedientes "
           "FROM entrega en")
    parametros = []
    if efector in EFECTORES:
        sql += " WHERE en.efector = ?"
        parametros.append(efector)
    sql += " ORDER BY en.efector, en.numero DESC"
    return [dict(f) for f in con.execute(sql, parametros)]


def firmados_sin_entrega(con, efector=None):
    """Expedientes FIRMADO que todavía no están en ninguna entrega (candidatos a asignar)."""
    sql = ("SELECT e.id, e.tipo, e.efector, e.oc, e.sap, p.razon_social, e.periodo, e.factura, e.version "
           "FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap WHERE e.estado = 'FIRMADO' AND e.entrega_id IS NULL")
    parametros = []
    if efector in EFECTORES:
        sql += " AND e.efector = ?"
        parametros.append(efector)
    return [dict(f) for f in con.execute(sql + " ORDER BY e.id", parametros)]


def _ids_expedientes(ids):
    if not isinstance(ids, list) or not ids:
        raise ErrorValidacion("Elegí al menos un expediente.")
    resultado = []
    for valor in ids:
        if isinstance(valor, bool):
            raise ErrorValidacion("Los expedientes se indican por número.")
        try:
            resultado.append(int(valor))
        except (TypeError, ValueError):
            raise ErrorValidacion("Los expedientes se indican por número.") from None
    return list(dict.fromkeys(resultado))


def _nombre_entrega(entrega):
    return "%s %d" % (entrega["efector"], entrega["numero"])


def asignar_a_entrega(con, entrega_id, version, ids):
    """Asigna expedientes FIRMADO del mismo efector a una entrega ABIERTA (cada uno con su versión y su evento)."""
    version = _version(version)
    ids = _ids_expedientes(ids)
    with db.transaccion(con):
        entrega = _leer_entrega(con, entrega_id)
        if entrega["estado"] != "ABIERTA":
            raise ErrorNegocio("La entrega %d ya se envió: no se le pueden agregar expedientes." % entrega["numero"])
        db.actualizar_con_version(con, "entrega", {"id": entrega["id"]}, version, {"estado": "ABIERTA"})
        for id_expediente in ids:
            actual = _leer_expediente(con, id_expediente)
            if actual["estado"] != "FIRMADO" or actual["efector"] != entrega["efector"]:
                raise ErrorNegocio(MENSAJE_ASIGNAR)
            if actual["entrega_id"] not in (None, entrega["id"]):
                raise ErrorNegocio("El expediente %d ya está en otra entrega." % actual["id"])
            if actual["entrega_id"] == entrega["id"]:
                continue
            contenido = _datos_de(actual)
            entrada = _entrada_historial("ENTREGA", "FIRMADO")
            entrada["entrega"] = _nombre_entrega(entrega)
            contenido["historial"].append(entrada)
            db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, actual["version"], {
                "entrega_id": entrega["id"], "datos": contenido, "actualizado": db.ahora_utc(),
            })
    return obtener_entrega(con, entrega_id)


def quitar_de_entrega(con, entrega_id, version, ids):
    """Saca expedientes de una entrega que todavía no se envió."""
    version = _version(version)
    ids = _ids_expedientes(ids)
    with db.transaccion(con):
        entrega = _leer_entrega(con, entrega_id)
        if entrega["estado"] != "ABIERTA":
            raise ErrorNegocio("La entrega %d ya se envió: no se le pueden quitar expedientes." % entrega["numero"])
        db.actualizar_con_version(con, "entrega", {"id": entrega["id"]}, version, {"estado": "ABIERTA"})
        for id_expediente in ids:
            actual = _leer_expediente(con, id_expediente)
            if actual["entrega_id"] != entrega["id"]:
                raise ErrorNegocio("El expediente %d no está en esta entrega." % actual["id"])
            contenido = _datos_de(actual)
            entrada = _entrada_historial("QUITAR_DE_ENTREGA", actual["estado"])
            entrada["entrega"] = _nombre_entrega(entrega)
            contenido["historial"].append(entrada)
            db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, actual["version"], {
                "entrega_id": None, "datos": contenido, "actualizado": db.ahora_utc(),
            })
    return obtener_entrega(con, entrega_id)


def enviar_entrega(con, entrega_id, version, fecha):
    """Marca la entrega ENVIADA con su fecha y pasa cada expediente asignado a ENVIADO (única vía a ENVIADO)."""
    version = _version(version)
    fecha = _fecha(fecha, "de envío", permitir_vacio=False)
    with db.transaccion(con):
        entrega = _leer_entrega(con, entrega_id)
        if entrega["estado"] != "ABIERTA":
            raise ErrorNegocio("La entrega %d ya se envió." % entrega["numero"])
        expedientes = _expedientes_de_entrega(con, entrega["id"])
        if not expedientes:
            raise ErrorNegocio("La entrega no tiene expedientes asignados.")
        no_firmados = [str(e["id"]) for e in expedientes if e["estado"] != "FIRMADO"]
        if no_firmados:
            raise ErrorNegocio("Para enviar la entrega, todos sus expedientes tienen que estar FIRMADO (revisá: %s)."
                               % ", ".join(no_firmados))
        db.actualizar_con_version(con, "entrega", {"id": entrega["id"]}, version,
                                  {"estado": "ENVIADA", "fecha_envio": fecha})
        for resumen in expedientes:
            actual = _leer_expediente(con, resumen["id"])
            contenido = _datos_de(actual)
            entrada = _entrada_historial("ESTADO", "ENVIADO")
            entrada.update(desde="FIRMADO", entrega=_nombre_entrega(entrega), fecha_envio=fecha)
            contenido["historial"].append(entrada)
            db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, actual["version"], {
                "estado": "ENVIADO", "datos": contenido, "actualizado": db.ahora_utc(),
            })
    return obtener_entrega(con, entrega_id)


# --- Pendientes (paso 25) ---------------------------------------------------

def pendientes(con, hoy=None):
    """Expedientes PENDIENTE con su demora (días desde la fecha de seguimiento, 0 si todavía no llegó), más demorados primero."""
    hoy = _fecha_hoy(hoy)
    filas = con.execute(
        "SELECT e.id, e.tipo, e.efector, e.oc, e.sap, p.razon_social, e.periodo, e.motivo_pendiente, e.fecha_seguimiento "
        "FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap WHERE e.estado = 'PENDIENTE'"
    )
    resultado = []
    for fila in filas:
        demora = 0
        if fila["fecha_seguimiento"]:
            try:
                demora = max(0, (hoy - util.fecha_desde_texto(fila["fecha_seguimiento"])).days)
            except ValueError:
                demora = 0
        resultado.append({
            "id": fila["id"], "tipo": fila["tipo"], "efector": fila["efector"],
            "proveedor": fila["razon_social"] or "", "sap": fila["sap"], "oc": fila["oc"], "periodo": fila["periodo"],
            "motivo": fila["motivo_pendiente"], "fecha_seguimiento": fila["fecha_seguimiento"], "dias_demora": demora,
        })
    resultado.sort(key=lambda f: (-f["dias_demora"], f["fecha_seguimiento"] or "", f["id"]))
    return resultado


# --- Centralizadas (paso 27) --------------------------------------------------

CLAVES_CENTRALIZADA = ("numero_cv", "numero_nota", "fecha_envio")


def _lista_json(valor):
    if isinstance(valor, list):
        return valor
    try:
        lista = json.loads(valor or "[]")
    except ValueError:
        return []
    return lista if isinstance(lista, list) else []


def centralizada_enviada(fila):
    """True si la centralizada ya tiene N° de nota y fecha de envío (marca ◆ del calendario)."""
    central = _datos_de(fila).get("centralizada") or {}
    return bool(central.get("numero_nota") and central.get("fecha_envio"))


def guardar_centralizada(con, id_expediente, version, centralizada):
    """Guarda datos.centralizada = {numero_cv, numero_nota (GDE validados), fecha_envio} de un expediente CENTRALIZADA."""
    version = _version(version)
    if not isinstance(centralizada, dict):
        raise ErrorValidacion("Faltan los datos de la centralizada.")
    desconocidas = [c for c in centralizada if c not in CLAVES_CENTRALIZADA]
    if desconocidas:
        raise ErrorValidacion("Campos desconocidos: %s." % ", ".join(sorted(desconocidas)))
    nuevos = {
        "numero_cv": _gde_valido(centralizada.get("numero_cv")),
        "numero_nota": _gde_valido(centralizada.get("numero_nota")),
        "fecha_envio": _fecha(centralizada.get("fecha_envio"), "de envío") or "",
    }
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if actual["tipo"] != "CENTRALIZADA":
            raise ErrorNegocio("El expediente %d no es una centralizada." % actual["id"])
        contenido = _datos_de(actual)
        contenido["centralizada"] = nuevos
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version,
                                  {"datos": contenido, "actualizado": db.ahora_utc()})
    return obtener_expediente(con, id_expediente)


def centralizadas_por_periodo(con, anio, efector=None):
    """Expedientes CENTRALIZADA del año, ordenados por período, con su nota/CV y si ya se enviaron."""
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        raise ErrorValidacion("El año no es válido.") from None
    sql = ("SELECT e.id, e.efector, e.oc, e.sap, p.razon_social, e.periodo, e.estado, e.datos, e.version, "
           "o.doc_requerida_central FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap "
           "LEFT JOIN oc o ON o.numero = e.oc WHERE e.tipo = 'CENTRALIZADA' AND e.estado <> 'ANULADO' AND e.periodo LIKE ?")
    valores = ["%04d-%%" % anio]
    if efector in EFECTORES:
        sql += " AND e.efector = ?"
        valores.append(efector)
    expedientes = []
    for fila in con.execute(sql + " ORDER BY e.periodo, e.oc, e.id", valores):
        fila = dict(fila)
        datos = _datos_de(fila)
        central = datos.get("centralizada") or {}
        expedientes.append({
            "id": fila["id"], "efector": fila["efector"], "oc": fila["oc"], "sap": fila["sap"],
            "razon_social": fila["razon_social"] or "", "periodo": fila["periodo"], "estado": fila["estado"],
            "version": fila["version"], "numero_cv": central.get("numero_cv") or "",
            "numero_nota": central.get("numero_nota") or "", "fecha_envio": central.get("fecha_envio") or "",
            "checklist": datos.get("checklist") or {}, "enviada": centralizada_enviada(fila),
            "documentos": _lista_json(fila["doc_requerida_central"]),
        })
    return {"anio": anio, "expedientes": expedientes}


# --- Mantenimiento correctivo (paso 28) -------------------------------------------

CLAVES_CORRECTIVO = ("procedimiento", "objeto_correctivo", "presupuestos", "informes", "monto_convalidado")


def _importe_renglon_correctivo(con, numero_oc):
    """Importe (centavos) de los renglones de la OC marcados es_correctivo; None si no hay ninguno."""
    fila = con.execute("SELECT COUNT(*) AS n, COALESCE(SUM(importe_centavos), 0) AS total FROM renglon "
                       "WHERE oc = ? AND es_correctivo = 1", (numero_oc,)).fetchone()
    return int(fila["total"]) if fila["n"] else None


def porcentaje_convalidado(monto_convalidado, importe_renglon):
    """monto_convalidado / importe del renglón de correctivo × 100, entero half-up (None si falta un dato)."""
    if monto_convalidado in (None, "") or not importe_renglon:
        return None
    return util.porcentaje_entero(int(monto_convalidado), int(importe_renglon))


def _resumen_correctivo(con, ctx):
    importe = ctx["importe_renglon_correctivo"]
    return {
        "importe_renglon": importe,
        "monto_convalidado": ctx["monto_convalidado"],
        "porcentaje_convalidado": porcentaje_convalidado(ctx["monto_convalidado"], importe),
    }


def _centavos_validos(valor, nombre):
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ErrorValidacion("%s debe ser un importe en centavos (número entero, sin decimales)." % nombre)
    return valor


def _validar_correctivo(correctivo):
    if not isinstance(correctivo, dict):
        raise ErrorValidacion("Faltan los datos del correctivo.")
    desconocidas = [c for c in correctivo if c not in CLAVES_CORRECTIVO]
    if desconocidas:
        raise ErrorValidacion("Campos desconocidos: %s." % ", ".join(sorted(desconocidas)))
    presupuestos = correctivo.get("presupuestos") or []
    if not isinstance(presupuestos, list):
        raise ErrorValidacion("Los presupuestos deben ser una lista.")
    limpios = []
    for i, p in enumerate(presupuestos, start=1):
        if not isinstance(p, dict):
            raise ErrorValidacion("El presupuesto %d no es válido." % i)
        limpios.append({"proveedor": _texto(p.get("proveedor") or "", "proveedor del presupuesto").strip(),
                        "centavos": _centavos_validos(p.get("centavos"), "El presupuesto %d" % i)})
    informes = correctivo.get("informes") or []
    if not isinstance(informes, list):
        raise ErrorValidacion("Los informes deben ser una lista de números GDE.")
    monto = correctivo.get("monto_convalidado")
    return {
        "procedimiento": _texto(correctivo.get("procedimiento") or "", "procedimiento").strip(),
        "objeto_correctivo": _texto(correctivo.get("objeto_correctivo") or "", "objeto del correctivo").strip(),
        "presupuestos": limpios,
        "informes": [g for g in (_gde_valido(i) for i in informes) if g],
        "monto_convalidado": None if monto in (None, "") else _centavos_validos(monto, "El monto a convalidar"),
    }


def guardar_correctivo(con, id_expediente, version, correctivo):
    """Guarda datos.correctivo de un expediente CORRECTIVO (presupuestos e importes en centavos, informes GDE)."""
    version = _version(version)
    nuevos = _validar_correctivo(correctivo)
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if actual["tipo"] != "CORRECTIVO":
            raise ErrorNegocio("El expediente %d no es un mantenimiento correctivo." % actual["id"])
        contenido = _datos_de(actual)
        contenido["correctivo"] = nuevos
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version,
                                  {"datos": contenido, "actualizado": db.ahora_utc()})
    return obtener_expediente(con, id_expediente)


def informe_mensual_correctivos(con, mes):
    """Correctivos (no anulados) del período `mes` para el informe mensual a GESP."""
    mes = _periodo(mes)
    filas = con.execute(
        "SELECT e.id, e.oc, e.datos, p.razon_social FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap "
        "WHERE e.tipo = 'CORRECTIVO' AND e.estado <> 'ANULADO' AND e.periodo = ? ORDER BY e.oc, e.id", (mes,),
    )
    resultado = []
    for fila in filas:
        fila = dict(fila)
        datos = _datos_de(fila)
        correctivo = datos.get("correctivo") or {}
        resultado.append({
            "id": fila["id"],
            "expediente": (datos.get("gde") or {}).get("expediente") or "",
            "oc": fila["oc"] or "",
            "procedimiento": correctivo.get("procedimiento") or "",
            "adjudicatario": fila["razon_social"] or "",
            "detalle": correctivo.get("objeto_correctivo") or "",
            "monto": correctivo.get("monto_convalidado"),
        })
    return resultado


# --- Pago eventual (paso 29) ------------------------------------------------------

CLAVES_EVENTUAL = (
    "tipo_factura", "establecimiento", "establecimiento_detallado", "tipo_servicio", "docfi", "orden_docfi",
    "remito", "documento_remito", "orden_remito", "providencia_informe", "orden_informe", "cargo_responsable",
    "responsable", "cuit", "orden_compra", "vencimiento_oc", "expediente_anterior", "providencia_prorroga",
    "orden_prorroga", "gerencia", "nota_autorizacion", "orden_autorizacion",
)


def _validar_eventual(eventual):
    if not isinstance(eventual, dict):
        raise ErrorValidacion("Faltan los datos de la solicitud de pago eventual.")
    desconocidas = [c for c in eventual if c not in CLAVES_EVENTUAL]
    if desconocidas:
        raise ErrorValidacion("Campos desconocidos: %s." % ", ".join(sorted(desconocidas)))
    limpio = {}
    for clave in CLAVES_EVENTUAL:
        valor = eventual.get(clave)
        if isinstance(valor, int) and not isinstance(valor, bool):
            valor = str(valor)
        limpio[clave] = _texto(valor or "", clave).strip()
    limpio["tipo_factura"] = limpio["tipo_factura"].upper()
    if limpio["tipo_factura"] not in ("", "B", "C"):
        raise ErrorValidacion('El tipo de factura del pago eventual debe ser "B" o "C".')
    if limpio["orden_compra"]:
        limpio["orden_compra"] = util.sap_sin_ceros(limpio["orden_compra"])
    limpio["vencimiento_oc"] = _fecha(limpio["vencimiento_oc"], "de vencimiento de la OC") or ""
    return limpio


def guardar_eventual(con, id_expediente, version, eventual):
    """Guarda datos.eventual (campos de la solicitud de pago eventual) de un expediente EVENTUAL."""
    version = _version(version)
    nuevos = _validar_eventual(eventual)
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
        if actual["tipo"] != "EVENTUAL":
            raise ErrorNegocio("El expediente %d no es un pago eventual." % actual["id"])
        contenido = _datos_de(actual)
        contenido["eventual"] = nuevos
        db.actualizar_con_version(con, "expediente", {"id": actual["id"]}, version,
                                  {"datos": contenido, "actualizado": db.ahora_utc()})
    return obtener_expediente(con, id_expediente)


def _eventual_para_textos(con, exp, oc, remitos):
    """datos.eventual con valores por defecto tomados de la OC, el proveedor y los remitos cuando falta un campo."""
    proveedor = db.leer_fila(con, "proveedor", {"sap": exp["sap"]}) if exp.get("sap") else None
    primero = next((r["numero"] for r in remitos if not r.get("es_equipo_comodato")), "")
    valores = {
        "remito": primero,
        "cuit": proveedor["cuit"] if proveedor else "",
        "orden_compra": exp.get("oc") or "",
        "vencimiento_oc": (oc["vig_hasta"] or "") if oc else "",
    }
    guardado = exp["datos"].get("eventual") or {}
    valores.update({k: v for k, v in guardado.items() if v not in (None, "")})
    return valores


# --- Servicios del CASPH: AySA y Edenor (paso 30) -----------------------------------

EMPRESAS_SERVICIO_CASPH = ("AYSA", "EDENOR")


def texto_servicio_casph(datos):
    """Valida el pedido de POST /api/textos/servicio-casph y devuelve {"parrafos": [2 strings]}."""
    if not isinstance(datos, dict):
        raise ErrorValidacion("Faltan los datos de la autorización.")
    empresa = datos.get("empresa")
    if empresa not in EMPRESAS_SERVICIO_CASPH:
        raise ErrorValidacion("Elegí la empresa: AYSA o EDENOR.")
    factura = _texto(datos.get("factura"), "factura")
    if not factura:
        raise ErrorValidacion("Falta el N° de factura.")
    centavos = _centavos_validos(datos.get("centavos"), "El importe")
    mes = _texto(datos.get("mes"), "mes").lower()
    if mes not in util.MESES:
        raise ErrorValidacion("El mes no es válido (se espera el nombre del mes, por ejemplo agosto).")
    anio = datos.get("anio")
    if isinstance(anio, str) and anio.strip().isdigit():
        anio = int(anio)
    if isinstance(anio, bool) or not isinstance(anio, int) or not 2000 <= anio <= 2100:
        raise ErrorValidacion("El año no es válido.")
    expediente = _gde_valido(datos.get("expediente"))
    if not expediente:
        raise ErrorValidacion("Falta el N° de expediente.")
    return {"parrafos": textos.autorizacion_servicio_casph(empresa, factura, centavos, mes, anio, expediente)}
