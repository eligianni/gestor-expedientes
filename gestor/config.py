"""Configuración local: config.json de la raíz del proyecto o el archivo que indica GESTOR_CONFIG."""
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """No se pudo leer el archivo de configuración."""


def ruta_config():
    """Ruta del config.json en uso: GESTOR_CONFIG si está definida y no vacía; si no, el de la raíz."""
    valor = os.environ.get("GESTOR_CONFIG")
    if valor:
        return Path(valor)
    return RAIZ / "config.json"


def cargar_config():
    """Lee el config.json en uso y agrega las claves internas _ruta y _dir."""
    ruta = ruta_config()
    if not ruta.is_file():
        raise ConfigError("No se encontró el archivo de configuración: %s" % ruta)
    with open(ruta, encoding="utf-8") as archivo:
        cfg = json.load(archivo)
    cfg["_ruta"] = str(ruta)
    cfg["_dir"] = str(ruta.parent)
    return cfg


def ruta(cfg, clave):
    """Ruta de cfg[clave]; si es relativa, se toma desde la carpeta del config.json."""
    valor = Path(cfg[clave])
    if valor.is_absolute():
        return valor
    return Path(cfg["_dir"]) / valor


def guardar_config(cfg):
    """Escribe la configuración en su archivo, sin las claves internas que empiezan con _."""
    destino = Path(cfg["_ruta"]) if cfg.get("_ruta") else ruta_config()
    limpio = {clave: valor for clave, valor in cfg.items() if not clave.startswith("_")}
    with open(destino, "w", encoding="utf-8") as archivo:
        json.dump(limpio, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
