"""Textos generados del expediente: una función pura por texto (blueprint §5, "Textos canónicos").

Cada función recibe el `ctx` que arma `negocio.contexto_textos` y devuelve `str` (o una lista de dicts). Si falta un dato
obligatorio lanza `TextoIncompleto`; nunca devuelve un texto con huecos.
"""
import re

from gestor import letras, util


class TextoIncompleto(Exception):
    """Falta un dato obligatorio para generar el texto."""


_FALTANTES = {
    "sap": "el N° SAP del proveedor",
    "razon": "la razón social del proveedor",
    "oc": "el N° de OC",
    "factura": "el N° de factura",
    "periodo": "el período validado",
}


def _requerir(ctx, *claves):
    faltan = [_FALTANTES.get(c, c) for c in claves if not ctx.get(c)]
    if faltan:
        raise TextoIncompleto("Falta cargar " + ", ".join(faltan) + ".")


def _prefijo(ctx):
    return "CASPH - " if ctx.get("efector") == "CASPH" else ""


def caratula(ctx):
    """`PAGO SAP <sap> <razon> - FC <factura> - <oc>` (CASPH antepone `CASPH - `)."""
    _requerir(ctx, "sap", "razon", "factura", "oc")
    return "%sPAGO SAP %s %s - FC %s - %s" % (_prefijo(ctx), ctx["sap"], ctx["razon"], ctx["factura"], ctx["oc"])


def nombre_archivo(referencia):
    """Referencia → nombre de archivo: cada uno de \\ / : * ? " < > | pasa a `-`, más `.pdf`."""
    return re.sub(r'[\\/:*?"<>|]', "-", referencia) + ".pdf"


def referencias(ctx):
    """Referencias GDE en orden, cada una `{"clave", "referencia", "archivo"}`."""
    _requerir(ctx, "razon", "factura", "periodo")
    remitos = [r for r in ctx.get("remitos") or [] if r]
    if not remitos:
        raise TextoIncompleto("Falta cargar al menos un remito.")
    mm_aa = util.mm_aa(ctx["periodo"])
    razon, factura = ctx["razon"], ctx["factura"]
    filas = [
        ("factura", "%s - FC %s - %s" % (mm_aa, factura, razon)),
        ("sii", "%s - CARGA EN SII - %s" % (mm_aa, razon)),
    ]
    if len(remitos) == 1:
        filas.append(("remitos", "%s - RTO %s - %s" % (mm_aa, remitos[0], razon)))
    else:
        filas.append(("remitos", "%s - REMITOS - %s" % (mm_aa, razon)))
    if ctx.get("remito_equipo") and ctx.get("primera_validacion"):
        filas.append(("remito_equipo", "%s - REMITO POR EQUIPO EN COMODATO - %s" % (mm_aa, razon)))
    filas.append(("cv", "%s - CERTIFICADO DE VALIDACIÓN - %s" % (mm_aa, razon)))
    if ctx.get("tipo_oc") in ("BIEN", "PROVISION"):
        filas.append(("vale_hoja", "%s - VALE DE ENTRADA - %s" % (mm_aa, razon)))
    else:
        filas.append(("vale_hoja", "%s - HOJA DE ENTRADA - %s" % (mm_aa, razon)))
    filas.append(("autorizacion", "AUTORIZACIÓN DE PAGO FC N° %s, %s - %s" % (factura, razon, mm_aa)))
    filas.append(("constancia", "%s - CONSTANCIA DE CONTABILIZACIÓN - %s" % (mm_aa, razon)))
    prefijo = _prefijo(ctx)
    return [
        {"clave": clave, "referencia": prefijo + texto, "archivo": nombre_archivo(prefijo + texto)}
        for clave, texto in filas
    ]


# --- Autorización de pago --------------------------------------------------

def frase_remitos(numeros):
    """1 → "conforme al remito N° A"; 2 → "... N° A y B"; 3+ → "... N° A, B y C"."""
    numeros = [n for n in numeros if n]
    if not numeros:
        raise TextoIncompleto("Falta cargar al menos un remito.")
    if len(numeros) == 1:
        return "conforme al remito N° %s" % numeros[0]
    return "conforme a los remitos N° %s y %s" % (", ".join(numeros[:-1]), numeros[-1])


