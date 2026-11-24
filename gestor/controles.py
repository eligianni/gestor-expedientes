"""Controles del expediente: cuatro niveles (error, salvable, aviso, verificar).

Los controles NO leen la base: cada `control_<codigo>(ctx)` recibe el contexto que arma `armar_contexto` y devuelve
una lista de `Resultado`. El contexto lo arma `gestor.negocio` (dueño de las lecturas), que registra su armador con
`registrar_armador` al importarse; así este módulo solo depende de `util` y `letras`.
"""
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple, Optional

from gestor import util

NIVELES = ("error", "salvable", "aviso", "verificar")

# Estados desde los que una OC ya tuvo su "primera validación".
ESTADOS_VALIDADOS = ("CONTROLADO", "EN_FIRMA", "FIRMADO", "ENVIADO", "CONTABILIZADO", "CERRADO")

_RE_REMITO = re.compile(r"\d{4,5}-\d{8}")


class Resultado(NamedTuple):
    codigo: str
    nivel: str
    ambito: str
    mensaje: str
    referencia: Optional[str] = None


# --- Contexto ----------------------------------------------------------------

_armador = None


def registrar_armador(funcion):
    """`gestor.negocio` registra acá la función que lee la base y arma el contexto."""
    global _armador
    _armador = funcion


def armar_contexto(con, expediente_id):
    """Contexto del expediente: expediente, oc, proveedor, renglones, consumo, parametros y otros expedientes."""
    if _armador is None:
        raise RuntimeError("No hay armador de contexto registrado (falta importar gestor.negocio).")
    return _armador(con, expediente_id)


# --- Ayudas puras --------------------------------------------------------------

def _pesos(centavos):
    return "$ " + util.formato_pesos(centavos)


def _datos(ctx):
    return ctx["expediente"].get("datos") or {}


def _factura(ctx):
    return _datos(ctx).get("factura") or {}


def _sii(ctx):
    return _datos(ctx).get("sii") or {}


def _remitos(ctx):
    return _datos(ctx).get("remitos") or []


def _remitos_de_consumo(ctx):
    return [r for r in _remitos(ctx) if not r.get("es_equipo_comodato")]


def _decimal(valor):
    if valor in (None, ""):
        return Decimal(0)
    try:
        return util.a_decimal(valor if isinstance(valor, (int, Decimal)) else str(valor), decimales=None)
    except (TypeError, ValueError):
        return Decimal(0)


def _cantidades(ctx):
    """{pos: Decimal} de los ítems de remitos que no son del equipo."""
    cantidades = {}
    for remito in _remitos_de_consumo(ctx):
        for item in remito.get("items") or []:
            try:
                pos = int(item.get("pos"))
            except (TypeError, ValueError):
                continue
            cantidades[pos] = cantidades.get(pos, Decimal(0)) + _decimal(item.get("cantidad"))
    return cantidades


def _renglones(ctx):
    return {int(r["pos"]): r for r in ctx.get("renglones") or []}


def _fecha_base(remito):
    return remito.get("fecha_firma") or remito.get("fecha")


def _limites(ctx):
    exp = ctx["expediente"]
    if not exp.get("periodo_desde") or not exp.get("periodo_hasta"):
        return None
    return util.fecha_desde_texto(exp["periodo_desde"]), util.fecha_desde_texto(exp["periodo_hasta"])


def _texto_igual(a, b):
    return util.normalizar_texto(a or "") == util.normalizar_texto(b or "")


def _cantidad_texto(numero):
    return "0" if numero == 0 else format(numero.normalize(), "f")


# --- Factura -------------------------------------------------------------------

def control_importe_factura(ctx):
    factura = _factura(ctx)
    cantidades = _cantidades(ctx)
    if not cantidades or factura.get("centavos") in (None, ""):
        return []
    renglones = _renglones(ctx)
    esperado = Decimal(0)
    for pos, cantidad in cantidades.items():
        r = renglones.get(pos)
        if r is None:
            continue
        precio = r["desglose_precio_centavos"] if r.get("desglose_cantidad") not in (None, "") else r["precio_centavos"]
        esperado += cantidad * Decimal(int(precio or 0))
    centavos = int(factura["centavos"])
    if Decimal(centavos) == esperado:
        return []
    redondeado = int(esperado.to_integral_value(rounding=ROUND_HALF_UP))
    return [Resultado(
        "importe_factura", "error", "factura",
        "El importe de la factura (%s) no coincide con cantidad × precio (%s)." % (_pesos(centavos), _pesos(redondeado)),
    )]


