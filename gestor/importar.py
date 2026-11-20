"""Importador del reporte z_compras2 de SAP: mapeo por encabezado, limpieza, descartes, upsert e informe.

Las columnas se buscan por NOMBRE normalizado (util.clave_encabezado), nunca por posición.
"""
import getpass
import json
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from gestor import db, util, xlsx

MAPA = {
    "numero de expediente gde": "expediente_contratacion",
    "clase de pedido": "clase",
    "licitacion": "licitacion",
    "ano licit": "anio_licit",
    "precio unitario": "precio",
    "proveedor": "sap",
    "razon social proveed": "razon_social",
    "n o c": "oc",
    "f o compra": "fecha_oc",
    "in periodo validez": "vig_desde",
    "fin periodo validez": "vig_hasta",
    "posicion": "pos",
    "codigo": "codigo",
    "elemento": "descripcion",
    "cant": "cantidad",
    "importe": "importe",
    "org compras": "org_compras",
    "centro": "centro",
    "centro gestor": "centro_gestor",
    "entrega final": "entrega_final",
    "factura final": "factura_final",
    "por entregar cantid": "sap_por_entregar",
    "entregadas cantidad": "sap_entregado",
    "facturadas cantidad": "sap_facturado",
    "partida presupuestar": "partida",
}

OBLIGATORIAS = ("N° O/C", "Posición.", "Elemento", "Cant", "Importe", "Centro", "Proveedor", "Razón Social Proveed")

AVISO_SIN_PARTIDA = (
    "Este reporte no tiene la partida presupuestaria; no se pueden descartar honorarios (3490000). "
    "Agregá la columna al layout del z_compras2."
)

MOTIVOS_DESCARTE = ("sin_oc", "partida", "centro", "exclusion_manual")

# Campos de la OC que vienen del reporte o se infieren al importar (los demás se cargan a mano).
CAMPOS_OC = (
    "efector", "sap", "clase", "org_compras", "centro", "ca", "expediente_contratacion",
    "fecha_oc", "vig_desde", "vig_hasta", "cerrada_sap", "tipo", "comodato", "centralizada", "dia_inicio_periodo",
)
# Campos del renglón que vienen del reporte o se infieren al importar.
CAMPOS_RENGLON = (
    "codigo", "descripcion", "cantidad", "precio_centavos", "importe_centavos", "partida",
    "sap_entregado", "sap_facturado", "sap_por_entregar", "revisar_importe", "crudo",
    "desglose_cantidad", "desglose_unidad", "desglose_precio_centavos", "revisar_desglose", "exceso_sap",
)

RE_ANIO_FINAL = re.compile(r"[-\s]+(20\d\d)\s*$")
RE_CODIGO_SERVICIO = re.compile(r"1\d{6}")
# Campos que, si cambian, se listan en informe["cambios"].
CAMPOS_CAMBIO_RENGLON = ("precio_centavos", "cantidad")
CAMPOS_CAMBIO_OC = ("vig_desde", "vig_hasta")


class ErrorImportacion(Exception):
    """El reporte no se puede importar (columna faltante, efector inválido, etc.)."""


# --- Conversión de celdas --------------------------------------------------

