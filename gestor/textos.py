"""Textos generados del expediente: una función pura por texto (blueprint §5, "Textos canónicos").

Cada función recibe el `ctx` que arma `negocio.contexto_textos` y devuelve `str` (o una lista de dicts). Si falta un dato
obligatorio lanza `TextoIncompleto`; nunca devuelve un texto con huecos.
"""
import re

from gestor import util


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