def control_destinatario_factura(ctx):
    factura = _factura(ctx)
    esperado = (ctx["parametros"].get("destinatario_factura") or {}).get("nombre", "INSSJP")
    destinatario = " ".join(str(factura.get("destinatario") or "").upper().split())
    if destinatario == esperado.upper():
        return []
    if not destinatario:
        mensaje = "Falta el destinatario de la factura (debe ser %s)." % esperado
    else:
        mensaje = "La factura está dirigida a %s; debe ser %s." % (destinatario, esperado)
    return [Resultado("destinatario_factura", "error", "factura", mensaje)]


def control_domicilio_factura(ctx):
    domicilio = util.normalizar_domicilio(_factura(ctx).get("domicilio"))
    esperado = util.normalizar_domicilio((ctx["parametros"].get("destinatario_factura") or {}).get("domicilio", "PERU 169"))
    if domicilio.startswith(esperado) and domicilio:
        return []
    if not domicilio:
        mensaje = "Falta el domicilio del destinatario en la factura (debe ser %s)." % esperado
    else:
        mensaje = "El domicilio de la factura (%s) no es %s." % (domicilio, esperado)
    return [Resultado("domicilio_factura", "error", "factura", mensaje)]


def control_periodo_factura(ctx):
    factura = _factura(ctx)
    desde, hasta = factura.get("periodo_desde"), factura.get("periodo_hasta")
    limites = _limites(ctx)
    if not desde or not hasta or limites is None:
        return []
    f_desde, f_hasta = util.fecha_desde_texto(desde), util.fecha_desde_texto(hasta)
    if limites[0] <= f_desde and f_hasta <= limites[1]:
        return []
    return [Resultado(
        "periodo_factura", "salvable", "factura",
        "La factura indica el período %s al %s, fuera del período validado %s."
        % (util.ddmmaaaa(f_desde), util.ddmmaaaa(f_hasta), ctx["expediente"]["periodo"]),
    )]


def _menciones_reales(ctx):
    gde = _datos(ctx).get("gde") or {}
    return {
        "oc": [ctx["oc"]["numero"]] if ctx.get("oc") else [],
        "expediente": [util.normalizar_gde(gde["expediente"])] if gde.get("expediente") else [],
        "remito": [r.get("numero") for r in _remitos(ctx) if r.get("numero")],
    }


def control_menciones_factura(ctx):
    menciona = _factura(ctx).get("menciona") or {}
    if not isinstance(menciona, dict):
        return []
    reales = _menciones_reales(ctx)
    resultados = []
    for clave in ("oc", "expediente", "remito"):
        valor = menciona.get(clave)
        if not valor:
            continue
        reales_clave = reales[clave]
        if clave == "expediente":
            coincide = util.normalizar_gde(valor) in reales_clave
        elif clave == "oc":
            coincide = util.sap_sin_ceros(valor) in [util.sap_sin_ceros(v) for v in reales_clave]
        else:
            coincide = str(valor).strip() in reales_clave
        if not coincide:
            real = ", ".join(reales_clave) or "(sin cargar)"
            resultados.append(Resultado(
                "menciones_factura", "salvable", "factura",
                "La factura menciona %s %s; el dato real es %s." % (
                    {"oc": "la OC", "expediente": "el expediente", "remito": "el remito"}[clave], valor, real),
                clave,
            ))
    return resultados


def control_formato_factura(ctx):
    factura = _factura(ctx)
    resultados = []
    numero = factura.get("numero")
    if not numero:
        resultados.append(Resultado("formato_factura", "error", "factura", "Falta el número de la factura."))
    else:
        try:
            util.normalizar_factura(numero)
        except ValueError:
            resultados.append(Resultado(
                "formato_factura", "error", "factura", "El número de factura %s no es válido." % numero))
    cae = factura.get("cae")
    if not cae or not re.fullmatch(r"\d{14}", str(cae).strip()):
        resultados.append(Resultado(
            "formato_factura", "error", "factura",
            "El CAE de la factura debe tener 14 dígitos." if cae else "Falta el CAE de la factura.",
        ))
    return resultados


