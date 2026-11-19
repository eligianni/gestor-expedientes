"""Exportes tabulares: CSV con formato NUMERACIÓN (paso 24)."""
import csv
import io

from gestor import negocio, textos, util

ENCABEZADOS_NUMERACION = (
    "REMITO", "SII", "PERIODO", "SAP", "OC", "FACTURA", "IMPORTE", "TEXTO SAP", "TXT CABECERA", "EXPEDIENTE",
    "GDE CARATULA", "GDE FACTURA", "GDE SII", "GDE OC", "GDE REMITOS", "GDE CV", "GDE VALE/HOJA", "GDE AUTORIZACION",
    "GDE CONTABILIZACION",
)

SEPARADOR_LISTA = " / "


def _periodo_mm_aa(periodo):
    """"2026-08" → "08-26"."""
    if not periodo or len(periodo) != 7:
        return ""
    return "%s-%s" % (periodo[5:7], periodo[2:4])


def _textos_sap(con, id_expediente):
    try:
        ctx = negocio.contexto_textos(con, id_expediente)
        return textos.textos_sap(ctx, ctx["limite_texto_sap"])
    except textos.TextoIncompleto:
        return None


def _fila_numeracion(con, id_expediente):
    exp = negocio.obtener_expediente(con, id_expediente)
    datos = exp["datos"]
    remitos = [r for r in datos.get("remitos") or [] if isinstance(r, dict)]
    comunes = [r["numero"] for r in remitos if not r.get("es_equipo_comodato")]
    equipo = [r["numero"] for r in remitos if r.get("es_equipo_comodato")]
    factura = datos.get("factura") or {}
    sii = datos.get("sii") or {}
    gde = datos.get("gde") or {}
    gde_remitos = gde.get("remitos") or {}
    rm = [gde_remitos[n] for n in comunes if gde_remitos.get(n)]
    if gde.get("remito_equipo"):
        rm.append(gde["remito_equipo"])
    sap = _textos_sap(con, exp["id"]) or {}
    centavos = factura.get("centavos")
    return [
        SEPARADOR_LISTA.join(comunes + equipo),
        sii.get("cod_tramite") or "",
        _periodo_mm_aa(exp.get("periodo")),
        exp.get("sap") or "",
        exp.get("oc") or "",
        exp.get("factura") or "",
        util.formato_pesos(centavos) if centavos not in (None, "") else "",
        (sap.get("ingreso") or {}).get("texto", ""),
        (sap.get("contabilizada") or {}).get("txt_cabecera", ""),
        gde.get("expediente") or "",
        gde.get("caratula") or "",
        gde.get("factura") or "",
        gde.get("sii") or "",
        gde.get("oc_pdf") or "",
        SEPARADOR_LISTA.join(rm),
        gde.get("cv") or "",
        gde.get("vale_hoja") or "",
        gde.get("autorizacion") or "",
        gde.get("contabilizacion") or "",
    ]


def filas_numeracion(con, entrega_id):
    """Una fila NUMERACIÓN por expediente de la entrega, en el orden de los encabezados."""
    entrega = negocio.obtener_entrega(con, entrega_id)
    return [_fila_numeracion(con, e["id"]) for e in entrega["expedientes"]]


def a_csv(encabezados, filas):
    """CSV para Excel en español: UTF-8 con BOM, separador `;`, fin de línea CRLF."""
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(list(encabezados))
    for fila in filas:
        escritor.writerow(["" if valor is None else str(valor) for valor in fila])
    return ("﻿" + salida.getvalue()).encode("utf-8")


def nombre_csv_numeracion(entrega):
    return "NUMERACION %s %d.csv" % (entrega["efector"], entrega["numero"])
