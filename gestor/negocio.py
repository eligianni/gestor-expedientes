"""Reglas de negocio sobre la base (OC, renglones; expedientes desde el paso 9).

Toda escritura va dentro de `db.transaccion`, con control de versión y evento de auditoría.
"""
import copy
import getpass
import json
import re
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
    contenido["historial"] = [_entrada_historial("ALTA", "BORRADOR")]
    ahora = db.ahora_utc()
    fila = {
        "tipo": tipo,
        "efector": efector,
        "oc": numero_oc or None,
        "sap": sap,
        "estado": "BORRADOR",
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
    with db.transaccion(con):
        actual = _leer_expediente(con, id_expediente)
        _no_anulado(actual)
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
