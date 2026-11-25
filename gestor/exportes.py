"""Exportes tabulares: CSV NUMERACIÓN (paso 24) y los seis exportes en Excel, CSV e imprimible (paso 26)."""
import csv
import html
import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from gestor import controles, db, negocio, textos, util, xlsx_escritor

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
    return ("\ufeff" + salida.getvalue()).encode("utf-8")


def nombre_csv_numeracion(entrega):
    return "NUMERACION %s %d.csv" % (entrega["efector"], entrega["numero"])


# --- Seis exportes (paso 26) ---------------------------------------------------
# Cada exporte devuelve (titulo, encabezados, filas, columnas_moneda); las columnas de moneda llevan centavos int.

class ExporteDesconocido(Exception):
    """No existe un exporte con ese nombre."""


def _cantidad(texto):
    try:
        return util.a_decimal(str(texto or "0"), decimales=None)
    except (TypeError, ValueError):
        return Decimal(0)


def _texto_cantidad(numero):
    return "0" if numero == 0 else format(numero.normalize(), "f")


def _sin_ceros(valor):
    return util.sap_sin_ceros(str(valor or "").strip())


def _centavos_por(cantidad, precio_centavos):
    return int((cantidad * Decimal(int(precio_centavos or 0))).to_integral_value(rounding=ROUND_HALF_UP))


def exporte_consumo_oc(con, parametros):
    numero = _sin_ceros(parametros.get("oc"))
    if not numero:
        raise negocio.ErrorValidacion("Indicá la OC (?oc=) para exportar su consumo.")
    ficha = negocio.ficha_oc(con, numero)
    oc, proveedor = ficha["oc"], ficha["proveedor"] or {}
    efector = parametros.get("efector") if parametros.get("efector") in negocio.EFECTORES else None
    consumo = negocio.consumo_oc(con, numero, efector)
    periodos = [p for p in consumo["grilla"]["periodos"]]
    precios = {}
    for r in ficha["renglones"]:
        con_desglose = r.get("desglose_cantidad") not in (None, "")
        precios[r["pos"]] = int((r.get("desglose_precio_centavos") if con_desglose else r.get("precio_centavos")) or 0)
    expedientes_por_pos = {}
    for resumen in ficha["expedientes"]:
        if resumen["estado"] == "ANULADO" or (efector and resumen.get("efector") != efector):
            continue
        exp = negocio.obtener_expediente(con, resumen["id"])
        for pos in negocio.cantidades_del_expediente(exp):
            expedientes_por_pos.setdefault(pos, []).append(str(resumen["id"]))
    nombres_periodo = {negocio.COLUMNA_UNICA: "Consumido", negocio.SIN_PERIODO: "Sin período"}
    encabezados = (["Pos", "Descripción", "Cantidad OC", "Unidad", "Precio unitario", "Consumo previo"]
                   + ["Consumido %s" % nombres_periodo.get(p, p) for p in periodos]
                   + ["Total consumido", "Importe consumido", "Saldo", "% consumido", "Expedientes"])
    celdas = {f["pos"]: f["celdas"] for f in consumo["grilla"]["filas"]}
    filas = []
    for r in consumo["renglones"]:
        total = _cantidad(r["consumo_previo"]) + _cantidad(r["validado"])
        filas.append(
            [r["pos"], r["descripcion"], r["cantidad_oc"], r["unidad"], precios.get(r["pos"], 0), r["consumo_previo"]]
            + [celdas.get(r["pos"], {}).get(p, "0") for p in periodos]
            + [_texto_cantidad(total), _centavos_por(total, precios.get(r["pos"], 0)), r["saldo"], r["pct_consumido"],
               ", ".join(expedientes_por_pos.get(r["pos"], []))])
    vigencia = "%s a %s" % (oc.get("vig_desde") or "?", negocio._fin_vigencia(oc) or "?")
    titulo = "Consumo de la OC %s — %s — %s — vigencia %s" % (
        oc["numero"], proveedor.get("razon_social") or "", oc.get("objeto") or "sin objeto", vigencia)
    return titulo, encabezados, filas, ("Precio unitario", "Importe consumido")


def _estado_oc(oc, hoy, dias_aviso):
    if oc.get("excluida"):
        return "Excluida"
    fin = negocio._fin_vigencia(oc)
    if not oc.get("vig_desde") or not fin:
        return "Sin vigencia"
    try:
        fin = util.fecha_desde_texto(fin)
    except ValueError:
        return "Sin vigencia"
    if fin < hoy:
        estado = "Vencida"
    elif (fin - hoy).days <= dias_aviso:
        estado = "Por vencer"
    else:
        estado = "Vigente"
    return estado + (" (cerrada en SAP)" if oc.get("cerrada_sap") else "")


