"""Datos reales reutilizables por los tests (paso 8; se amplía en los pasos 13 y 21).

Todo se carga sobre la base temporal de tests/ayudas.py; nunca sobre datos/ del proyecto.
"""
from gestor import comprobantes, db, importar, negocio, util
from tests import ayudas

# OC EFIA cargada a mano: todavía no figura en el z_compras2.
OC_EFIA_MANUAL = {
    "numero": "4500555861",
    "efector": "HBI",
    "sap": "77170",
    "razon_social": "GRUPO EFIA S.R.L.",
    "fecha_oc": "2025-09-04",
    "vig_desde": "2025-10-01",
    "vig_hasta": "2026-09-30",
    "ca": "195-2025",
    "expediente_contratacion": "EX-2025-70356979- -INSSJP-GESP#INSSJP",
    "objeto": "servicio de control integral de plagas, fumigación, desinsectación y desratización",
    "objeto_articulo": "al",
    "concepto_corto": "SERV. FUMIGACIÓN",
    "dia_inicio_periodo": 1,
    "renglones": [
        {
            "pos": 1,
            "descripcion": "SERV INTEGRAL CONTROL DE PLAGAS",
            "cantidad": "1",
            "unidad": "UN",
            "precio_centavos": 1102491000,
            "importe_centavos": 1102491000,
            "desglose_cantidad": "9",
            "desglose_unidad": "MES",
            "desglose_precio_centavos": 122499000,
        },
    ],
}

OC_BIOFAB = "4500587121"
OC_MACATEX = "4500594643"


def cargar_efia(con):
    """Da de alta la OC manual EFIA (si no existe) y devuelve su ficha."""
    if db.leer_fila(con, "oc", {"numero": OC_EFIA_MANUAL["numero"]}) is None:
        return negocio.crear_oc_manual(con, OC_EFIA_MANUAL)
    return negocio.ficha_oc(con, OC_EFIA_MANUAL["numero"])


def importar_hbi_2026(con):
    """Importa z_compras2_hbi_2026.xlsx como HBI y devuelve el informe."""
    parametros = db.leer_parametros(con)
    return importar.importar(con, ayudas.XLSX_HBI_2026, "HBI", parametros, archivo=ayudas.XLSX_HBI_2026.name)


def _asegurar_importado(con, numero):
    if db.leer_fila(con, "oc", {"numero": numero}) is None:
        importar_hbi_2026(con)


def preparar_biofab(con):
    """Importa y deja la OC BIO FAB 4500587121 con comodato y su objeto cargado a mano."""
    _asegurar_importado(con, OC_BIOFAB)
    oc = db.leer_fila(con, "oc", {"numero": OC_BIOFAB})
    return negocio.actualizar_oc(con, OC_BIOFAB, oc["version"], {
        "comodato": 1,
        "objeto": "provisión de inmunoensayo por fluorescencia",
        "objeto_articulo": "a la",
    })


def preparar_macatex(con):
    """Importa y deja la OC MACATEX 4500594643 tal como viene (objeto vacío)."""
    _asegurar_importado(con, OC_MACATEX)
    return negocio.ficha_oc(con, OC_MACATEX)


# --- Expedientes reales armados (paso 13) -----------------------------------

def _remito(numero, fecha, items=(), equipo=False):
    return {
        "numero": numero, "fecha": fecha, "fecha_firma": None, "es_equipo_comodato": equipo, "aclara_periodo": False,
        "items": [{"pos": pos, "cantidad": cantidad, "codigo": codigo} for pos, cantidad, codigo in items],
    }


def _factura(numero, fecha, centavos, cae, vto_cae=None):
    return {
        "numero": numero, "fecha": fecha, "centavos": centavos, "cae": cae, "vto_cae": vto_cae,
        "destinatario": "INSSJP", "domicilio": "Perú 169 CABA",
    }


def _armar(con, oc, remito_principal, remitos, factura, carpeta_sii):
    """Alta del expediente, período sugerido por el remito principal y carga de remitos, factura y SII."""
    exp = negocio.crear_expediente(con, {"tipo": "COMUN", "oc": oc})
    linea = "%s;%s" % (remito_principal["numero"], util.ddmmaaaa(util.fecha_desde_texto(remito_principal["fecha"])))
    exp = negocio.pegar_remitos(con, exp["id"], exp["version"], linea)
    sii = comprobantes.analizar_texto_sii(ayudas.texto_fixture(carpeta_sii, "0004_IF-*.txt"))
    return negocio.actualizar_expediente(con, exp["id"], exp["version"], {
        "datos": {"remitos": remitos, "factura": factura, "sii": sii},
    })


EX_EFIA = "EX-2026-89654857- -INSSJP-GESP#INSSJP"
EX_BIOFAB = "EX-2026-94963848- -INSSJP-GESP#INSSJP"
EX_MACATEX = "EX-2026-99349179- -INSSJP-GESP#INSSJP"


