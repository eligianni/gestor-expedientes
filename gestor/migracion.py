"""Migración del seguimiento en Excel al gestor: NUMERACIÓN (una hoja por entrega) + solapa de remitos de HBI.

- La NUMERACIÓN es la fuente principal: cada fila con N° de factura es un expediente ya enviado, con su entrega,
  período, factura, importe, código del SII, EX y números GDE. Con fecha o constancia de contabilización queda
  CERRADO (FINALIZADO si es pago eventual); la hoja de pendientes queda PENDIENTE; el resto, ENVIADO.
- La solapa de remitos (una fila por remito) aporta la lista de remitos de cada expediente, cruzando por N° de factura
  (y, si la factura no coincide, por N° de remito). Los remitos de 2026 que todavía no salieron en ninguna entrega se
  agrupan por OC y factura (o período) y quedan como expedientes en BORRADOR.
- Las cantidades por renglón no están en las planillas: se deducen solo cuando la OC tiene un renglón y el importe
  dividido por su precio (o por el precio del desglose) da exacto.
- Es idempotente: un expediente con la misma factura y el mismo proveedor ya cargado no se vuelve a crear.

Todas las columnas se buscan por NOMBRE normalizado (util.clave_encabezado), nunca por posición.
"""
import getpass
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from gestor import db, negocio, util, xlsx

HOJA_REMITOS = "hbi 20252026"
ANIO_DESDE = "2026"
FUENTE = "migracion_seguimiento"

_RE_ENTREGA = re.compile(r"^entrega\s+(\d+)\b")
_RE_REMITO = re.compile(r"(\d{1,5})\s*-\s*(\d{4,9})")
# Hojas de la NUMERACIÓN que no se importan: copias con el número entre paréntesis, como "ENTREGA (2)" (borrador de la
# ENTREGA 11). Se compara el nombre tal cual (con paréntesis), no la clave normalizada.
_RE_HOJA_COPIA = re.compile(r"^\s*entrega\s*\(\d+\)\s*$", re.IGNORECASE)

# Columnas de números GDE: palabra clave del encabezado → clave de datos.gde. Se toma la primera columna cuyo valor
# es un número GDE válido (las columnas de "nombre de archivo" tienen el mismo encabezado pero no son números GDE).
_GDE_POR_ENCABEZADO = (
    ("const", "contabilizacion"),
    ("comprobante de carga en sii", "sii"),
    ("carga en sii", "sii"),
    ("orden de compra", "oc_pdf"),
    ("vale", "vale_hoja"),
    ("autorizacion", "autorizacion"),
    ("cv", "cv"),
    ("remito", "remito"),
    ("factura", "factura"),
)


class ErrorMigracion(Exception):
    """Las planillas no se pueden migrar (archivo equivocado, falta la hoja, etc.)."""


# --- Conversión de celdas ------------------------------------------------------

def _texto(valor):
    return "" if valor is None else re.sub(r"\s+", " ", str(valor)).strip()


def _clave(texto):
    return util.clave_encabezado(texto or "")


