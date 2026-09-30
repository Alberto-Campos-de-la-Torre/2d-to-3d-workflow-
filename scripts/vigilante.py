"""Mantiene ComfyUI en pie: si deja de responder, lo reinicia.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\vigilante.py
  ...\\python.exe scripts\\vigilante.py --lan            (lo levanta accesible en la red)
  ...\\python.exe scripts\\vigilante.py --una-vez        (comprueba y sale, para el Programador)

No basta con mirar si el proceso existe. Ya paso una vez: la ventana de consola entro en
modo seleccion, Windows congelo el proceso en la siguiente escritura y el servidor dejo de
responder con el puerto abierto y el python vivo. Por eso se comprueba pidiendo una pagina
de verdad, no la lista de procesos.

Deja constancia en vigilante_log.txt de cada caida y cada arranque, que es lo que hace
falta para saber si pasa a menudo o fue una vez.
"""
import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(r"D:\AI3D")
REGISTRO = RAIZ / "vigilante_log.txt"
DIRECCION = "http://127.0.0.1:8188"
ARRANQUE = {False: RAIZ / "Iniciar_ComfyUI_3D.bat", True: RAIZ / "Iniciar_ComfyUI_LAN.bat"}


def anotar(texto):
    linea = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto)
    print(linea, flush=True)
    with REGISTRO.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def responde(tiempo=10):
    """Una peticion de verdad. El proceso puede estar vivo y el servidor colgado."""
    try:
        with urllib.request.urlopen(DIRECCION + "/system_stats", timeout=tiempo) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def procesos():
    """PIDs de ComfyUI, para poder matar uno colgado antes de levantar otro."""
    orden = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } | "
             "ForEach-Object { $_.ProcessId }")
    try:
        salida = subprocess.run(["powershell", "-NoProfile", "-Command", orden],
                                capture_output=True, text=True, timeout=30)
    except (subprocess.SubprocessError, OSError):
        return []
    return [int(x) for x in salida.stdout.split() if x.strip().isdigit()]


def levantar(lan):
    """Mata lo que haya colgado y arranca de nuevo."""
    for pid in procesos():
        anotar("matando el proceso colgado %d" % pid)
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    time.sleep(3)
    bat = ARRANQUE[bool(lan)]
    anotar("arrancando con %s" % bat.name)
    subprocess.Popen(["cmd", "/c", "start", "", str(bat)], cwd=str(RAIZ), shell=False)


def esperar_a_que_arranque(intentos=30, espera=5):
    for _ in range(intentos):
        time.sleep(espera)
        if responde():
            return True
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lan", action="store_true", help="levantarlo accesible desde la red local")
    p.add_argument("--una-vez", action="store_true",
                   help="comprobar y salir; pensado para el Programador de tareas")
    p.add_argument("--cada", type=int, default=60, help="segundos entre comprobaciones")
    args = p.parse_args()

    if args.una_vez:
        if responde():
            print("ComfyUI responde")
            return 0
        anotar("no responde: se reinicia")
        levantar(args.lan)
        if esperar_a_que_arranque():
            anotar("vuelve a responder")
            return 0
        anotar("NO consiguio arrancar; mira comfy_log.txt")
        return 1

    anotar("vigilante en marcha (cada %d s, %s)" % (args.cada, "LAN" if args.lan else "local"))
    caidas = 0
    try:
        while True:
            if not responde():
                caidas += 1
                anotar("no responde (caida numero %d): se reinicia" % caidas)
                levantar(args.lan)
                if esperar_a_que_arranque():
                    anotar("vuelve a responder")
                else:
                    anotar("NO consiguio arrancar; mira comfy_log.txt")
            time.sleep(args.cada)
    except KeyboardInterrupt:
        anotar("vigilante detenido a mano (%d caidas atendidas)" % caidas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
