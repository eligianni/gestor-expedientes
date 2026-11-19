"""Vistas en tabla de expedientes, OC y renglones (pantalla Tablas) y su exportación a Excel.

Cada tabla es {"columnas": [{"clave", "titulo", "tipo"}], "filas": [{clave: valor}]}. El filtrado, el orden y la
elección de columnas se hacen en el navegador; Excel recibe exactamente lo que se ve (columnas visibles y filas
filtradas, en ese orden). Tipos: texto, numero, moneda (centavos int), cantidad (texto de Decimal), fecha (AAAA-MM-DD),
fecha_hora (ISO), si_no (0/1).
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from gestor import util, xlsx_escritor

TIPOS = ("texto", "numero", "moneda", "cantidad", "fecha", "fecha_hora", "si_no")


class TablaDesconocida(Exception):
    """No existe una tabla con ese nombre."""


def _col(clave, titulo, tipo="texto", visible=True):
    return {"clave": clave, "titulo": titulo, "tipo": tipo, "visible": visible}


def _json(valor, defecto):
    try:
        resultado = json.loads(valor or "")
    except (TypeError, ValueError):
        return defecto
    return resultado if isinstance(resultado, type(defecto)) else defecto


def _filtro_efector(efector):
    return efector if efector in ("HBI", "CASPH") else None


def _cargas_pdf(con):
    """({numero de OC: fecha de la última carga de su PDF}, {(oc, pos) de renglones tomados del PDF})."""
    cargas, renglones = {}, set()
    for fila in con.execute("SELECT clave, fecha, despues FROM evento WHERE tabla = 'oc' AND accion = 'IMPORTACION' ORDER BY id"):
        despues = _json(fila["despues"], {})
        if despues.get("fuente") == "pdf_oc":
            numero = _json(fila["clave"], {}).get("numero")
            cargas[numero] = fila["fecha"]
            renglones.update((numero, pos) for pos in despues.get("renglones") or [] if isinstance(pos, int))
    return cargas, renglones


COLUMNAS_EXPEDIENTES = [
    _col("id", "N°", "numero"), _col("tipo", "Tipo"), _col("efector", "Efector"), _col("estado", "Estado"),
    _col("oc", "OC"), _col("sap", "SAP"), _col("razon_social", "Proveedor"), _col("objeto", "Objeto", visible=False),
    _col("periodo", "Período"), _col("periodo_desde", "Período desde", "fecha", False),
    _col("periodo_hasta", "Período hasta", "fecha", False), _col("factura", "Factura"),
    _col("factura_fecha", "Fecha factura", "fecha", False), _col("factura_importe", "Importe factura", "moneda"),
    _col("remitos", "Remitos", visible=False), _col("sii", "SII", visible=False),
    _col("gde_expediente", "Expediente GDE"), _col("entrega", "Entrega", visible=False),
    _col("motivo_pendiente", "Motivo pendiente", visible=False), _col("fecha_seguimiento", "Seguimiento", "fecha", False),
    _col("motivo_anulacion", "Motivo anulación", visible=False), _col("creado", "Creado", "fecha_hora", False),
    _col("actualizado", "Actualizado", "fecha_hora"), _col("usuario", "Usuario", visible=False),
]


def tabla_expedientes(con, efector=None):
    sql = (
        "SELECT e.*, p.razon_social, oc.objeto, en.numero AS entrega_numero, en.nombre AS entrega_nombre "
        "FROM expediente e LEFT JOIN proveedor p ON p.sap = e.sap LEFT JOIN oc ON oc.numero = e.oc "
        "LEFT JOIN entrega en ON en.id = e.entrega_id"
    )
    parametros = []
    if _filtro_efector(efector):
        sql += " WHERE e.efector = ?"
        parametros.append(efector)
    sql += " ORDER BY e.id DESC"
    filas = []
    for fila in con.execute(sql, parametros):
        datos = _json(fila["datos"], {})
        factura = datos.get("factura") if isinstance(datos.get("factura"), dict) else {}
        remitos = [r.get("numero") for r in datos.get("remitos") or [] if isinstance(r, dict) and r.get("numero")]
        centavos = factura.get("centavos")
        entrega = ""
        if fila["entrega_numero"] is not None:
            entrega = "%s %s" % (fila["entrega_numero"], fila["entrega_nombre"] or "")
        filas.append({
            "id": fila["id"], "tipo": fila["tipo"], "efector": fila["efector"], "estado": fila["estado"],
            "oc": fila["oc"] or "", "sap": fila["sap"] or "", "razon_social": fila["razon_social"] or "",
            "objeto": fila["objeto"] or "", "periodo": fila["periodo"] or "", "periodo_desde": fila["periodo_desde"],
            "periodo_hasta": fila["periodo_hasta"], "factura": fila["factura"] or "",
            "factura_fecha": factura.get("fecha") or None,
            "factura_importe": centavos if isinstance(centavos, int) and not isinstance(centavos, bool) else None,
            "remitos": " / ".join(remitos), "sii": ((datos.get("sii") or {}).get("cod_tramite") or "")
            if isinstance(datos.get("sii"), dict) else "",
            "gde_expediente": ((datos.get("gde") or {}).get("expediente") or "") if isinstance(datos.get("gde"), dict) else "",
            "entrega": entrega.strip(), "motivo_pendiente": fila["motivo_pendiente"],
            "fecha_seguimiento": fila["fecha_seguimiento"], "motivo_anulacion": fila["motivo_anulacion"],
            "creado": fila["creado"], "actualizado": fila["actualizado"], "usuario": fila["usuario"],
        })
    return {"columnas": COLUMNAS_EXPEDIENTES, "filas": filas}


COLUMNAS_OC = [
    _col("numero", "OC"), _col("efector", "Efector"), _col("sap", "SAP"), _col("razon_social", "Proveedor"),
    _col("cuit", "CUIT", visible=False), _col("objeto", "Objeto"), _col("objeto_articulo", "Artículo", visible=False),
    _col("concepto_corto", "Concepto corto", visible=False), _col("tipo", "Tipo"), _col("comodato", "Comodato", "si_no", False),
    _col("centralizada", "Centralizada", "si_no", False), _col("ca", "CA"),
    _col("expediente_contratacion", "Expediente de contratación", visible=False), _col("gde_pdf_oc", "GDE del PDF", visible=False),
    _col("fecha_oc", "Fecha OC", "fecha", False), _col("vig_desde", "Vigencia desde", "fecha"),
    _col("vig_hasta", "Vigencia hasta", "fecha"), _col("prorroga", "Prórroga hasta", "fecha", False),
    _col("renglones", "Renglones", "numero"), _col("importe_centavos", "Importe total", "moneda"),
    _col("expedientes", "Expedientes", "numero"), _col("ultimo_periodo", "Último período", visible=False),
    _col("pdf_cargado", "PDF cargado", "fecha_hora"), _col("origen", "Origen", visible=False),
    _col("cerrada_sap", "Cerrada en SAP", "si_no", False), _col("excluida", "Excluida", "si_no", False),
    _col("ultima_importacion", "Última importación", "fecha_hora", False),
]


def tabla_oc(con, efector=None):
    sql = (
        "SELECT oc.*, p.razon_social, p.cuit, "
        "(SELECT COUNT(*) FROM renglon r WHERE r.oc = oc.numero) AS renglones, "
        "(SELECT COALESCE(SUM(r.importe_centavos), 0) FROM renglon r WHERE r.oc = oc.numero) AS importe_centavos, "
        "(SELECT COUNT(*) FROM expediente e WHERE e.oc = oc.numero AND e.estado != 'ANULADO') AS expedientes, "
        "(SELECT MAX(e.periodo) FROM expediente e WHERE e.oc = oc.numero AND e.estado != 'ANULADO') AS ultimo_periodo "
        "FROM oc LEFT JOIN proveedor p ON p.sap = oc.sap"
    )
    parametros = []
    if _filtro_efector(efector):
        sql += " WHERE oc.efector = ?"
        parametros.append(efector)
    sql += " ORDER BY oc.numero"
    cargas, _ = _cargas_pdf(con)
    filas = []
    for fila in con.execute(sql, parametros):
        dic = {c["clave"]: fila[c["clave"]] for c in COLUMNAS_OC if c["clave"] in fila.keys()}
        dic["razon_social"] = dic.get("razon_social") or ""
        dic["cuit"] = dic.get("cuit") or ""
        dic["ultimo_periodo"] = dic.get("ultimo_periodo") or ""
        dic["pdf_cargado"] = cargas.get(fila["numero"])
        if fila["tipo"] == "BIEN":  # los bienes no tienen períodos
            dic["vig_desde"] = dic["vig_hasta"] = dic["prorroga"] = None
        filas.append(dic)
    return {"columnas": COLUMNAS_OC, "filas": filas}


COLUMNAS_RENGLONES = [
    _col("oc", "OC"), _col("efector", "Efector"), _col("razon_social", "Proveedor"), _col("pos", "Renglón", "numero"),
    _col("codigo", "Código"), _col("descripcion", "Descripción"), _col("cantidad", "Cantidad", "cantidad"),
    _col("unidad", "Unidad"), _col("precio_centavos", "Precio unitario", "moneda"),
    _col("importe_centavos", "Importe", "moneda"), _col("desglose_cantidad", "Desglose: cantidad", "cantidad"),
    _col("desglose_unidad", "Desglose: unidad"), _col("desglose_precio_centavos", "Desglose: precio", "moneda"),
    _col("partida", "Partida", visible=False), _col("sap_entregado", "Entregado (SAP)", "cantidad"),
    _col("sap_facturado", "Facturado (SAP)", "cantidad", False), _col("sap_por_entregar", "Por entregar (SAP)", "cantidad"),
    _col("consumo_previo", "Consumo previo", "cantidad", False), _col("del_pdf", "Tomado del PDF", "si_no"),
    _col("revisar_desglose", "Revisar desglose", "si_no", False), _col("revisar_importe", "Revisar importe", "si_no", False),
    _col("exceso_sap", "Exceso SAP", "si_no", False), _col("es_correctivo", "Correctivo", "si_no", False),
    _col("excluida", "OC excluida", "si_no", False),
]


def tabla_renglones(con, efector=None):
    sql = ("SELECT r.*, oc.efector, oc.excluida, p.razon_social FROM renglon r JOIN oc ON oc.numero = r.oc "
           "LEFT JOIN proveedor p ON p.sap = oc.sap")
    parametros = []
    if _filtro_efector(efector):
        sql += " WHERE oc.efector = ?"
        parametros.append(efector)
    sql += " ORDER BY r.oc, r.pos"
    _, del_pdf = _cargas_pdf(con)
    filas = []
    for fila in con.execute(sql, parametros):
        dic = {c["clave"]: fila[c["clave"]] for c in COLUMNAS_RENGLONES if c["clave"] in fila.keys()}
        dic["razon_social"] = dic.get("razon_social") or ""
        dic["del_pdf"] = 1 if (fila["oc"], fila["pos"]) in del_pdf else 0
        filas.append(dic)
    return {"columnas": COLUMNAS_RENGLONES, "filas": filas}


TABLAS = {
    "expedientes": ("Expedientes", tabla_expedientes),
    "oc": ("Órdenes de compra", tabla_oc),
    "renglones": ("Renglones de OC", tabla_renglones),
}


def tabla(con, nombre, efector=None):
    if nombre not in TABLAS:
        raise TablaDesconocida("No existe la tabla %s." % nombre)
    titulo, funcion = TABLAS[nombre]
    resultado = funcion(con, efector)
    resultado["titulo"] = titulo
    return resultado


# --- Exportación ---------------------------------------------------------------

def _fecha_ar(texto):
    if not texto or len(str(texto)) < 10:
        return texto or ""
    t = str(texto)
    return "%s/%s/%s" % (t[8:10], t[5:7], t[0:4])


def _celda(tipo, valor):
    if valor is None or valor == "":
        return None
    if tipo == "moneda":
        return util.a_centavos(valor) if not isinstance(valor, int) else valor
    if tipo == "numero":
        try:
            return int(valor)
        except (TypeError, ValueError):
            return str(valor)
    if tipo == "cantidad":
        try:
            numero = Decimal(str(valor))
        except InvalidOperation:
            return str(valor)
        if numero == numero.to_integral_value():
            return int(numero)
        return format(numero, "f").replace(".", ",")
    if tipo == "fecha":
        return _fecha_ar(valor)
    if tipo == "fecha_hora":
        return _fecha_ar(valor) + (" " + str(valor)[11:16] if len(str(valor)) >= 16 else "")
    if tipo == "si_no":
        return "Sí" if valor in (1, True, "1") else "No"
    return str(valor)


def exportar_xlsx(pedido):
    """(bytes, nombre de archivo) de un .xlsx con lo que se ve en pantalla.

    `pedido`: {"nombre", "titulo", "filtros" (texto descriptivo), "columnas": [{"titulo", "tipo"}], "filas": [[...]]}.
    """
    if not isinstance(pedido, dict):
        raise ValueError("El pedido de exportación debe ser un objeto.")
    columnas = pedido.get("columnas")
    filas = pedido.get("filas")
    if not isinstance(columnas, list) or not columnas or not isinstance(filas, list):
        raise ValueError("No hay columnas ni filas para exportar.")
    if len(filas) > 50000:
        raise ValueError("Demasiadas filas para exportar (máximo 50.000).")
    titulos, tipos = [], []
    for columna in columnas:
        if not isinstance(columna, dict) or not isinstance(columna.get("titulo"), str):
            raise ValueError("Cada columna necesita su título.")
        tipo = columna.get("tipo") if columna.get("tipo") in TIPOS else "texto"
        titulos.append(columna["titulo"])
        tipos.append(tipo)
    datos = []
    for fila in filas:
        if not isinstance(fila, list) or len(fila) != len(columnas):
            raise ValueError("Cada fila debe tener un valor por columna.")
        datos.append([_celda(tipos[i], v) for i, v in enumerate(fila)])
    nombre = pedido.get("nombre") if pedido.get("nombre") in TABLAS else "tabla"
    titulo = str(pedido.get("titulo") or TABLAS.get(nombre, ("Tabla",))[0])
    filtros = str(pedido.get("filtros") or "").strip()
    if filtros:
        titulo += " (" + filtros + ")"
    moneda = [t for t, tipo in zip(titulos, tipos) if tipo == "moneda"]
    contenido = xlsx_escritor.contenido_xlsx(TABLAS.get(nombre, ("Tabla",))[0], xlsx_escritor.titulo_con_fecha(titulo),
                                            titulos, datos, moneda)
    return contenido, "%s-%s.xlsx" % (nombre, date.today().strftime("%Y%m%d"))