def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _texto_decimal(numero):
    """Decimal → texto sin ceros de más: Decimal("3600.00") → "3600", Decimal("1.50") → "1.5"."""
    texto = format(numero, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in ("", "-0") else texto


def _decimal(valor):
    texto = _texto(valor)
    return util.a_decimal(texto) if texto else Decimal("0.00")


def _fecha(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return util.fecha_desde_serial_excel(texto)
    except (ValueError, ArithmeticError):
        return util.fecha_desde_texto(texto)


def _centavos_de_decimal(numero):
    return int((numero * 100).to_integral_value(rounding=ROUND_HALF_UP))


# --- Lectura y limpieza ----------------------------------------------------

def _columnas(encabezados):
    """campo → encabezado original, para las columnas de MAPA presentes en el reporte."""
    presentes = {}
    for encabezado in encabezados:
        campo = MAPA.get(util.clave_encabezado(encabezado))
        if campo is not None and campo not in presentes:
            presentes[campo] = encabezado
    claves = {util.clave_encabezado(e) for e in encabezados}
    for nombre in OBLIGATORIAS:
        if util.clave_encabezado(nombre) not in claves:
            raise ErrorImportacion('Falta la columna obligatoria "%s" en el reporte.' % nombre)
    return presentes


# Centro gestor de cada efector y organización de compras propia, si la tabla config todavía no los tiene.
CENTROS_GESTORES_POR_DEFECTO = {"HBI": ["4500"], "CASPH": ["4900"]}
ORG_COMPRAS_POR_DEFECTO = {"HBI": ["1900"], "CASPH": ["1300"]}
CENTROS_PROPIOS_POR_DEFECTO = {"HBI": ["1900"], "CASPH": ["1300"]}


def _datos_efector(efector, parametros):
    efectores = parametros.get("efectores") or {}
    if efector not in efectores:
        raise ErrorImportacion("Elegí el efector (HBI o CASPH) antes de importar.")
    return efectores[efector] or {}


def centros_gestores(efector, parametros):
    datos = _datos_efector(efector, parametros)
    valores = datos["centros_gestores"] if "centros_gestores" in datos else CENTROS_GESTORES_POR_DEFECTO.get(efector, [])
    return {str(c).strip() for c in valores or [] if str(c).strip()}


def usa_centro_gestor(encabezados):
    return any(util.clave_encabezado(e or "") == "centro gestor" for e in encabezados)


def falta_configuracion(efector, parametros, encabezados):
    """Mensaje si falta configurar con qué se reconoce al efector en este reporte (centro gestor o centro), o None.

    Los reportes por centro gestor (4500 HBI, 4900 CASPH) traen todo lo imputado al efector aunque el renglón tenga otro
    centro (centralizadas con centro 0010, 1000, 1500…); los reportes viejos sin esa columna se filtran por centro.
    """
    if usa_centro_gestor(encabezados):
        if not centros_gestores(efector, parametros):
            return "Configurá el centro gestor de %s antes de importar." % efector
        return None
    if not [c for c in _datos_efector(efector, parametros).get("centros") or [] if str(c).strip()]:
        return "Configurá los centros SAP de %s antes de importar." % efector
    return None


def _limpiar_fila(fila, columnas):
    """Fila del Excel → (datos de OC, datos de renglón) ya limpios."""
    def celda(campo):
        encabezado = columnas.get(campo)
        return fila.get(encabezado) if encabezado is not None else None

    cantidad = _decimal(celda("cantidad"))
    importe_exacto = util.a_decimal(_texto(celda("importe")) or 0, decimales=None)
    importe_centavos = _centavos_de_decimal(importe_exacto)
    if "precio" in columnas and _texto(celda("precio")):
        precio_centavos = util.a_centavos(_texto(celda("precio")))
    elif cantidad != 0:
        precio_centavos = _centavos_de_decimal(importe_exacto / cantidad)
    else:
        precio_centavos = 0
    revisar_importe = 1 if abs(cantidad * precio_centavos - importe_centavos) > 1 else 0

    licitacion = _texto(celda("licitacion"))
    anio_licit = _texto(celda("anio_licit"))
    ca = "%s-%s" % (licitacion, anio_licit) if licitacion and anio_licit else licitacion

    expediente = _texto(celda("expediente_contratacion"))
    vig_desde = _fecha(celda("vig_desde"))
    vig_hasta = _fecha(celda("vig_hasta"))
    fecha_oc = _fecha(celda("fecha_oc"))
    cerrada = 1 if (_texto(celda("entrega_final")).upper() == "X" or _texto(celda("factura_final")).upper() == "X") else 0

    oc = {
        "numero": util.sap_sin_ceros(_texto(celda("oc"))),
        "sap": util.sap_sin_ceros(_texto(celda("sap"))),
        "razon_social": _texto(celda("razon_social")),
        "clase": _texto(celda("clase")),
        "org_compras": _texto(celda("org_compras")),
        "centro": _texto(celda("centro")),
        "ca": ca,
        "expediente_contratacion": util.normalizar_gde(expediente) if expediente else "",
        "fecha_oc": util.iso(fecha_oc) if fecha_oc else None,
        "vig_desde": util.iso(vig_desde) if vig_desde else None,
        "vig_hasta": util.iso(vig_hasta) if vig_hasta else None,
        "cerrada_sap": cerrada,
    }
    renglon = {
        "oc": oc["numero"],
        "pos": int(util.a_decimal(util.sap_sin_ceros(_texto(celda("pos"))) or "0", decimales=0)),
        "codigo": _texto(celda("codigo")),
        "descripcion": _texto(celda("descripcion")),
        "cantidad": _texto_decimal(cantidad),
        "precio_centavos": precio_centavos,
        "importe_centavos": importe_centavos,
        "sap_entregado": _texto_decimal(_decimal(celda("sap_entregado"))),
        "sap_facturado": _texto_decimal(_decimal(celda("sap_facturado"))),
        "sap_por_entregar": _texto_decimal(_decimal(celda("sap_por_entregar"))),
        "revisar_importe": revisar_importe,
        "crudo": {encabezado: valor for encabezado, valor in fila.items()},
    }
    if "partida" in columnas:
        renglon["partida"] = _texto(celda("partida"))
    return oc, renglon


# --- Inferencias: desglose mensual, por entregar, tipo de OC --------------

def anio_final(descripcion):
    """Año con que termina la descripción ("… - 2027", "SERV. ESTERIL. POR ETO 2026") o None."""
    m = RE_ANIO_FINAL.search(descripcion or "")
    return int(m.group(1)) if m is not None else None


def _a_fecha(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, date):
        return valor
    return util.fecha_desde_texto(valor)


def _sumar_meses(fecha, meses):
    total = fecha.year * 12 + (fecha.month - 1) + meses
    anio, mes = divmod(total, 12)
    mes += 1
    ultimo = (date(anio + (mes // 12), mes % 12 + 1, 1) - timedelta(days=1)).day
    return date(anio, mes, min(fecha.day, ultimo))


def meses_entre(desde, hasta):
    """Meses enteros de `desde` a `hasta` + 1 día (2026-04-09..2026-08-08 → 4); None si no es un número entero."""
    desde, hasta = _a_fecha(desde), _a_fecha(hasta)
    if desde is None or hasta is None or hasta < desde:
        return None
    fin = hasta + timedelta(days=1)
    meses = (fin.year - desde.year) * 12 + (fin.month - desde.month)
    if meses >= 1 and _sumar_meses(desde, meses) == fin:
        return Decimal(meses)
    return None


def inferir_desglose(renglon, vig_desde, vig_hasta):
    """Desglose mensual de un servicio cargado como cantidad 1, y por entregar/exceso según SAP.

    Devuelve los campos a guardar: desglose_*, revisar_desglose, sap_por_entregar, exceso_sap.
    """
    cantidad = Decimal(str(renglon.get("cantidad") or "0"))
    entregado = Decimal(str(renglon.get("sap_entregado") or "0"))
    importe = int(renglon.get("importe_centavos") or 0)
    desde, hasta = _a_fecha(vig_desde), _a_fecha(vig_hasta)
    resultado = {
        "desglose_cantidad": None,
        "desglose_unidad": None,
        "desglose_precio_centavos": None,
        "revisar_desglose": 0,
    }

    tramo = None
    if cantidad == 1 and desde is not None and hasta is not None:
        anio = anio_final(renglon.get("descripcion"))
        if anio is not None:
            tramo = (max(desde, date(anio, 1, 1)), min(hasta, date(anio, 12, 31)))
        elif entregado > 1:
            tramo = (desde, hasta)
    if tramo is not None:
        meses = meses_entre(*tramo) if tramo[0] <= tramo[1] else None
        if meses is None or importe % int(meses) != 0:
            resultado["revisar_desglose"] = 1
        else:
            resultado.update({
                "desglose_cantidad": _texto_decimal(meses),
                "desglose_unidad": "MES",
                "desglose_precio_centavos": importe // int(meses),
            })

    base = Decimal(resultado["desglose_cantidad"]) if resultado["desglose_cantidad"] is not None else cantidad
    resultado["sap_por_entregar"] = _texto_decimal(max(Decimal(0), base - entregado))
    resultado["exceso_sap"] = 1 if entregado > base else 0
    return resultado


def _es_servicio(codigo):
    codigo = (codigo or "").strip()
    return codigo == "" or RE_CODIGO_SERVICIO.fullmatch(codigo) is not None


CENTROS_CENTRALES_POR_DEFECTO = ["0010"]  # centro SAP de Nivel Central: sus OC son las centralizadas


def centros_centrales(parametros):
    return {str(c).strip() for c in parametros.get("centros_centrales", CENTROS_CENTRALES_POR_DEFECTO) or []}


def centro_de_fila(renglon):
    """Centro SAP de la fila del reporte que trajo el renglón ("" si no se sabe)."""
    for encabezado, valor in (renglon.get("crudo") or {}).items():
        if util.clave_encabezado(encabezado) == "centro":
            return _texto(valor)
    return ""


def inferir_oc(oc, renglones, parametros):
    """tipo, comodato y centralizada de la OC a partir de sus renglones.

    Centralizada (compra de Nivel Central, «UOC: Nivel Central BS» en el PDF): algún renglón del centro de Nivel Central
    (0010), o comprada por otra organización de compras (0100, 0110…) para entregar en un centro propio del efector
    (1900 HBI, 1300 CASPH). Lo comprado por otra organización para otro centro (farmacia o depósito 1000, 1500, 1700…)
    no es centralizada: queda como «otro centro». Si el reporte no trae el centro, alcanza con la organización.
    """
    efector = oc.get("efector")
    datos = ((parametros.get("efectores") or {}).get(efector) or {}) if efector else {}
    propias = {str(o) for o in parametros.get("org_compras_propias") or []}
    if efector:
        propias |= {str(o) for o in datos.get("org_compras", ORG_COMPRAS_POR_DEFECTO.get(efector, [])) or []}
    org_ajena = (oc.get("org_compras") or "") not in propias
    centros = {centro_de_fila(r) for r in renglones} - {""}
    if centros:
        centros_del_efector = {str(c) for c in datos.get("centros") or []} or set(CENTROS_PROPIOS_POR_DEFECTO.get(efector, []))
        centralizada = 1 if (centros & centros_centrales(parametros)) or (org_ajena and centros & centros_del_efector) else 0
    else:
        centralizada = 1 if org_ajena else 0
    comodato = any("COMODATO" in (r.get("descripcion") or "").upper() for r in renglones)
    if comodato:
        tipo = "PROVISION"
    elif renglones and all(_es_servicio(r.get("codigo")) for r in renglones):
        tipo = "SERVICIO"
    else:
        tipo = "BIEN"
    return {
        "tipo": tipo,
        "comodato": 1 if comodato else 0,
        "centralizada": centralizada,
    }


def dia_inicio_periodo(vig_desde):
    """Día en que arranca cada período: el de inicio de la vigencia (1 = mes calendario).

    Una OC que empieza el 17/07 se valida del 17 al 16 de cada mes. La base admite 1 a 28: si la vigencia arranca
    del 29 al 31 se usa el mes calendario y se corrige a mano si hace falta.
    """
    desde = _a_fecha(vig_desde)
    if desde is None or desde.day > 28:
        return 1
    return desde.day


def _aplicar_inferencias(ocs, renglones, parametros):
    por_oc = {}
    for (numero, _), renglon in renglones.items():
        por_oc.setdefault(numero, []).append(renglon)
    for numero, oc in ocs.items():
        lista = por_oc.get(numero, [])
        oc.update(inferir_oc(oc, lista, parametros))
        oc["dia_inicio_periodo"] = dia_inicio_periodo(oc.get("vig_desde"))
        for renglon in lista:
            renglon.update(inferir_desglose(renglon, oc["vig_desde"], oc["vig_hasta"]))


def _leer(origen, efector, parametros):
    """Lee y limpia el reporte. Devuelve (informe sin comparar con la base, OC por número, renglones por (oc, pos))."""
    _datos_efector(efector, parametros)
    encabezados, filas = xlsx.leer_tabla(origen)
    columnas = _columnas(encabezados)
    falta = falta_configuracion(efector, parametros, encabezados)
    if falta:
        raise ErrorImportacion(falta)
    if "centro_gestor" in columnas:
        campo_filtro, valores_filtro = "centro_gestor", centros_gestores(efector, parametros)
    else:
        campo_filtro = "centro"
        valores_filtro = {str(c) for c in _datos_efector(efector, parametros).get("centros") or []}
    excluidas = {str(p) for p in parametros.get("partidas_excluidas") or []}
    exclusiones = parametros.get("exclusiones") or {}
    sap_excluidos = {util.sap_sin_ceros(str(s)) for s in exclusiones.get("sap") or []}
    oc_excluidas = {util.sap_sin_ceros(str(o)) for o in exclusiones.get("oc") or []}

    informe = {
        "filas": len(filas),
        "descartes": {motivo: 0 for motivo in MOTIVOS_DESCARTE},
        "quedan": 0,
        "oc_distintas": 0,
        "duplicados": 0,
        "altas": 0,
        "actualizadas": 0,
        "sin_cambios": 0,
        "cambios": [],
        "avisos": [],
        "errores": [],
    }
    if "partida" not in columnas:
        informe["avisos"].append(AVISO_SIN_PARTIDA)

    ocs = {}
    renglones = {}
    for indice, fila in enumerate(filas):
        numero_fila = indice + 2  # fila 1 = encabezados
        if not _texto(fila.get(columnas["oc"])):
            informe["descartes"]["sin_oc"] += 1
            continue
        if "partida" in columnas and _texto(fila.get(columnas["partida"])) in excluidas:
            informe["descartes"]["partida"] += 1
            continue
        if _texto(fila.get(columnas[campo_filtro])) not in valores_filtro:
            informe["descartes"]["centro"] += 1
            continue
        oc_txt = util.sap_sin_ceros(_texto(fila.get(columnas["oc"])))
        sap_txt = util.sap_sin_ceros(_texto(fila.get(columnas["sap"])))
        if sap_txt in sap_excluidos or oc_txt in oc_excluidas:
            informe["descartes"]["exclusion_manual"] += 1
            continue
        informe["quedan"] += 1
        try:
            oc, renglon = _limpiar_fila(fila, columnas)
        except (ValueError, ArithmeticError) as error:
            informe["errores"].append({"fila": numero_fila, "oc": oc_txt, "mensaje": "Valor inválido: %s" % error})
            continue
        if oc["vig_desde"] and oc["vig_hasta"] and oc["vig_hasta"] < oc["vig_desde"]:
            informe["errores"].append({
                "fila": numero_fila,
                "oc": oc["numero"],
                "mensaje": "La vigencia termina (%s) antes de empezar (%s)." % (oc["vig_hasta"], oc["vig_desde"]),
            })
            continue
        oc["efector"] = efector
        previa = ocs.get(oc["numero"])
        if previa is not None:
            oc["cerrada_sap"] = max(oc["cerrada_sap"], previa["cerrada_sap"])
        ocs[oc["numero"]] = oc
        clave = (renglon["oc"], renglon["pos"])
        if clave in renglones:
            informe["duplicados"] += 1
        renglones[clave] = renglon
    _aplicar_inferencias(ocs, renglones, parametros)
    informe["oc_distintas"] = len(ocs)
    return informe, ocs, renglones


# --- Comparación con la base y upsert --------------------------------------

def _manuales(fila):
    try:
        return set(json.loads(fila.get("campos_manuales") or "[]"))
    except ValueError:
        return set()


def _normalizar_para_comparar(campo, valor):
    if campo == "crudo" and not isinstance(valor, str):
        return json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return valor


def _diferencias(actual, nuevo, campos):
    """Cambios de `nuevo` contra la fila `actual`, sin tocar los campos manuales."""
    manuales = _manuales(actual)
    cambios = {}
    for campo in campos:
        if campo not in nuevo or campo in manuales:
            continue
        valor = _normalizar_para_comparar(campo, nuevo[campo])
        if actual.get(campo) != valor:
            cambios[campo] = valor
    return cambios


def _por_entregar_con_manuales(actual, renglon, cambios):
    """Si la cantidad o el desglose quedaron fijados a mano (o desde el PDF de la OC), el por entregar y el exceso se
    miden con esos valores y no con el desglose que se infiere del reporte."""
    manuales = _manuales(actual)
    if not manuales & {"cantidad", "desglose_cantidad"}:
        return
    entregado = Decimal(str(renglon.get("sap_entregado", actual.get("sap_entregado")) or "0"))
    desglose = actual.get("desglose_cantidad") if "desglose_cantidad" in manuales else renglon.get("desglose_cantidad")
    cantidad = actual.get("cantidad") if "cantidad" in manuales else renglon.get("cantidad")
    base = Decimal(str(desglose if desglose is not None else (cantidad or "0")))
    nuevos = {"sap_por_entregar": _texto_decimal(max(Decimal(0), base - entregado)), "exceso_sap": 1 if entregado > base else 0}
    for campo, valor in nuevos.items():
        if actual.get(campo) != valor:
            cambios[campo] = valor
        else:
            cambios.pop(campo, None)


def _planificar(con, ocs, renglones, informe):
    """Compara contra la base y devuelve la lista de operaciones; completa altas/actualizadas/cambios del informe."""
    operaciones = []
    proveedores_vistos = set()
    for numero, oc in ocs.items():
        if oc["sap"] not in proveedores_vistos:
            proveedores_vistos.add(oc["sap"])
            if con is None or db.leer_fila(con, "proveedor", {"sap": oc["sap"]}) is None:
                operaciones.append(("alta", "proveedor", {"sap": oc["sap"], "razon_social": oc["razon_social"]}))
        actual = db.leer_fila(con, "oc", {"numero": numero}) if con is not None else None
        if actual is None:
            fila = {campo: oc[campo] for campo in CAMPOS_OC}
            fila["numero"] = numero
            fila["origen"] = "SAP"
            operaciones.append(("alta", "oc", fila))
        else:
            cambios = _diferencias(actual, oc, CAMPOS_OC)
            for campo in CAMPOS_CAMBIO_OC:
                if campo in cambios:
                    informe["cambios"].append({
                        "oc": numero, "pos": None, "campo": campo, "antes": actual.get(campo), "despues": cambios[campo],
                    })
            if cambios:
                operaciones.append(("modificacion", "oc", {"numero": numero}, actual["version"], cambios))

    for (numero, pos), renglon in renglones.items():
        actual = db.leer_fila(con, "renglon", {"oc": numero, "pos": pos}) if con is not None else None
        if actual is None:
            informe["altas"] += 1
            operaciones.append(("alta", "renglon", dict(renglon)))
            continue
        cambios = _diferencias(actual, renglon, CAMPOS_RENGLON)
        _por_entregar_con_manuales(actual, renglon, cambios)
        if not cambios:
            informe["sin_cambios"] += 1
            continue
        informe["actualizadas"] += 1
        for campo in CAMPOS_CAMBIO_RENGLON:
            if campo in cambios:
                informe["cambios"].append({
                    "oc": numero, "pos": pos, "campo": campo, "antes": actual.get(campo), "despues": cambios[campo],
                })
        operaciones.append(("modificacion", "renglon", {"oc": numero, "pos": pos}, actual["version"], cambios))
    return operaciones


def analizar(origen, efector, parametros, con=None):
    """Vista previa: lee, limpia y (si hay conexión) compara con la base. No escribe nada."""
    informe, ocs, renglones = _leer(origen, efector, parametros)
    _planificar(con, ocs, renglones, informe)
    return informe


def importar(con, origen, efector, parametros, archivo=""):
    """Importa el reporte (upsert) en una sola transacción y guarda el informe en `importacion`."""
    informe, ocs, renglones = _leer(origen, efector, parametros)
    ahora = db.ahora_utc()
    with db.transaccion(con):
        operaciones = _planificar(con, ocs, renglones, informe)
        for operacion in operaciones:
            if operacion[0] == "alta":
                _, tabla, fila = operacion
                if tabla == "oc":
                    fila = dict(fila, ultima_importacion=ahora)
                db.insertar(con, tabla, fila)
            else:
                _, tabla, clave, version, cambios = operacion
                if tabla == "oc":
                    cambios = dict(cambios, ultima_importacion=ahora)
                db.actualizar_con_version(con, tabla, clave, version, cambios)
        usuario = getpass.getuser()
        cursor = con.execute(
            "INSERT INTO importacion (fecha, archivo, efector, usuario, informe) VALUES (?, ?, ?, ?, ?)",
            (ahora, archivo, efector, usuario, json.dumps(informe, ensure_ascii=False, sort_keys=True)),
        )
        db.registrar_evento(
            con, "IMPORTACION", "importacion", {"id": cursor.lastrowid}, None,
            {"archivo": archivo, "efector": efector, "altas": informe["altas"], "actualizadas": informe["actualizadas"]},
        )
    return informe