def _serial_a_fecha(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return util.fecha_desde_serial_excel(int(Decimal(texto)))
    except (InvalidOperation, ValueError, OverflowError):
        pass
    try:
        return util.fecha_desde_texto(texto.replace(".", "/"))
    except (ValueError, TypeError):
        return None


def _periodo(valor):
    fecha = _serial_a_fecha(valor)
    return fecha.strftime("%Y-%m") if fecha is not None else None


def _fecha_iso(valor):
    fecha = _serial_a_fecha(valor)
    return util.iso(fecha) if fecha is not None else None


def _numero_entero(valor):
    texto = _texto(valor)
    if not texto:
        return ""
    try:
        return str(int(Decimal(texto)))
    except InvalidOperation:
        return util.sap_sin_ceros(texto)


def _centavos(valor):
    texto = _texto(valor).replace("$", "").strip()
    if not texto:
        return None
    try:
        return util.a_centavos(texto)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _factura(valor):
    """Número de factura normalizado ("0003B00031812") o "" si no es una factura (vacío, PENDIENTE, etc.)."""
    texto = _texto(valor).replace("\t", "")
    if not texto:
        return ""
    try:
        return negocio.numero_factura_normalizado(texto)
    except negocio.ErrorValidacion:
        return ""


def _clave_factura(numero):
    try:
        pv, _, nro = util.normalizar_factura(numero)
    except ValueError:
        return None
    return pv, nro


def _remitos_de_texto(texto):
    """"0001-00007852/74" → ["0001-00007852/74"]; "A y B" → ["A", "B"]; "466 al 474" → ["466 al 474"]."""
    texto = _texto(texto)
    if not texto or _clave(texto) in ("pendiente", "referencias", "exptes completos"):
        return []
    partes = [p.strip(" ,;") for p in re.split(r"\s+(?:y|-\s)\s*|\s*;\s*|\s*,\s*|\s+/\s+", texto) if p.strip(" ,;")]
    return partes or [texto]


def _claves_remito(texto):
    """Claves (punto de venta, número) de los remitos mencionados en el texto, para cruzar."""
    return {(int(a), int(b)) for a, b in _RE_REMITO.findall(_texto(texto))}


def _gde(valor):
    texto = _texto(valor)
    if not texto:
        return ""
    normalizado = util.normalizar_gde(texto)
    return normalizado if util.validar_gde(normalizado) else ""


# --- Lectura de las planillas ----------------------------------------------------

def _fila_encabezados(filas):
    for i, fila in enumerate(filas[:10]):
        claves = {_clave(x) for x in fila if x}
        if "n factura" in claves and ("periodo" in claves or "oc" in claves or "proveedor" in claves):
            return i
    return None


def _registros(filas, indice):
    """Filas debajo del encabezado como lista de (n° de fila Excel, {clave: primer valor}, [(clave, valor), ...])."""
    encabezados = [_clave(x) for x in filas[indice]]
    registros = []
    for n, fila in enumerate(filas[indice + 1:], start=indice + 2):
        if not any(_texto(x) for x in fila):
            continue
        primero, todos = {}, []
        for i, valor in enumerate(fila):
            clave = encabezados[i] if i < len(encabezados) else ""
            if not clave:
                continue
            todos.append((clave, valor))
            if clave not in primero:
                primero[clave] = valor
        registros.append((n, primero, todos))
    return registros


def _primero(fila, *claves):
    for clave in claves:
        valor = _texto(fila.get(clave))
        if valor:
            return valor
    return ""


def _gde_de_fila(todos):
    """Números GDE de la fila por encabezado; el EX va aparte."""
    gde = {"remitos_rm": ""}
    expediente = ""
    for clave, valor in todos:
        numero = _gde(valor)
        if not numero:
            continue
        if numero.startswith("EX-"):
            expediente = expediente or numero
            continue
        for palabra, destino in _GDE_POR_ENCABEZADO:
            if clave.startswith(palabra) or palabra in clave:
                if destino == "remito":
                    gde["remitos_rm"] = gde["remitos_rm"] or numero
                elif not gde.get(destino):
                    gde[destino] = numero
                break
    gde["expediente"] = expediente
    return gde


def _tipo_de_hoja(nombre):
    clave = _clave(nombre)
    if "correctivo" in clave:
        return "CORRECTIVO"
    if "eventual" in clave:
        return "EVENTUAL"
    return None


def leer_numeracion(hojas):
    """Expedientes de la NUMERACIÓN: lista de dicts con los datos de cada fila con factura."""
    expedientes, ignoradas = [], []
    for nombre, filas in hojas:
        clave_hoja = _clave(nombre)
        if _RE_HOJA_COPIA.match(nombre or ""):
            ignoradas.append(nombre)
            continue
        indice = _fila_encabezados(filas)
        if indice is None:
            ignoradas.append(nombre)
            continue
        m = _RE_ENTREGA.match(clave_hoja)
        for n, fila, todos in _registros(filas, indice):
            factura = _factura(fila.get("n factura"))
            if not factura:
                continue
            gde = _gde_de_fila(todos)
            remito_texto = _primero(fila, "n remito") or (_texto(fila.get("remito")) if not _gde(fila.get("remito")) else "")
            expedientes.append({
                "hoja": nombre, "fila": n, "entrega": int(m.group(1)) if m else None,
                "pendiente": clave_hoja.startswith("pendiente"), "tipo_hoja": _tipo_de_hoja(nombre),
                "oc": _numero_entero(fila.get("oc")), "sap": _numero_entero(fila.get("sap")),
                "proveedor": _texto(fila.get("proveedor")), "concepto": _primero(fila, "concepto", "motivo"),
                "periodo": _periodo(fila.get("periodo")), "factura": factura,
                "fecha_factura": _fecha_iso(fila.get("fecha doc") or fila.get("fecha factura fecha doc")),
                "fecha_contab": _fecha_iso(fila.get("fecha contab") or fila.get("fecha contabilizacion")),
                "centavos": _centavos(fila.get("importe")),
                "sii": _texto(fila.get("carga en sii")) if not _gde(fila.get("carga en sii")) else "",
                "remito_texto": remito_texto, "gde": gde,
                "observaciones": _primero(fila, "observaciones", "aclaraciones"),
            })
    return expedientes, ignoradas


def leer_remitos(hojas):
    """Filas de la solapa HBI 20252026: un remito por fila."""
    for nombre, filas in hojas:
        if _clave(nombre) != HOJA_REMITOS:
            continue
        indice = _fila_encabezados(filas)
        if indice is None:
            raise ErrorMigracion("La solapa %s no tiene la fila de encabezados (OC, REMITO, PERIODO, N° FACTURA)." % nombre)
        remitos = []
        for n, fila, _ in _registros(filas, indice):
            numero = _texto(fila.get("remito"))
            if not numero:
                continue
            remitos.append({
                "fila": n, "oc": _numero_entero(fila.get("oc")) if _texto(fila.get("oc")).upper() != "SIN OC" else "",
                "sap": _numero_entero(fila.get("sap")), "proveedor": _texto(fila.get("proveedor")), "remito": numero,
                "periodo": _periodo(fila.get("periodo")), "factura": _factura(fila.get("n factura")),
                "factura_texto": _texto(fila.get("n factura")), "sii": _texto(fila.get("carga en sii")),
                "centavos": _centavos(fila.get("importe")), "entrega": _texto(fila.get("n entrega")),
                "observaciones": _texto(fila.get("observaciones")),
            })
        return remitos
    raise ErrorMigracion("El archivo de seguimiento de remitos no tiene la solapa «HBI 20252026».")


# --- Armado del plan -----------------------------------------------------------------

def _cantidad_texto(numero):
    texto = format(numero, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto


def deducir_items(renglones, centavos):
    """[{pos, cantidad}] si la OC tiene un solo renglón y el importe dividido por su precio da exacto; si no, []."""
    validos = [r for r in renglones if not r.get("es_correctivo")]
    if len(validos) != 1 or not centavos:
        return []
    r = validos[0]
    precio = r.get("desglose_precio_centavos") if r.get("desglose_cantidad") not in (None, "") else r.get("precio_centavos")
    if not precio:
        return []
    cantidad = (Decimal(centavos) / Decimal(precio)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if cantidad <= 0 or int((cantidad * precio).to_integral_value(rounding=ROUND_HALF_UP)) != centavos:
        return []
    return [{"pos": r["pos"], "cantidad": _cantidad_texto(cantidad), "codigo": r.get("codigo") or ""}]


def _remito(numero, items=()):
    return {"numero": numero, "fecha": None, "fecha_firma": None, "es_equipo_comodato": False, "aclara_periodo": False,
            "items": list(items)}


def _estado(exp):
    if exp["pendiente"]:
        return "PENDIENTE"
    if exp["fecha_contab"] or exp["gde"].get("contabilizacion"):
        return "FINALIZADO" if exp["tipo"] == "EVENTUAL" else "CERRADO"
    return "DEVUELTO" if exp["tipo"] == "EVENTUAL" else "ENVIADO"


def _ya_existe(con, factura, sap):
    fila = con.execute(
        "SELECT id FROM expediente WHERE factura = ? AND sap = ? AND estado <> 'ANULADO' LIMIT 1", (factura, sap),
    ).fetchone()
    return fila["id"] if fila is not None else None


def _ya_existe_borrador(con, oc, periodo):
    """Expediente sin factura de la misma OC y período (un borrador migrado antes)."""
    fila = con.execute(
        "SELECT id FROM expediente WHERE oc = ? AND periodo = ? AND factura = '' AND estado <> 'ANULADO' LIMIT 1", (oc, periodo),
    ).fetchone()
    return fila["id"] if fila is not None else None


def planificar(con, hojas_numeracion, hojas_remitos):
    """Plan de la migración (sin escribir nada): expedientes a crear, entregas, lo que no se importa y por qué."""
    numeracion, ignoradas = leer_numeracion(hojas_numeracion)
    if not numeracion:
        raise ErrorMigracion("No se encontraron expedientes en la NUMERACIÓN: falta la columna N° FACTURA o está vacía.")
    remitos = leer_remitos(hojas_remitos)

    ocs = {f["numero"]: dict(f) for f in con.execute("SELECT * FROM oc")}
    renglones = {}
    for f in con.execute("SELECT * FROM renglon ORDER BY oc, pos"):
        renglones.setdefault(f["oc"], []).append(dict(f))
    proveedores = {f["sap"]: f["razon_social"] for f in con.execute("SELECT sap, razon_social FROM proveedor")}
    sap_por_nombre = {}
    for sap, razon in proveedores.items():
        sap_por_nombre.setdefault(_clave(razon), sap)

    informe = {"expedientes": [], "no_importados": [], "avisos": [], "hojas_ignoradas": ignoradas, "entregas": []}
    por_factura, por_remito, vistos = {}, {}, set()

    def no_importado(origen, fila, detalle, motivo):
        informe["no_importados"].append({"origen": origen, "fila": fila, "detalle": detalle, "motivo": motivo})

    # 1) Expedientes de la NUMERACIÓN.
    for e in numeracion:
        clave_fc = _clave_factura(e["factura"])
        detalle = "%s · FC %s · %s" % (e["oc"] or "sin OC", e["factura"], e["proveedor"])
        if (clave_fc, e["sap"]) in vistos:
            no_importado(e["hoja"], e["fila"], detalle, "Factura repetida en la NUMERACIÓN: se toma la primera.")
            continue
        vistos.add((clave_fc, e["sap"]))
        tipo = e["tipo_hoja"]
        oc = ocs.get(e["oc"]) if e["oc"] else None
        if tipo != "EVENTUAL":
            if oc is None:
                no_importado(e["hoja"], e["fila"], detalle, "La OC %s no está en el gestor: importá antes el z_compras2 (o cargala)."
                             % (e["oc"] or "(vacía)"))
                continue
            tipo = tipo or ("CENTRALIZADA" if oc["centralizada"] else "COMUN")
        sap = oc["sap"] if oc is not None else (e["sap"] or sap_por_nombre.get(_clave(e["proveedor"]), ""))
        if not sap:
            no_importado(e["hoja"], e["fila"], detalle,
                         "Falta el SAP del proveedor y «%s» no está en el gestor con ese nombre." % e["proveedor"])
            continue
        if not e["periodo"]:
            no_importado(e["hoja"], e["fila"], detalle, "Falta el período.")
            continue
        e["tipo"] = tipo
        plan = {
            "origen": "%s, fila %d" % (e["hoja"], e["fila"]), "hoja": e["hoja"], "entrega": e["entrega"],
            "tipo": tipo, "efector": oc["efector"] if oc is not None else "HBI", "oc": oc["numero"] if oc else None,
            "sap": sap, "razon_social": proveedores.get(sap) or e["proveedor"], "periodo": e["periodo"],
            "factura": e["factura"], "fecha_factura": e["fecha_factura"], "centavos": e["centavos"], "sii": e["sii"],
            "estado": _estado(e), "gde": e["gde"], "remitos": [], "remito_texto": e["remito_texto"],
            "motivo_pendiente": e["observaciones"] if e["pendiente"] else "", "concepto": e["concepto"],
            "avisos": [], "ya_existe": _ya_existe(con, e["factura"], sap),
        }
        informe["expedientes"].append(plan)
        por_factura[(clave_fc, sap)] = plan
        por_factura.setdefault((clave_fc, None), plan)
        for clave_rm in _claves_remito(e["remito_texto"]):
            por_remito.setdefault((sap, clave_rm), plan)

    # 2) Remitos de la solapa HBI: se cuelgan de su expediente; los de 2026 sin entrega forman borradores.
    borradores = {}
    for r in remitos:
        clave_fc = _clave_factura(r["factura"]) if r["factura"] else None
        plan = por_factura.get((clave_fc, r["sap"])) or por_factura.get((clave_fc, None)) if clave_fc else None
        if plan is None:
            for clave_rm in _claves_remito(r["remito"]):
                plan = por_remito.get((r["sap"], clave_rm))
                if plan is not None:
                    plan["avisos"].append("El remito %s se cruzó por número: en la solapa de remitos figura con la factura %s."
                                          % (r["remito"], r["factura_texto"] or "(vacía)"))
                    break
        if plan is not None:
            if r["remito"] not in plan["remitos"]:
                plan["remitos"].append(r["remito"])
            continue
        detalle = "%s · RTO %s · %s" % (r["oc"] or "sin OC", r["remito"], r["proveedor"])
        if not r["periodo"] or r["periodo"] < ANIO_DESDE:
            no_importado("HBI 20252026", r["fila"], detalle,
                         "Remito de %s que no está en esta NUMERACIÓN (entrega de otro año)." % (r["periodo"] or "período vacío"))
            continue
        oc = ocs.get(r["oc"]) if r["oc"] else None
        if oc is None:
            no_importado("HBI 20252026", r["fila"], detalle,
                         "Sin OC en el gestor (%s): cargalo a mano." % (r["oc"] or "la fila dice SIN OC"))
            continue
        clave = (oc["numero"], r["factura"] or r["periodo"])
        plan = borradores.get(clave)
        if plan is None:
            plan = {
                "origen": "HBI 20252026, fila %d" % r["fila"], "hoja": "HBI 20252026", "entrega": None,
                "tipo": "CENTRALIZADA" if oc["centralizada"] else "COMUN", "efector": oc["efector"], "oc": oc["numero"],
                "sap": oc["sap"], "razon_social": proveedores.get(oc["sap"]) or r["proveedor"], "periodo": r["periodo"],
                "factura": r["factura"], "fecha_factura": None, "centavos": r["centavos"],
                "sii": r["sii"] if r["sii"] not in ("-", "") else "", "estado": "BORRADOR", "gde": {"expediente": ""},
                "remitos": [], "remito_texto": "", "motivo_pendiente": "", "concepto": "",
                "avisos": ["Todavía no salió en ninguna entrega: queda en Borrador para validarlo en el gestor."],
                "ya_existe": (_ya_existe(con, r["factura"], oc["sap"]) if r["factura"]
                              else _ya_existe_borrador(con, oc["numero"], r["periodo"])),
            }
            if r["observaciones"]:
                plan["avisos"].append("Observación de la planilla: %s" % r["observaciones"])
            borradores[clave] = plan
            informe["expedientes"].append(plan)
        plan["remitos"].append(r["remito"])

    # 3) Remitos de la NUMERACIÓN cuando la solapa no los tenía; cantidades deducidas.
    for plan in informe["expedientes"]:
        if not plan["remitos"]:
            plan["remitos"] = _remitos_de_texto(plan["remito_texto"])
            if not plan["remitos"] and plan["tipo"] not in ("EVENTUAL", "CORRECTIVO"):
                plan["avisos"].append("No se encontró el remito ni en la NUMERACIÓN ni en la solapa de remitos.")
        items = deducir_items(renglones.get(plan["oc"], []), plan["centavos"]) if plan["oc"] else []
        plan["items"] = items
        if plan["oc"] and not items and plan["tipo"] not in ("EVENTUAL", "CORRECTIVO"):
            plan["avisos"].append("Sin cantidades por renglón: no se pudo deducir del importe (cargá el consumo previo si hace falta).")

    # 4) Entregas.
    existentes = {(f["efector"], f["numero"]): dict(f) for f in con.execute("SELECT * FROM entrega")}
    numeros = sorted({p["entrega"] for p in informe["expedientes"] if p["entrega"] is not None})
    for numero in numeros:
        actual = existentes.get(("HBI", numero))
        informe["entregas"].append({"efector": "HBI", "numero": numero, "existe": actual is not None,
                                    "expedientes": sum(1 for p in informe["expedientes"] if p["entrega"] == numero)})
    for plan in informe["expedientes"]:
        if plan["entrega"] is not None and plan["efector"] != "HBI":
            plan["avisos"].append("La OC es de %s y la entrega %d es de HBI: se importa sin entrega." % (plan["efector"], plan["entrega"]))
            plan["entrega"] = None

    a_crear = [p for p in informe["expedientes"] if not p["ya_existe"]]
    por_estado = {}
    for p in a_crear:
        por_estado[p["estado"]] = por_estado.get(p["estado"], 0) + 1
    informe["resumen"] = {
        "expedientes": len(a_crear), "ya_existentes": len(informe["expedientes"]) - len(a_crear), "por_estado": por_estado,
        "remitos": sum(len(p["remitos"]) for p in a_crear), "con_cantidades": sum(1 for p in a_crear if p["items"]),
        "entregas_nuevas": sum(1 for e in informe["entregas"] if not e["existe"]),
        "no_importados": len(informe["no_importados"]),
    }
    return informe


# --- Escritura -------------------------------------------------------------------------

def _datos_expediente(plan, hoja_origen):
    gde = plan["gde"]
    remitos = []
    for i, numero in enumerate(plan["remitos"]):
        remitos.append(_remito(numero, plan["items"] if i == 0 else ()))
    datos = {
        "remitos": remitos,
        "factura": {"numero": plan["factura"], "fecha": plan["fecha_factura"], "centavos": plan["centavos"],
                    "cae": None, "vto_cae": None} if plan["factura"] else {},
        "sii": {"cod_tramite": plan["sii"]} if plan["sii"] else {},
        "gde": {},
        "sap": {}, "notas_aclaratorias": [], "checklist": {}, "correctivo": {}, "eventual": {}, "centralizada": {},
        "historial": [{"fecha": db.ahora_utc(), "usuario": getpass.getuser(), "accion": "MIGRACION",
                       "estado": plan["estado"], "origen": hoja_origen}],
    }
    if any(v for k, v in gde.items() if k != "remitos_rm"):
        limpio = {clave: gde.get(clave) or "" for clave in negocio.CLAVES_GDE if clave not in ("remitos", "orden_remito_equipo")}
        limpio["remitos"] = {numero: gde["remitos_rm"] for numero in plan["remitos"]} if gde.get("remitos_rm") else {}
        limpio["orden_remito_equipo"] = None
        datos["gde"] = limpio
    if plan["tipo"] == "CORRECTIVO" and plan["concepto"]:
        datos["correctivo"] = {"objeto_correctivo": plan["concepto"]}
    return datos


def migrar(con, hojas_numeracion, hojas_remitos, archivos=""):
    """Planifica y escribe en una sola transacción: entregas, proveedores faltantes y expedientes. Devuelve el informe."""
    informe = planificar(con, hojas_numeracion, hojas_remitos)
    ahora = db.ahora_utc()
    usuario = getpass.getuser()
    creados = 0
    with db.transaccion(con):
        entregas = {}
        for e in informe["entregas"]:
            fila = db.leer_fila(con, "entrega", {"efector": e["efector"], "numero": e["numero"]})
            if fila is None:
                nuevo = db.insertar(con, "entrega", {"efector": e["efector"], "numero": e["numero"],
                                                     "nombre": "Entrega %d (migrada)" % e["numero"], "estado": "ENVIADA",
                                                     "observaciones": "Migrada de la NUMERACIÓN 2026."})
                entregas[e["numero"]] = nuevo
            else:
                entregas[e["numero"]] = fila["id"]
        for plan in informe["expedientes"]:
            if plan["ya_existe"]:
                continue
            if db.leer_fila(con, "proveedor", {"sap": plan["sap"]}) is None:
                db.insertar(con, "proveedor", {"sap": plan["sap"], "razon_social": plan["razon_social"] or plan["sap"]})
            dia_inicio = 1
            if plan["oc"]:
                oc = db.leer_fila(con, "oc", {"numero": plan["oc"]})
                dia_inicio = int(oc["dia_inicio_periodo"] or 1)
            limites = negocio.limites_de_periodo(plan["periodo"], dia_inicio)
            fila = {
                "tipo": plan["tipo"], "efector": plan["efector"], "oc": plan["oc"], "sap": plan["sap"],
                "periodo": plan["periodo"], "periodo_desde": util.iso(limites.desde), "periodo_hasta": util.iso(limites.hasta),
                "periodo_manual": 1, "factura": plan["factura"], "estado": plan["estado"],
                "motivo_pendiente": plan["motivo_pendiente"] or ("Migrado como pendiente." if plan["estado"] == "PENDIENTE" else ""),
                "entrega_id": entregas.get(plan["entrega"]), "datos": _datos_expediente(plan, plan["origen"]),
                "creado": ahora, "actualizado": ahora, "usuario": usuario,
            }
            db.insertar(con, "expediente", fila)
            creados += 1
        informe["resumen"]["creados"] = creados
        db.insertar(con, "importacion", {
            "fecha": ahora, "archivo": archivos or "migración de seguimiento", "efector": "HBI", "usuario": usuario,
            "informe": {"fuente": FUENTE, "resumen": informe["resumen"]},
        })
        db.registrar_evento(con, "IMPORTACION", "expediente", {"fuente": FUENTE}, None,
                            {"archivos": archivos, "resumen": informe["resumen"]})
    return informe


def leer_archivos(numeracion, remitos):
    """(hojas de la NUMERACIÓN, hojas del seguimiento de remitos) desde bytes o rutas."""
    try:
        return xlsx.leer_hojas(numeracion), xlsx.leer_hojas(remitos)
    except xlsx.XlsxError as error:
        raise ErrorMigracion(str(error)) from None