def exporte_seguimiento_oc(con, parametros):
    hoy = date.today()
    dias_aviso = int(db.leer_parametros(con).get("dias_aviso_vencimiento_oc", 60))
    efector = parametros.get("efector") or None
    if efector == "Ambos":
        efector = None
    lista = negocio.listar_oc(con, efector=efector, texto=parametros.get("q") or "")
    encabezados = ["OC", "Efector", "SAP", "Proveedor", "Objeto", "Vigencia desde", "Vigencia hasta", "Estado",
                   "Importe OC", "Importe consumido", "% consumido", "Renglones por agotarse", "Último período validado"]
    filas = []
    for resumen in lista:
        ficha = negocio.ficha_oc(con, resumen["numero"])
        oc = ficha["oc"]
        renglones = {r["pos"]: r for r in ficha["renglones"]}
        consumo = negocio.consumo_por_renglon(con, oc)
        consumido = 0
        for r in consumo:
            fila_r = renglones.get(r["pos"]) or {}
            con_desglose = fila_r.get("desglose_cantidad") not in (None, "")
            precio = (fila_r.get("desglose_precio_centavos") if con_desglose else fila_r.get("precio_centavos")) or 0
            consumido += _centavos_por(_cantidad(r["consumo_previo"]) + _cantidad(r["validado"]), precio)
        importe = int(resumen["importe_centavos"] or 0)
        pct = int((Decimal(consumido) * 100 / importe).to_integral_value(rounding=ROUND_HALF_UP)) if importe else 0
        ultimo = con.execute(
            "SELECT MAX(periodo) FROM expediente WHERE oc = ? AND estado IN (%s)"
            % ", ".join("?" * len(controles.ESTADOS_VALIDADOS)), (oc["numero"],) + controles.ESTADOS_VALIDADOS,
        ).fetchone()[0]
        filas.append([
            oc["numero"], oc["efector"], oc["sap"], resumen["razon_social"], oc.get("objeto") or "",
            oc.get("vig_desde") or "", negocio._fin_vigencia(oc) or "", _estado_oc(oc, hoy, dias_aviso),
            importe, consumido, pct, ", ".join(str(r["pos"]) for r in consumo if r["por_agotarse"]), ultimo or "",
        ])
    titulo = "Seguimiento de OC" + (" — %s" % efector if efector else "") + (
        " — búsqueda \"%s\"" % parametros["q"] if parametros.get("q") else "")
    return titulo, encabezados, filas, ("Importe OC", "Importe consumido")


def exporte_pendientes(con, parametros):
    encabezados = ["Expediente", "Efector", "Proveedor", "OC", "Período", "Motivo", "Seguimiento", "Días de demora"]
    filas = [[p["id"], p["efector"], p["proveedor"], p["oc"] or "", p["periodo"] or "", p["motivo"],
              p["fecha_seguimiento"] or "", p["dias_demora"]] for p in negocio.pendientes(con)]
    return "Expedientes pendientes", encabezados, filas, ()


def exporte_entrega(con, parametros):
    entrega_id = parametros.get("id")
    if not entrega_id:
        raise negocio.ErrorValidacion("Indicá la entrega (?id=) para exportarla.")
    entrega = negocio.obtener_entrega(con, entrega_id)
    titulo = "Entrega %s %d — %s%s" % (entrega["efector"], entrega["numero"], entrega["nombre"],
                                      " — enviada el %s" % entrega["fecha_envio"] if entrega["fecha_envio"] else "")
    return titulo, list(ENCABEZADOS_NUMERACION), filas_numeracion(con, entrega["id"]), ()


def exporte_calendario(con, parametros):
    anio = parametros.get("anio") or date.today().year
    efector = parametros.get("efector") or None
    datos = negocio.calendario(con, anio, efector=None if efector == "Ambos" else efector,
                               tipo=parametros.get("tipo") or None, sap=parametros.get("sap") or None)
    encabezados = ["OC", "Proveedor", "Objeto"] + [m.capitalize() for m in util.MESES] + ["Por vencer"]
    filas = []
    for fila in datos["filas"]:
        celdas = []
        for c in fila["celdas"]:
            marcas = ("●" if c["entrega_enviada"] else "") + ("◆" if c["centralizada_enviada"] else "")
            celdas.append(c["letra"] + (" " + marcas if marcas else ""))
        filas.append([fila["oc"], fila["razon_social"], fila["objeto"] or ""] + celdas
                     + ["Sí" if fila["vence_pronto"] else ""])
    referencias = ", ".join("%s %s" % (letra, estado.replace("_", " ")) for estado, letra in datos["estados"].items())
    return "Calendario %d (%s)" % (datos["anio"], referencias), encabezados, filas, ()


def exporte_centralizadas(con, parametros):
    sql = ("SELECT e.id FROM expediente e WHERE e.tipo = 'CENTRALIZADA' AND e.estado <> 'ANULADO'")
    valores = []
    if parametros.get("periodo"):
        sql += " AND e.periodo = ?"
        valores.append(parametros["periodo"])
    encabezados = ["OC", "Proveedor", "Período", "Remito", "N° de CV", "N° de nota", "Fecha de envío", "Estado", "Expediente"]
    filas = []
    for (id_expediente,) in con.execute(sql + " ORDER BY e.periodo, e.oc, e.id", valores).fetchall():
        exp = negocio.obtener_expediente(con, id_expediente)
        central = exp["datos"].get("centralizada") or {}
        remitos = [r["numero"] for r in exp["datos"].get("remitos") or [] if isinstance(r, dict)]
        filas.append([exp.get("oc") or "", exp.get("razon_social") or "", exp.get("periodo") or "",
                      SEPARADOR_LISTA.join(remitos), central.get("numero_cv") or "", central.get("numero_nota") or "",
                      central.get("fecha_envio") or "", exp["estado"], exp["id"]])
    titulo = "Centralizadas" + (" — período %s" % parametros["periodo"] if parametros.get("periodo") else "")
    return titulo, encabezados, filas, ()


