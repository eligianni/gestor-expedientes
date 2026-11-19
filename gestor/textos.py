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


# --- Nota a Central (centralizadas) ------------------------------------------

def periodo_nota_central(ctx):
    """Mes calendario → "08-2026"; período específico → "dd/mm/aaaa al dd/mm/aaaa"."""
    _requerir(ctx, "periodo")
    if int(ctx.get("dia_inicio") or 1) == 1:
        anio, mes = ctx["periodo"].split("-")
        return "%s-%s" % (mes, anio)
    if not ctx.get("periodo_desde") or not ctx.get("periodo_hasta"):
        raise TextoIncompleto("Faltan las fechas desde y hasta del período.")
    return "%s al %s" % (util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_desde"])),
                         util.ddmmaaaa(util.fecha_desde_texto(ctx["periodo_hasta"])))


def nota_central(ctx):
    """Nota a Central de una centralizada: {"referencia", "cuerpo"}; el cuerpo lista la documentación embebida."""
    _requerir(ctx, "razon", "oc", "periodo")
    if not ctx.get("expediente_contratacion"):
        raise TextoIncompleto("Falta el expediente de la contratación en la OC %s." % ctx["oc"])
    periodo = periodo_nota_central(ctx)
    referencia = "VALIDACIÓN DE BIENES Y SERVICIOS %s - %s, período %s" % (
        ctx["razon"], ctx["expediente_contratacion"], periodo)
    cuerpo = (
        "Se envían como archivos embebidos la validación del servicio y remito correspondientes al proveedor %s, "
        "del %s, con orden de compra %s, período %s." % (ctx["razon"], ctx["expediente_contratacion"], ctx["oc"], periodo)
    )
    cuerpo += "\nDocumentación embebida:" + "".join("\n- %s" % doc for doc in ctx.get("doc_requerida_central") or [])
    return {"referencia": referencia, "cuerpo": cuerpo}


# --- Mantenimiento correctivo ------------------------------------------------

def referencia_correctivo(ctx):
    """<sap> <razon> - OC <oc> - <procedimiento> - <objeto> - MANTENIMIENTO CORRECTIVO - <objeto_correctivo>."""
    _requerir(ctx, "sap", "razon", "oc")
    faltan = [nombre for clave, nombre in (
        ("procedimiento", "el procedimiento del correctivo"),
        ("objeto", "el objeto de la contratación de la OC"),
        ("objeto_correctivo", "el objeto del correctivo"),
    ) if not (ctx.get(clave) or "").strip()]
    if faltan:
        raise TextoIncompleto("Falta cargar " + ", ".join(faltan) + ".")
    return "%s %s - OC %s - %s - %s - MANTENIMIENTO CORRECTIVO - %s" % (
        ctx["sap"], ctx["razon"], ctx["oc"], ctx["procedimiento"].strip(), ctx["objeto"].strip(),
        ctx["objeto_correctivo"].strip())


def informe_economico(ctx):
    """Informe económico del correctivo: líneas separadas por \n (presupuestos, diferencia y monto a convalidar)."""
    _requerir(ctx, "sap", "razon", "oc")
    if not (ctx.get("objeto_correctivo") or "").strip():
        raise TextoIncompleto("Falta cargar el objeto del correctivo.")
    montos = [int(p["centavos"]) for p in ctx.get("presupuestos") or []]
    if len(montos) < 2:
        raise TextoIncompleto("Cargá al menos dos presupuestos.")
    if ctx.get("monto_convalidado") in (None, ""):
        raise TextoIncompleto("Falta cargar el monto a convalidar.")
    if not ctx.get("importe_renglon_correctivo"):
        raise TextoIncompleto("Marcá en la OC %s el renglón de mantenimiento correctivo." % ctx["oc"])
    menor, mayor = min(montos), max(montos)
    monto, importe = int(ctx["monto_convalidado"]), int(ctx["importe_renglon_correctivo"])
    lineas = [
        "INFORME ECONÓMICO - MANTENIMIENTO CORRECTIVO",
        "Orden de Compra N° %s - %s (SAP %s) - %s" % (ctx["oc"], ctx["razon"], ctx["sap"], ctx["objeto_correctivo"].strip()),
        "Presupuesto menor: $ %s" % util.formato_pesos(menor),
        "Presupuesto mayor: $ %s" % util.formato_pesos(mayor),
        "Diferencia entre presupuestos: $ %s (%d %%)." % (
            util.formato_pesos(mayor - menor), util.porcentaje_entero(mayor - menor, menor)),
        "Monto a convalidar frente al renglón de correctivo: $ %s de $ %s (%d %%)." % (
            util.formato_pesos(monto), util.formato_pesos(importe), util.porcentaje_entero(monto, importe)),
    ]
    return "\n".join(lineas)


