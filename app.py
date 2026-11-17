"""Entry point del gestor de expedientes: python app.py [--no-browser] [--port N] [--check]."""
import argparse
import json
import sys
import threading
import webbrowser

from gestor import APP_ID, config, server


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
