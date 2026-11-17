"""Datos reales reutilizables por los tests (paso 8; se amplía en los pasos 13 y 21).

Todo se carga sobre la base temporal de tests/ayudas.py; nunca sobre datos/ del proyecto.
"""
from gestor import db, importar, negocio
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