# --- Pago eventual (paso 29) ---------------------------------------------------

def caratula_eventual(ctx):
    """`<SIGLA> - PAGO EVENTUAL - <razon> - FC N° <factura>`."""
    _requerir(ctx, "razon", "factura")
    sigla = ctx.get("sigla") or ctx.get("efector") or "HBI"
    return "%s - PAGO EVENTUAL - %s - FC N° %s" % (sigla, ctx["razon"], ctx["factura"])


_REFERENCIA_EVENTUAL = ("SOLICITUD PAGO EVENTUAL - [N° EXPEDIENTE PRINCIPAL] - [ESTABLECIMIENTO/HOSPITAL] - "
                        "[NOMBRE DEL PROVEEDOR]")

# Párrafos literales de §5 "Solicitud de pago eventual"; el segundo elemento dice de qué dato sale cada [N° DE ORDEN].
_PARRAFOS_EVENTUAL = (
    ('Por la presente se solicita el pago eventual de la Factura tipo "[B/C]" N° [NÚMERO DE FACTURA], de fecha '
     "[FECHA DE EMISIÓN DE FACTURA], por la suma total de $ [MONTO EN NÚMEROS].- (PESOS [MONTO EN LETRAS] CON [XX]/100 "
     "CENTAVOS), correspondiente al período del [FECHA INICIO] al [FECHA FIN], del proveedor [RAZÓN SOCIAL DEL PROVEEDOR] "
     "(SAP [N SAP]), vinculada al expediente [N° EXPEDIENTE], a través del [N° DOCUMENTO FINANCIERO/DOCFI], vinculado en "
     "orden [N° DE ORDEN].", "orden_docfi"),
    ("La citada factura corresponde al [TIPO DE SERVICIO, EJ: MANTENIMIENTO PREVENTIVO DE LOS ASCENSORES] pertenecientes "
     "al [NOMBRE DEL ESTABLECIMIENTO DETALLADO], tal como se describe en el remito N° [NÚMERO DE REMITO] perteneciente al "
     "periodo [FECHA INICIO] al [FECHA FIN] tal cual lo describe la factura, vinculado mediante [N° DOCUMENTO REMITO] en "
     "orden [N° DE ORDEN].", "orden_remito"),
    ("Las tareas específicas de [TIPO DE SERVICIO] se encuentran detalladas en el informe técnico brindado por [NOMBRE DEL "
     "PROVEEDOR], el cual se encuentra embebido en la [N° PROVIDENCIA INFORME], orden [N° DE ORDEN]. La mencionada "
     "providencia fue confeccionada y firmada por el [CARGO DEL RESPONSABLE TÉCNICO], [NOMBRE Y APELLIDO DEL RESPONSABLE], "
     "quien da conformidad e informa sobre el correcto funcionamiento de los equipos al día de la fecha.", "orden_informe"),
    ("De la consulta efectuada en el CUP - Padrón de Prestadores y Proveedores del Instituto, se verifica que la firma "
     "[RAZÓN SOCIAL DEL PROVEEDOR] (SAP [CÓDIGO SAP]), titular de la CUIT N° [NÚMERO DE CUIT], no registra suspensión ni "
     "inhabilitación para contratar, resultando su estado válido.", None),
    ("La Orden de Compra N° [NÚMERO DE ORDEN DE COMPRA] se encontraba vencida el día [FECHA DE VENCIMIENTO], habiendo sido "
     "tramitada por el expediente [N° EXPEDIENTE ANTERIOR]. No obstante, el proveedor siguió prestando el servicio, "
     "manteniéndose el precio y las bases y condiciones de la contratación. Asimismo, se solicitó la prórroga de dicha "
     "Orden de Compra mediante la [N° PROVIDENCIA PRÓRROGA], en orden [N° DE ORDEN] del citado expediente.",
     "orden_prorroga"),
    ("Asimismo, se deja constancia de que la presente tramitación cuenta con la correspondiente autorización de la "
     "[NOMBRE DE LA GERENCIA COMPETENTE], conforme a lo establecido en la [N° NOTA AUTORIZACIÓN], orden [N° DE ORDEN], "
     "mediante la cual se habilita la continuidad del servicio bajo la modalidad de pago eventual, en función de las "
     "razones expuestas en las actuaciones.", "orden_autorizacion"),
    ("Finalmente, se deja constancia de que este Efector no ha cursado durante el corriente año ningún pedido de pago "
     "eventual a la firma mencionada.", None),
    ("Con el Visto Bueno de esta Dirección, y atento a la urgencia y necesidad del caso, por no encontrarse la prestación "
     "bajo marco contractual, se giran las presentes actuaciones para su consideración y prosecución del trámite.", None),
)