EXPORTES = {
    "consumo-oc": exporte_consumo_oc,
    "seguimiento-oc": exporte_seguimiento_oc,
    "pendientes": exporte_pendientes,
    "entrega": exporte_entrega,
    "calendario": exporte_calendario,
    "centralizadas": exporte_centralizadas,
}
FORMATOS = ("xlsx", "csv", "html")


def exportar(con, nombre, parametros):
    """(titulo con fecha de emisión, encabezados, filas, columnas_moneda) del exporte `nombre`."""
    if nombre not in EXPORTES:
        raise ExporteDesconocido("No existe el exporte %s." % nombre)
    titulo, encabezados, filas, moneda = EXPORTES[nombre](con, parametros or {})
    return xlsx_escritor.titulo_con_fecha(titulo), list(encabezados), filas, tuple(moneda)


def _texto_celda(valor, moneda):
    if valor is None:
        return ""
    if moneda and isinstance(valor, int) and not isinstance(valor, bool):
        return util.formato_pesos(valor)
    return str(valor)


def filas_como_texto(encabezados, filas, columnas_moneda=()):
    moneda = set(columnas_moneda)
    return [[_texto_celda(v, i < len(encabezados) and encabezados[i] in moneda) for i, v in enumerate(fila)] for fila in filas]


def a_html(titulo, encabezados, filas, columnas_moneda=()):
    """Página imprimible (bytes UTF-8): tabla con estilos propios y @media print sin la barra de acciones."""
    moneda = set(columnas_moneda)
    e = html.escape
    cabeza = "".join("<th scope=\"col\">%s</th>" % e(str(x)) for x in encabezados)
    cuerpo = []
    for fila in filas:
        celdas = []
        for i, valor in enumerate(fila):
            es_moneda = i < len(encabezados) and encabezados[i] in moneda
            es_numero = es_moneda or (isinstance(valor, int) and not isinstance(valor, bool))
            celdas.append("<td%s>%s</td>" % (' class="numero"' if es_numero else "", e(_texto_celda(valor, es_moneda))))
        cuerpo.append("<tr>%s</tr>" % "".join(celdas))
    if not cuerpo:
        cuerpo.append('<tr><td colspan="%d">Sin datos.</td></tr>' % max(1, len(encabezados)))
    pagina = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(titulo)s</title>
<style>
body { margin: 24px; font: 14px/1.4 "Segoe UI", system-ui, sans-serif; color: #1B2430; background: #FFFFFF; }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 16px; }
.acciones { margin: 0 0 16px; }
button { min-height: 44px; padding: 8px 16px; border: 1px solid #1F4E8C; border-radius: 4px; background: #1F4E8C;
  color: #FFFFFF; font: inherit; font-weight: 600; cursor: pointer; }
button:focus { outline: 3px solid #1F4E8C; outline-offset: 2px; }
table { border-collapse: collapse; width: 100%%; }
th, td { padding: 6px 8px; border: 1px solid #D0D7DE; text-align: left; vertical-align: top; }
th { background: #F6F8FA; font-weight: 600; }
.numero { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
@media print {
  body { margin: 0; font-size: 11px; }
  .acciones { display: none; }
  th, td { padding: 3px 4px; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
}
</style>
</head>
<body>
<div class="acciones"><button type="button" onclick="window.print()">Imprimir</button></div>
<h1>%(titulo)s</h1>
<table>
<thead><tr>%(cabeza)s</tr></thead>
<tbody>
%(cuerpo)s
</tbody>
</table>
</body>
</html>
""" % {"titulo": e(titulo), "cabeza": cabeza, "cuerpo": "\n".join(cuerpo)}
    return pagina.encode("utf-8")


def generar(con, nombre, formato, parametros):
    """(contenido bytes, tipo MIME, nombre de archivo, en_linea) del exporte en el formato pedido."""
    if formato not in FORMATOS:
        raise ExporteDesconocido("No existe el formato %s." % formato)
    titulo, encabezados, filas, moneda = exportar(con, nombre, parametros)
    archivo = "%s-%s.%s" % (nombre, date.today().strftime("%Y%m%d"), formato)
    if formato == "xlsx":
        hoja = nombre.replace("-", " ").capitalize()
        return (xlsx_escritor.contenido_xlsx(hoja, titulo, encabezados, filas, moneda),
                xlsx_escritor.TIPO_XLSX, archivo, False)
    if formato == "csv":
        return a_csv(encabezados, filas_como_texto(encabezados, filas, moneda)), "text/csv; charset=utf-8", archivo, False
    return a_html(titulo, encabezados, filas, moneda), "text/html; charset=utf-8", archivo, True