def control_vencimiento_cae(ctx):
    factura = _factura(ctx)
    if not factura.get("vto_cae"):
        return [Resultado("vencimiento_cae", "verificar", "factura",
                          "La factura no tiene vencimiento del CAE cargado: verificalo a ojo.")]
    if not factura.get("fecha"):
        return []
    if util.fecha_desde_texto(factura["vto_cae"]) >= util.fecha_desde_texto(factura["fecha"]):
        return []
    return [Resultado(
        "vencimiento_cae", "error", "factura",
        "El CAE vence el %s, antes de la emisión de la factura (%s)." % (
            util.ddmmaaaa(util.fecha_desde_texto(factura["vto_cae"])),
            util.ddmmaaaa(util.fecha_desde_texto(factura["fecha"]))),
    )]


def control_factura_repetida(ctx):
    numero = _factura(ctx).get("numero")
    if not numero:
        return []
    return [
        Resultado("factura_repetida", "error", "factura",
                  "La factura %s ya está en el expediente %s." % (numero, otro["id"]), str(otro["id"]))
        for otro in ctx.get("otros_del_proveedor") or []
        if otro.get("factura") and util.misma_factura(numero, otro["factura"])
    ]


# --- SII -------------------------------------------------------------------------

def control_sii_coincide(ctx):
    sii, factura = _sii(ctx), _factura(ctx)
    if not sii:
        return [Resultado("sii_coincide", "error", "sii", "Falta pegar el texto de la factura cargada en el SII.")]
    resultados = []
    oc = ctx.get("oc")
    if oc and util.sap_sin_ceros(sii.get("orden_compra") or "") != util.sap_sin_ceros(oc["numero"]):
        resultados.append(Resultado("sii_coincide", "error", "sii",
                                    "La OC del SII (%s) no es la del expediente (%s)." % (sii.get("orden_compra") or "sin OC", oc["numero"]),
                                    "oc"))
    if factura.get("numero") and not (sii.get("nro_comprobante")
                                      and util.misma_factura(factura["numero"], sii["nro_comprobante"])):
        resultados.append(Resultado("sii_coincide", "error", "sii",
                                    "El N° de comprobante del SII (%s) no coincide con la factura %s."
                                    % (sii.get("nro_comprobante") or "sin número", factura["numero"]), "numero"))
    if factura.get("cae") and str(sii.get("cae") or "") != str(factura["cae"]).strip():
        resultados.append(Resultado("sii_coincide", "error", "sii",
                                    "El CAE del SII (%s) no coincide con el de la factura (%s)."
                                    % (sii.get("cae") or "sin CAE", factura["cae"]), "cae"))
    if factura.get("centavos") not in (None, "") and sii.get("monto_centavos") != int(factura["centavos"]):
        monto = sii.get("monto_centavos")
        resultados.append(Resultado("sii_coincide", "error", "sii",
                                    "El monto del SII (%s) no coincide con la factura (%s)."
                                    % (_pesos(monto) if monto is not None else "sin monto", _pesos(int(factura["centavos"]))),
                                    "monto"))
    return resultados


def periodo_sii_esperado(expediente):
    """Mes que va en el SII: el del fin del período validado (en un período específico, el del «hasta»)."""
    hasta = expediente.get("periodo_hasta")
    return hasta[:7] if hasta else expediente.get("periodo")


def control_sii_periodo(ctx):
    sii = _sii(ctx)
    expediente = ctx["expediente"]
    esperado = periodo_sii_esperado(expediente)
    if not sii or not esperado or sii.get("periodo") == esperado:
        return []
    if esperado == expediente.get("periodo"):
        detalle = esperado
    else:
        detalle = "%s, el mes en que termina el %s al %s" % (
            esperado, util.ddmmaaaa(util.fecha_desde_texto(expediente["periodo_desde"])),
            util.ddmmaaaa(util.fecha_desde_texto(expediente["periodo_hasta"])))
    return [Resultado("sii_periodo", "error", "sii",
                      "El período cargado en el SII (%s) no es el del período validado (%s)."
                      % (sii.get("periodo") or "sin período", detalle))]