# [CAMPO] → clave del dato (en ctx["eventual"] o en ctx).
_CAMPOS_EVENTUAL = {
    "N° EXPEDIENTE PRINCIPAL": "expediente",
    "N° EXPEDIENTE": "expediente",
    "ESTABLECIMIENTO/HOSPITAL": "establecimiento",
    "NOMBRE DEL PROVEEDOR": "razon",
    "RAZÓN SOCIAL DEL PROVEEDOR": "razon",
    "N SAP": "sap",
    "CÓDIGO SAP": "sap",
    "B/C": "tipo_factura",
    "NÚMERO DE FACTURA": "factura",
    "FECHA DE EMISIÓN DE FACTURA": "fecha_factura",
    "FECHA INICIO": "periodo_desde",
    "FECHA FIN": "periodo_hasta",
    "N° DOCUMENTO FINANCIERO/DOCFI": "docfi",
    "TIPO DE SERVICIO, EJ: MANTENIMIENTO PREVENTIVO DE LOS ASCENSORES": "tipo_servicio",
    "TIPO DE SERVICIO": "tipo_servicio",
    "NOMBRE DEL ESTABLECIMIENTO DETALLADO": "establecimiento_detallado",
    "NÚMERO DE REMITO": "remito",
    "N° DOCUMENTO REMITO": "documento_remito",
    "N° PROVIDENCIA INFORME": "providencia_informe",
    "CARGO DEL RESPONSABLE TÉCNICO": "cargo_responsable",
    "NOMBRE Y APELLIDO DEL RESPONSABLE": "responsable",
    "NÚMERO DE CUIT": "cuit",
    "NÚMERO DE ORDEN DE COMPRA": "orden_compra",
    "FECHA DE VENCIMIENTO": "vencimiento_oc",
    "N° EXPEDIENTE ANTERIOR": "expediente_anterior",
    "N° PROVIDENCIA PRÓRROGA": "providencia_prorroga",
    "NOMBRE DE LA GERENCIA COMPETENTE": "gerencia",
    "N° NOTA AUTORIZACIÓN": "nota_autorizacion",
}
_FECHAS_EVENTUAL = ("fecha_factura", "periodo_desde", "periodo_hasta", "vencimiento_oc")
_RE_CAMPO = re.compile(r"\[([^\]]+)\]")


def _completar_eventual(plantilla, datos, clave_orden):
    def reemplazo(m):
        campo = m.group(1)
        if campo in ("MONTO EN NÚMEROS", "MONTO EN LETRAS", "XX"):
            centavos = datos.get("centavos")
            if centavos in (None, ""):
                raise TextoIncompleto("Falta %s en la solicitud de pago eventual." % campo)
            pesos, cc = divmod(int(centavos), 100)
            if campo == "MONTO EN NÚMEROS":
                return util.formato_pesos(centavos)
            return letras.numero_a_letras(pesos) if campo == "MONTO EN LETRAS" else "%02d" % cc
        clave = clave_orden if campo == "N° DE ORDEN" else _CAMPOS_EVENTUAL[campo]
        valor = datos.get(clave) if clave else None
        valor = "" if valor is None else str(valor).strip()
        if not valor:
            raise TextoIncompleto("Falta %s en la solicitud de pago eventual." % campo)
        if clave in _FECHAS_EVENTUAL:
            valor = util.ddmmaaaa(util.fecha_desde_texto(valor))
        return valor
    return _RE_CAMPO.sub(reemplazo, plantilla)


def solicitud_pago_eventual(ctx):
    """{"referencia", "parrafos": [8 strings]}: los párrafos P1–P8 de §5 con cada [CAMPO] reemplazado por su dato."""
    datos = dict(ctx)
    datos.update({k: v for k, v in (ctx.get("eventual") or {}).items() if v not in (None, "")})
    return {
        "referencia": _completar_eventual(_REFERENCIA_EVENTUAL, datos, None),
        "parrafos": [_completar_eventual(plantilla, datos, orden) for plantilla, orden in _PARRAFOS_EVENTUAL],
    }


# --- Servicios del CASPH: AySA y Edenor (paso 30) -----------------------------------

_PARRAFO_RESOL_CASPH = (
    "Atento a que por el artículo 5 de la RESOL-2023-926-INSSJP-DE#INSSJP se estableció que el Centro Ambulatorio de "
    "Salud PAMI Hurlingham, funcionará transitoriamente como una unidad orgánica anexa del Hospital de Alta complejidad "
    "del Bicentenario Ituzaingó dependiente de la Gerencia de Efectores Sanitarios Propios, exclusivamente para proveer "
    "los bienes y servicios esenciales necesarios que permitan su efectivo y habitual funcionamiento. Sin más, se eleva "
    "para su intervención."
)