def caso(nombre, centavos=None, con_equipo=True):
    """Datos de cada expediente real: oc, remito principal, remitos (con ítems), factura, carpeta del SII y EX."""
    if nombre == "efia":
        remito = _remito("00001-00029461", "2026-08-31", [(1, "1", "")])
        factura = _factura("0003B00031812", "2026-09-10", 122499000 if centavos is None else centavos, "86372407008783")
        return {"oc": OC_EFIA_MANUAL["numero"], "remito": remito, "remitos": [remito], "factura": factura,
                "carpeta": "EX-2026-89654857_EFIA", "ex": EX_EFIA}
    if nombre == "biofab":
        remito = _remito("0001-00003354", "2026-08-25",
                         [(1, "1000", ""), (2, "400", "5002383"), (3, "200", ""), (4, "150", "")])
        remitos = [remito] + ([_remito("0001-00003281", "2026-08-25", equipo=True)] if con_equipo else [])
        factura = _factura("00002B00003908", "2026-09-11", 2109500000, "86372594419176", "2026-09-21")
        return {"oc": OC_BIOFAB, "remito": remito, "remitos": remitos, "factura": factura,
                "carpeta": "EX-2026-94963848_BIOFAB", "ex": EX_BIOFAB}
    if nombre == "macatex":
        remito = _remito("0001-00004409", "2026-09-07",
                         [(1, "2000", ""), (2, "650", ""), (3, "600", ""), (4, "1400", ""), (5, "1400", ""), (6, "550", "")])
        factura = _factura("0002B00000160", "2026-10-09", 3388160000, "86416949757962", "2026-10-19")
        return {"oc": OC_MACATEX, "remito": remito, "remitos": [remito], "factura": factura,
                "carpeta": "EX-2026-99349179_MACATEX", "ex": EX_MACATEX}
    raise ValueError("Caso desconocido: %s" % nombre)


def _armar_caso(con, datos):
    return _armar(con, datos["oc"], datos["remito"], datos["remitos"], datos["factura"], datos["carpeta"])


def armar_expediente_efia(con, centavos=122499000):
    """EFIA 2026-08: remito 00001-00029461 (1 mes), factura 0003B00031812, CAE sin vencimiento."""
    cargar_efia(con)
    return _armar_caso(con, caso("efia", centavos=centavos))


def armar_expediente_biofab(con, con_equipo=True):
    """BIO FAB 2026-08: remito 0001-00003354 (código 5002383 en el renglón 2) y, si corresponde, el del equipo."""
    preparar_biofab(con)
    return _armar_caso(con, caso("biofab", con_equipo=con_equipo))


def armar_expediente_macatex(con):
    """MACATEX 2026-09: remito 0001-00004409 con las cantidades totales de los 6 renglones."""
    preparar_macatex(con)
    return _armar_caso(con, caso("macatex"))


# --- Flujo completo por HTTP (paso 21) ---------------------------------------

def _ok(resp, que):
    if resp.estado != 200:
        raise AssertionError("%s: HTTP %d %s" % (que, resp.estado, resp.texto()))
    return resp.json()["datos"]


def _preparar_oc_por_api(servidor, nombre, numero):
    if servidor.get("/api/oc/%s" % numero).estado == 404:
        if nombre == "efia":
            _ok(servidor.post("/api/oc", OC_EFIA_MANUAL), "alta de la OC EFIA")
        else:
            _ok(servidor.subir("/api/importar/confirmar", ayudas.XLSX_HBI_2026, {"efector": "HBI"}), "importación HBI 2026")
    if nombre == "biofab":
        oc = _ok(servidor.get("/api/oc/%s" % numero), "ficha BIO FAB")["oc"]
        if not oc["comodato"] or not oc["objeto"]:
            _ok(servidor.put("/api/oc/%s" % numero, {"version": oc["version"], "cambios": {
                "comodato": 1, "objeto": "provisión de inmunoensayo por fluorescencia", "objeto_articulo": "a la",
            }}), "campos manuales BIO FAB")


def flujo_por_api(servidor, nombre):
    """Arma por HTTP el expediente real `nombre` (efia, biofab, macatex) hasta tener GDE cargados; devuelve el id."""
    datos = caso(nombre)
    _preparar_oc_por_api(servidor, nombre, datos["oc"])
    exp = _ok(servidor.post("/api/expedientes", {"tipo": "COMUN", "oc": datos["oc"]}), "alta del expediente")
    for remito in datos["remitos"]:
        linea = "%s;%s" % (remito["numero"], util.ddmmaaaa(util.fecha_desde_texto(remito["fecha"])))
        exp = _ok(servidor.post("/api/expedientes/%d/remitos/pegar" % exp["id"], {
            "version": exp["version"], "texto": linea, "es_equipo_comodato": remito["es_equipo_comodato"],
        }), "pegado del remito %s" % remito["numero"])
    exp = _ok(servidor.put("/api/expedientes/%d" % exp["id"], {
        "version": exp["version"], "cambios": {"datos": {"remitos": datos["remitos"]}},
    }), "cantidades de los remitos")
    texto = ayudas.texto_fixture(datos["carpeta"], "0004_IF-*.txt")
    sii = _ok(servidor.post("/api/comprobantes/analizar", {"texto": texto}), "análisis del texto SII")
    exp = _ok(servidor.put("/api/expedientes/%d" % exp["id"], {
        "version": exp["version"], "cambios": {"datos": {"factura": datos["factura"], "sii": sii}},
    }), "factura y SII")
    exp = _ok(servidor.put("/api/expedientes/%d/gde" % exp["id"], {"version": exp["version"], "gde": {"expediente": datos["ex"]}}),
              "números GDE")
    return exp["id"]