def control_sii_destino(ctx):
    sii = _sii(ctx)
    if not sii:
        return []
    esperado = ctx["parametros"].get("sii") or {}
    nombres = {"area": "el área", "tipo_servicio": "el tipo de servicio", "concepto": "el concepto"}
    return [
        Resultado("sii_destino", "error", "sii",
                  "En el SII %s es %s; debe ser %s." % (nombres[clave], sii.get(clave) or "(vacío)", esperado[clave]), clave)
        for clave in ("area", "tipo_servicio", "concepto")
        if clave in esperado and not _texto_igual(sii.get(clave), esperado[clave])
    ]


# --- Remitos -----------------------------------------------------------------------

def control_remito_fuera_de_periodo(ctx):
    limites = _limites(ctx)
    if limites is None:
        return []
    resultados = []
    for remito in _remitos_de_consumo(ctx):
        if remito.get("aclara_periodo") or not _fecha_base(remito):
            continue
        fecha = util.fecha_desde_texto(_fecha_base(remito))
        if not limites[0] <= fecha <= limites[1]:
            resultados.append(Resultado(
                "remito_fuera_de_periodo", "error", "remito",
                "El remito %s (%s) está fuera del período %s." % (
                    remito["numero"], util.ddmmaaaa(fecha), ctx["expediente"]["periodo"]),
                remito["numero"],
            ))
    return resultados


def control_codigo_remito_distinto(ctx):
    renglones = _renglones(ctx)
    vistos = set()
    resultados = []
    for remito in _remitos_de_consumo(ctx):
        for item in remito.get("items") or []:
            codigo = str(item.get("codigo") or "").strip()
            try:
                pos = int(item.get("pos"))
            except (TypeError, ValueError):
                continue
            renglon = renglones.get(pos)
            if not codigo or renglon is None or pos in vistos:
                continue
            if util.sap_sin_ceros(codigo) != util.sap_sin_ceros(renglon.get("codigo") or ""):
                vistos.add(pos)
                resultados.append(Resultado(
                    "codigo_remito_distinto", "salvable", "remito",
                    "El remito %s indica el código %s en el renglón %d; la OC tiene %s." % (
                        remito["numero"], codigo, pos, renglon.get("codigo") or "(sin código)"),
                    str(pos),
                ))
    return resultados


def control_formato_remito(ctx):
    return [
        Resultado("formato_remito", "aviso", "remito",
                  "El número de remito %s no tiene la forma 0001-00000001." % r.get("numero"), r.get("numero"))
        for r in _remitos(ctx)
        if not _RE_REMITO.fullmatch(str(r.get("numero") or "").strip())
    ]


# --- OC y renglones -------------------------------------------------------------------

def control_vigencia_oc(ctx):
    oc, limites = ctx.get("oc"), _limites(ctx)
    if not oc or limites is None:
        return []
    desde = util.fecha_desde_texto(oc["vig_desde"]) if oc.get("vig_desde") else None
    fines = [util.fecha_desde_texto(f) for f in (oc.get("vig_hasta"), oc.get("prorroga")) if f]
    hasta = max(fines) if fines else None
    if (desde is None or limites[1] >= desde) and (hasta is None or limites[0] <= hasta):
        return []
    return [Resultado("vigencia_oc", "error", "oc",
                      "El período %s está fuera de la vigencia de la OC %s (%s al %s)." % (
                          ctx["expediente"]["periodo"], oc["numero"],
                          util.ddmmaaaa(desde) if desde else "sin inicio", util.ddmmaaaa(hasta) if hasta else "sin fin"))]


def control_saldo_renglon(ctx):
    consumo = {int(f["pos"]): f for f in ctx.get("consumo") or []}
    propio = ctx["expediente"].get("estado") != "ANULADO"
    resultados = []
    for pos, cantidad in sorted(_cantidades(ctx).items()):
        fila = consumo.get(pos)
        if fila is None:
            resultados.append(Resultado("saldo_renglon", "error", "oc",
                                        "El renglón %d no existe en la OC." % pos, str(pos)))
            continue
        disponible = _decimal(fila["saldo"]) + (cantidad if propio else 0)
        if cantidad > disponible:
            resultados.append(Resultado(
                "saldo_renglon", "error", "oc",
                "El renglón %d tiene saldo %s y el expediente consume %s." % (
                    pos, _cantidad_texto(disponible), _cantidad_texto(cantidad)),
                str(pos),
            ))
    return resultados


