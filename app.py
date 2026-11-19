"""Entry point del gestor de expedientes: python app.py [--no-browser] [--port N] [--check]."""
import argparse
import json
import sys
import threading
import time
import webbrowser

from gestor import APP_ID, config, db, server


def _check(cfg):
    httpd = server.crear_servidor(0, cfg)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    try:
        salud = server.consultar_salud(httpd.server_address[1], timeout=10)
    finally:
        httpd.shutdown()
        httpd.server_close()
    print(json.dumps(salud))
    return 0 if salud is not None and salud.get("app") == APP_ID else 1


INTERVALO_BACKUP_DIARIO = 30 * 60  # segundos entre controles de la copia diaria


def _backup_diario(cfg):
    """Hace la copia del día si todavía no existe; un fallo no corta el programa (se reintenta en el próximo control)."""
    try:
        return db.backup_diario(
            config.ruta(cfg, "base_datos"),
            config.ruta(cfg, "carpeta_backups"),
            int(cfg.get("backups_diarios_a_conservar", 90)),
        )
    except Exception:  # noqa: BLE001 — se ve en Configuración (última copia diaria)
        return None


def _programar_backups_diarios(cfg):
    """Mientras el programa está abierto, cada media hora se fija si ya está la copia de hoy (cubre pasar la medianoche)."""
    def bucle():
        while True:
            _backup_diario(cfg)
            time.sleep(INTERVALO_BACKUP_DIARIO)

    threading.Thread(target=bucle, name="backup-diario", daemon=True).start()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gestor de expedientes de pago (HBI / CASPH)")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    parser.add_argument("--port", type=int, help="usar solo este puerto")
    parser.add_argument("--check", action="store_true", help="prueba de humo: levanta, pide /api/salud y sale")
    args = parser.parse_args(argv)

    try:
        cfg = config.cargar_config()
    except config.ConfigError as error:
        print(str(error), file=sys.stderr)
        return 1

    if args.check:
        return _check(cfg)

    puerto, ya_corriendo = server.elegir_puerto(
        args.port or cfg["puerto_preferido"],
        args.port or cfg["puerto_maximo"],
    )
    url = "http://127.0.0.1:%d/" % puerto
    if ya_corriendo:
        webbrowser.open(url)
        return 0

    httpd = server.crear_servidor(puerto, cfg)
    try:
        db.hacer_backup(
            config.ruta(cfg, "base_datos"),
            config.ruta(cfg, "carpeta_backups"),
            cfg["backups_a_conservar"],
        )
    except Exception:  # noqa: BLE001 — un backup fallido no impide arrancar; se ve en /api/base/estado
        pass
    _programar_backups_diarios(cfg)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
