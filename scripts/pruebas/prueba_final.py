"""Prueba final: las 10 imagenes de prueba por el sistema completo.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\prueba_final.py [carpeta]

Por cada imagen: geometria (TRELLIS.2) -> color -> solidificado -> paleta -> informe ->
grosor de pared -> STL y OBJ. Responde a la pregunta del negocio: cuantos encargos salen
imprimibles sin tocar nada a mano.

Deja `D:\\AI3D\\pruebas\\prueba_final.json` y un resumen en pantalla.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generar_3d import EXTENSIONES, peticion, subir_imagen, workflow

ENTRADA = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\AI3D\pruebas\entrada")
INFORME = Path(r"D:\AI3D\pruebas\prueba_final.json")
ALTURA_MM = 80.0


def construir(nombre_imagen, prefijo):
    grafo = workflow("trellis2", nombre_imagen, f"3d/final/{prefijo}", 20, 7.5, 0, 42, True, "#FFFFFF", True)
    # 73 = Paint Mesh: la malla ya solidificada con su color por vertice.
    grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
        "mesh": ["73", 0], "paleta": "", "colores": 4,
        "peso_luz": 0.25, "min_mancha": 0.3, "suavizar_bordes": 3}}
    grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
        "mesh": ["200", 0], "altura_mm": ALTURA_MM, "material": "PLA", "relleno": 15.0, "pared_mm": 1.2}}
    grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
        "mesh": ["201", 0], "grosor_min_mm": 1.2, "aviso_pct": 5.0, "muestras": 4000}}
    grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
        "mesh": ["202", 0], "nombre": f"final/{prefijo}", "guardar_obj": True, "poner_de_pie": True}}
    return grafo


def texto_de(salidas, nodo):
    datos = salidas.get(nodo, {}).get("text")
    return datos[0] if datos else ""


def numero(texto, patron, por_defecto=None):
    hallazgo = re.search(patron, texto)
    return float(hallazgo.group(1).replace(",", "")) if hallazgo else por_defecto


def ejecutar(ruta):
    nombre = subir_imagen(ruta)
    prefijo = re.sub(r"[^A-Za-z0-9_-]+", "_", ruta.stem)[:40]
    inicio = time.time()
    respuesta = peticion("/prompt", json.dumps({"prompt": construir(nombre, prefijo)}).encode(),
                         {"Content-Type": "application/json"})
    if respuesta.get("node_errors"):
        raise RuntimeError(json.dumps(respuesta["node_errors"])[:500])
    pid = respuesta["prompt_id"]
    while True:
        historial = peticion(f"/history/{pid}")
        if pid in historial:
            break
        time.sleep(3)
    estado = historial[pid].get("status", {})
    if estado.get("status_str") != "success":
        raise RuntimeError(json.dumps(estado.get("messages", []))[:800])

    salidas = historial[pid]["outputs"]
    solido = texto_de(salidas, "62")
    informe = texto_de(salidas, "201")
    grosor = texto_de(salidas, "202")
    paleta = texto_de(salidas, "200")

    agujeros = numero(solido, r"salida.*?Â·\s*([\d,]+)\s*agujeros", -1)
    finas = numero(grosor, r"zonas finas\s+([\d.]+)", -1)
    return {
        "imagen": ruta.name,
        "segundos": round(time.time() - inicio),
        "agujeros": int(agujeros) if agujeros is not None else -1,
        "cerrada": "cerrada" in informe and "ABIERTA" not in informe,
        "volumen_cm3": numero(informe, r"volumen\s+([\d.]+) cm3"),
        "peso_g": numero(informe, r"peso aprox\s+([\d.]+)"),
        "pct_zonas_finas": finas,
        "colores": len([l for l in paleta.split("\n")[1:] if l.strip()]),
        "solido": solido,
        "informe": informe,
        "grosor": grosor,
        "paleta": paleta,
    }


def main():
    imagenes = sorted(f for f in ENTRADA.iterdir() if f.suffix.lower() in EXTENSIONES)
    print(f"{len(imagenes)} imagenes Â· altura {ALTURA_MM:.0f} mm Â· guardando en output\\final\n", flush=True)
    resultados = []
    for i, ruta in enumerate(imagenes, 1):
        print(f"[{i}/{len(imagenes)}] {ruta.name} ...", flush=True)
        try:
            dato = ejecutar(ruta)
        except Exception as e:
            dato = {"imagen": ruta.name, "error": str(e)[:300]}
            print(f"    ERROR: {dato['error']}", flush=True)
        else:
            veredicto = "IMPRIMIBLE" if dato["cerrada"] and dato["pct_zonas_finas"] <= 5 else "REVISAR"
            print(f"    {veredicto} Â· {dato['segundos']} s Â· {dato['agujeros']} agujeros Â· "
                  f"{dato['pct_zonas_finas']}% finas Â· {dato['peso_g']} g Â· {dato['colores']} colores", flush=True)
        resultados.append(dato)
        INFORME.write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")

    buenos = [r for r in resultados if not r.get("error") and r.get("cerrada") and r.get("pct_zonas_finas", 100) <= 5]
    print(f"\n=== {len(buenos)} de {len(resultados)} imprimibles sin tocar nada ===")
    print(f"informe completo: {INFORME}")


if __name__ == "__main__":
    main()