def control_comodato_sin_remito_equipo(ctx):
    oc = ctx.get("oc")
    if not oc or not oc.get("comodato"):
        return []
    if any(o.get("estado") in ESTADOS_VALIDADOS for o in ctx.get("otros_de_la_oc") or []):
        return []
    if any(r.get("es_equipo_comodato") for r in _remitos(ctx)):
        return []
    return [Resultado("comodato_sin_remito_equipo", "error", "remito",
                      "Primera validación de OC con comodato sin remito del equipo.")]


def control_expediente_duplicado(ctx):
    periodo = ctx["expediente"].get("periodo")
    if not periodo:
        return []
    return [
        Resultado("expediente_duplicado", "aviso", "expediente",
                  "Ya hay otro expediente de la OC para %s (expediente %s)." % (periodo, o["id"]), str(o["id"]))
        for o in ctx.get("otros_de_la_oc") or []
        if o.get("periodo") == periodo
    ]


def control_renglon_por_agotarse(ctx):
    umbral = int(ctx["parametros"].get("umbral_por_agotarse_pct", 85))
    usados = _cantidades(ctx)
    return [
        Resultado("renglon_por_agotarse", "aviso", "oc",
                  ("El renglón %s se agotó: lleva consumido el %d %%." % (f["pos"], f["pct_consumido"]))
                  if f.get("agotado") else
                  "El renglón %s lleva consumido el %d %% (saldo %s)." % (f["pos"], f["pct_consumido"], f["saldo"]),
                  str(f["pos"]))
        for f in ctx.get("consumo") or []
        if int(f["pos"]) in usados and f["pct_consumido"] >= umbral
    ]


def control_objeto_faltante(ctx):
    oc = ctx.get("oc")
    if not oc or (oc.get("objeto") or "").strip():
        return []
    return [Resultado("objeto_faltante", "error", "oc", "Falta el objeto de la contratación en la OC %s" % oc["numero"])]


def control_documentacion_centralizada(ctx):
    oc = ctx.get("oc")
    if ctx["expediente"].get("tipo") != "CENTRALIZADA" or not oc:
        return []
    checklist = _datos(ctx).get("checklist") or {}
    faltan = [doc for doc in oc.get("doc_requerida_central") or [] if not checklist.get(doc)]
    if not faltan:
        return []
    return [Resultado("documentacion_centralizada", "error", "expediente",
                      "Falta tildar como auditada la documentación: %s." % ", ".join(faltan))]


def control_leyenda_cv_faltante(ctx):
    oc = ctx.get("oc")
    if ctx["expediente"].get("tipo") != "CENTRALIZADA" or not oc or not oc.get("centralizada"):
        return []
    if (oc.get("leyenda_cv") or "").strip():
        return []
    return [Resultado("leyenda_cv_faltante", "error", "oc", "Falta la leyenda del CV en la OC %s." % oc["numero"])]


def control_eventual_repetido(ctx):
    """Un pago eventual por proveedor y año (año de la factura); avisa en el posterior, nombrando al anterior."""
    expediente = ctx["expediente"]
    anio = (_factura(ctx).get("fecha") or "")[:4]
    if expediente.get("tipo") != "EVENTUAL" or not anio:
        return []
    return [
        Resultado("eventual_repetido", "error", "factura",
                  "Ya hay un pago eventual para el proveedor SAP %s en %s (expediente %s)." % (expediente["sap"], anio, otro["id"]),
                  str(otro["id"]))
        for otro in ctx.get("otros_del_proveedor") or []
        if otro.get("tipo") == "EVENTUAL" and otro["id"] < expediente["id"] and (otro.get("fecha_factura") or "")[:4] == anio
    ]


CONTROLES = [
    control_importe_factura,
    control_destinatario_factura,
    control_domicilio_factura,
    control_periodo_factura,
    control_menciones_factura,
    control_formato_factura,
    control_vencimiento_cae,
    control_factura_repetida,
    control_sii_coincide,
    control_sii_periodo,
    control_sii_destino,
    control_remito_fuera_de_periodo,
    control_codigo_remito_distinto,
    control_formato_remito,
    control_vigencia_oc,
    control_saldo_renglon,
    control_comodato_sin_remito_equipo,
    control_expediente_duplicado,
    control_renglon_por_agotarse,
    control_objeto_faltante,
    control_documentacion_centralizada,
    control_leyenda_cv_faltante,
    control_eventual_repetido,
]