def autorizacion_servicio_casph(empresa, factura, centavos, mes, anio, expediente):
    """Autorización de pago de AySA o Edenor del CASPH: dos párrafos (el segundo, el de la RESOL, es igual en ambos)."""
    pesos, cc = divmod(int(centavos), 100)
    en_letras = letras.numero_a_letras(pesos)
    monto = util.formato_pesos(centavos)
    mes = str(mes).upper()
    if empresa == "AYSA":
        primero = (
            "Por medio de la presente se autoriza el pago de la factura N° %s de la empresa AySA (AGUA Y SANEAMIENTOS "
            "ARGENTINOS S.A.), SAP 70262, por un monto de PESOS %s con %02d/100 CENTAVOS ($ %s-) correspondiente al mes "
            "de %s %s, por el servicio de CLOACA del Centro Ambulatorio de Salud PAMI Hurlingham de acuerdo a la factura "
            "vinculada al %s." % (factura, en_letras, cc, monto, mes, anio, expediente)
        )
    elif empresa == "EDENOR":
        primero = (
            "Por medio de la presente se autoriza el pago de la factura N° %s de la EMPRESA DISTRIBUIDORA Y "
            "COMERCIALIZADORA NORTE S.A. por un monto de PESOS %s CON %02d/100 CENTAVOS ($ %s-), correspondiente al mes "
            "de %s %s, por el servicio de provisión de energía eléctrica del Centro Ambulatorio de Salud PAMI Hurlingham, "
            "de acuerdo a la factura vinculada al expediente %s." % (factura, en_letras, cc, monto, mes, anio, expediente)
        )
    else:
        raise ValueError("Empresa desconocida: %r (se espera AYSA o EDENOR)." % (empresa,))
    return [primero, _PARRAFO_RESOL_CASPH]


# --- Textos para SAP -------------------------------------------------------

def _fecha_sap_iso(iso):
    return util.fecha_sap(util.fecha_desde_texto(iso))


def textos_sap(ctx, limite):
    """Ingreso, contabilizada y entrada (MIGO / ML81N) del expediente."""
    _requerir(ctx, "oc", "periodo")
    concepto = (ctx.get("concepto_corto") or "").strip()
    if not concepto:
        raise TextoIncompleto("Falta el concepto corto (Texto SAP) en la OC %s." % ctx["oc"])
    if ctx.get("centavos") in (None, ""):
        raise TextoIncompleto("Falta cargar el importe de la factura.")
    if not ctx.get("fecha_base_remitos"):
        raise TextoIncompleto("Falta cargar al menos un remito con fecha.")
    sigla = ctx.get("sigla") or ctx.get("efector") or "HBI"
    anio, mes = ctx["periodo"].split("-")
    mm_barra_aa = util.mm_barra_aa(ctx["periodo"])
    fecha_documento = "01.%s.%s" % (mes, anio)
    texto = "%s - OC %s - %s - %s" % (sigla, ctx["oc"], concepto, mm_barra_aa)
    largo = len(texto)
    if int(ctx.get("dia_inicio") or 1) == 1:
        periodo = "%s/%s" % (mes, anio)
    else:
        if not ctx.get("periodo_desde") or not ctx.get("periodo_hasta"):
            raise TextoIncompleto("Faltan las fechas desde y hasta del período.")
        periodo = "%s - %s" % (_fecha_sap_iso(ctx["periodo_desde"]), _fecha_sap_iso(ctx["periodo_hasta"]))
    return {
        "ingreso": {
            "fecha_documento": fecha_documento,
            "importe": util.formato_pesos(int(ctx["centavos"])),
            "texto": texto,
            "largo_texto": largo,
            "aviso_largo": ("El Texto tiene %d caracteres; el límite configurado es %d." % (largo, limite)
                            if largo > limite else None),
            "asignacion": "OC %s" % ctx["oc"],
            "txt_cabecera": "0000-0000-0000000-0",
            "clase": "KE",
        },
        "contabilizada": {"txt_cabecera": "%s %s OC %s" % (mm_barra_aa, sigla, ctx["oc"])},
        "entrada": {
            "transaccion": "MIGO" if ctx.get("tipo_oc") in ("BIEN", "PROVISION") else "ML81N",
            "fecha_documento": fecha_documento,
            "fecha_contabilizacion": _fecha_sap_iso(ctx["fecha_base_remitos"]),
            "renglones": [dict(r) for r in ctx.get("cantidades") or []],
            "periodo": periodo,
            "texto_breve": "%s - %s" % (concepto, mm_barra_aa),
        },
    }