def frase_periodo(ctx):
    """Día de inicio 1 → "en el mes de agosto del 2026"; otro → "en el período del dd/mm/aaaa al dd/mm/aaaa"."""
    _requerir(ctx, "periodo")
    if int(ctx.get("dia_inicio") or 1) == 1:
        anio, mes = (int(p) for p in ctx["periodo"].split("-"))
        return "en el mes de %s del %04d" % (util.MESES[mes - 1], anio)
    if not ctx.get("periodo_desde") or not ctx.get("periodo_hasta"):
        raise TextoIncompleto("Faltan las fechas desde y hasta del período.")
    return "en el período del %s al %s" % (
        util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_desde"])),
        util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_hasta"])))


def _frase_comodato(ctx):
    if ctx.get("comodato") and ctx.get("primera_validacion") and ctx.get("remito_equipo"):
        return ", y el remito n° %s, correspondiente al equipo entregado en calidad de comodato" % ctx["remito_equipo"]
    return ""


def autorizacion(ctx):
    """Autorización de pago: {"referencia", "cuerpo"} con el texto canónico en una sola línea."""
    if not (ctx.get("objeto") or "").strip():
        raise TextoIncompleto("Falta el objeto de la contratación en la OC %s" % ctx.get("oc", ""))
    if not ctx.get("expediente"):
        raise TextoIncompleto("Falta cargar el N° GDE del expediente (EX).")
    _requerir(ctx, "factura", "razon", "oc", "periodo")
    if ctx.get("centavos") in (None, ""):
        raise TextoIncompleto("Falta cargar el importe de la factura.")
    if not ctx.get("destino"):
        raise TextoIncompleto("Falta el destino del efector en la configuración.")
    cuerpo = (
        "Por medio del expediente %s AUTORIZO se abone la factura N° %s por la suma de %s del proveedor %s "
        "correspondiente %s %s, %s%s, con destino %s, %s de acuerdo a la Orden de compra N° %s." % (
            ctx["expediente"], ctx["factura"], letras.importe_en_letras(int(ctx["centavos"])), ctx["razon"],
            ctx.get("articulo") or "al", ctx["objeto"].strip(), frase_remitos(ctx.get("remitos") or []),
            _frase_comodato(ctx), ctx["destino"], frase_periodo(ctx), ctx["oc"])
    )
    referencia = "%sAUTORIZACIÓN DE PAGO FC N° %s, %s - %s" % (
        _prefijo(ctx), ctx["factura"], ctx["razon"], util.mm_aa(ctx["periodo"]))
    return {"referencia": referencia, "cuerpo": cuerpo}


# --- Constancia de recepción de comodato -----------------------------------

def constancia_comodato(ctx):
    """Constancia de recepción del equipo en comodato: {"referencia", "cuerpo"} (dos párrafos separados por \n)."""
    _requerir(ctx, "razon", "sap", "oc")
    faltan = [nombre for clave, nombre in (
        ("remito_equipo", "el remito del equipo en comodato"),
        ("orden_remito_equipo", "el orden del remito del equipo en el expediente"),
        ("expediente", "el N° GDE del expediente (EX)"),
        ("nota_comodato", "la nota de comodato en la configuración"),
    ) if not ctx.get(clave)]
    if faltan:
        raise TextoIncompleto("Falta cargar " + ", ".join(faltan) + ".")
    cuerpo = (
        "Por medio de la presente, y de conformidad con lo solicitado en la %s, se deja constancia de la recepción del "
        "equipamiento cedido en comodato por el proveedor %s (SAP %s), correspondiente a la Orden de Compra N° %s.\n"
        "Dicha entrega se encuentra debidamente respaldada mediante el remito N° %s, el cual consta vinculado en orden %s "
        "del %s y embebido al presente documento para su validación." % (
            ctx["nota_comodato"], ctx["razon"], ctx["sap"], ctx["oc"],
            ctx["remito_equipo"], ctx["orden_remito_equipo"], ctx["expediente"])
    )
    referencia = "%sCONSTANCIA DE RECEPCIÓN: EQUIPO EN COMODATO - OC %s, %s" % (_prefijo(ctx), ctx["oc"], ctx["razon"])
    return {"referencia": referencia, "cuerpo": cuerpo}