# --- Notas aclaratorias (controles salvables) ---------------------------------------

def _nota_codigo_remito_distinto(resultado, ctx):
    pos = int(resultado.referencia)
    renglon = _renglones(ctx)[pos]
    for remito in _remitos_de_consumo(ctx):
        for item in remito.get("items") or []:
            codigo = str(item.get("codigo") or "").strip()
            if str(item.get("pos")) == str(pos) and codigo and \
                    util.sap_sin_ceros(codigo) != util.sap_sin_ceros(renglon.get("codigo") or ""):
                return (
                    "Se deja constancia de que en el remito N° %s el renglón %d figura con el código %s, cuando el "
                    "código correcto según la Orden de Compra N° %s es %s. Se trata de un error de tipeo que no afecta "
                    "lo entregado." % (remito["numero"], pos, codigo, ctx["oc"]["numero"], renglon.get("codigo") or "")
                )
    return ""


def periodo_de_factura_texto(desde, hasta):
    """"2026-07" si desde y hasta caen en el mismo mes; si no, "dd/mm/aaaa al dd/mm/aaaa"."""
    f_desde, f_hasta = util.fecha_desde_texto(desde), util.fecha_desde_texto(hasta)
    if (f_desde.year, f_desde.month) == (f_hasta.year, f_hasta.month):
        return util.iso(f_desde)[:7]
    return "%s al %s" % (util.ddmmaaaa(f_desde), util.ddmmaaaa(f_hasta))


def _nota_periodo_factura(resultado, ctx):
    factura = _factura(ctx)
    return (
        "Se deja constancia de que la factura N° %s indica el período %s, cuando el período validado según remito es %s."
        % (factura.get("numero"), periodo_de_factura_texto(factura["periodo_desde"], factura["periodo_hasta"]),
           ctx["expediente"]["periodo"])
    )


_DATO_MENCION = {"oc": "la Orden de Compra N°", "expediente": "el expediente", "remito": "el remito N°"}


def _nota_menciones_factura(resultado, ctx):
    clave = resultado.referencia
    factura = _factura(ctx)
    real = ", ".join(_menciones_reales(ctx)[clave])
    return "Se deja constancia de que la factura N° %s menciona %s %s, cuando corresponde %s." % (
        factura.get("numero"), _DATO_MENCION[clave], factura["menciona"][clave], real)


NOTAS = {
    "codigo_remito_distinto": _nota_codigo_remito_distinto,
    "periodo_factura": _nota_periodo_factura,
    "menciones_factura": _nota_menciones_factura,
}


def _referencia(valor):
    return "" if valor is None else str(valor)


def evaluar(ctx):
    """Corre todos los controles sobre un contexto ya armado; los salvables traen su nota sugerida y la guardada."""
    resultados = []
    for control in CONTROLES:
        for resultado in control(ctx):
            if resultado.nivel not in NIVELES:
                raise ValueError("Nivel inválido %r en %s." % (resultado.nivel, resultado.codigo))
            resultados.append(resultado)
    guardadas = {
        (n.get("codigo"), _referencia(n.get("referencia"))): n
        for n in _datos(ctx).get("notas_aclaratorias") or []
    }
    salida = []
    con_nota = 0
    for resultado in resultados:
        fila = resultado._asdict()
        if resultado.nivel == "salvable":
            redactor = NOTAS.get(resultado.codigo)
            fila["nota_sugerida"] = redactor(resultado, ctx) if redactor else ""
            fila["nota_guardada"] = guardadas.get((resultado.codigo, _referencia(resultado.referencia)))
            if fila["nota_guardada"] is not None:
                con_nota += 1
        salida.append(fila)
    resumen = {nivel: sum(1 for r in resultados if r.nivel == nivel) for nivel in NIVELES}
    resumen["salvable_con_nota"] = con_nota
    return {"resultados": salida, "resumen": resumen}


def controlar(con, expediente_id):
    """{"resultados": [...], "resumen": {"error": n, "salvable": n, "aviso": n, "verificar": n}}."""
    return evaluar(armar_contexto(con, expediente_id))
