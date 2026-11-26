"""Del peso de la pieza al precio que se le dice al cliente.

Los numeros del negocio (lo que cuesta el kilo de filamento, la hora de maquina, el margen)
NO van en el codigo ni en el repositorio: se leen de config_local.json, que no se publica.
Lo que hay aqui son valores de ejemplo para que funcione el primer dia; hay que cambiarlos
por los tuyos o el presupuesto no significa nada.

Ejemplo en config_local.ejemplo.json:

  "precio_filamento_kg": 25.0,
  "moneda": "USD",
  "coste_hora_maquina": 1.20,
  "gramos_por_hora": 14.0,
  "preparacion": 3.00,
  "margen": 1.6
"""
import math

POR_DEFECTO = {
    "precio_filamento_kg": 25.0,   # lo que te cuesta a ti el kilo
    "moneda": "USD",
    "coste_hora_maquina": 1.20,    # amortizacion + luz + mantenimiento, por hora
    "gramos_por_hora": 14.0,       # ritmo real de tu impresora; sube si imprimes rapido
    "preparacion": 3.00,           # fijo por encargo: limpiar, quitar soportes, empaquetar
    "margen": 1.6,                 # lo que multiplicas sobre el coste
    "fallos_pct": 8.0,             # % de impresiones que se pierden, repartido en el precio
}


def ajustes():
    """Los valores del negocio, de config_local.json, con los de ejemplo de respaldo."""
    from .prompt_ia import ajustes as leer

    datos = dict(POR_DEFECTO)
    guardados = leer()
    for clave in POR_DEFECTO:
        if clave in guardados:
            datos[clave] = guardados[clave]
    datos["configurado"] = all(clave in guardados for clave in POR_DEFECTO)
    return datos


def calcular(peso_g, cfg=None, soportes_pct=0.0):
    """Desglose del precio de una pieza. 'soportes_pct' es el material que se tira."""
    cfg = dict(ajustes() if cfg is None else cfg)
    def numero(nombre, valor, positivo=False):
        try:
            n = float(valor)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(nombre + ": debe ser un numero finito") from None
        if not math.isfinite(n) or n < 0 or (positivo and n == 0):
            raise ValueError(nombre + (": debe ser mayor que cero y finito" if positivo else ": debe ser no negativo y finito"))
        return n
    peso = numero("peso_g", peso_g)
    soportes = numero("soportes_pct", soportes_pct)
    for clave in POR_DEFECTO:
        if clave != "moneda":
            cfg[clave] = numero(clave, cfg.get(clave), clave in ("gramos_por_hora", "margen"))
    if not isinstance(cfg.get("moneda"), str) or not cfg["moneda"].strip():
        raise ValueError("moneda: falta una moneda valida")
    peso_total = peso * (1.0 + soportes / 100.0)
    horas = peso_total / cfg["gramos_por_hora"]
    material = peso_total / 1000.0 * cfg["precio_filamento_kg"]
    maquina = horas * cfg["coste_hora_maquina"]
    coste = material + maquina + cfg["preparacion"]
    # Los fallos no son mala suerte, son un coste: si una de cada doce se va a la basura,
    # esa doceava parte la pagan las once que salen bien.
    coste *= 1.0 + float(cfg["fallos_pct"]) / 100.0
    precio = coste * float(cfg["margen"])

    if not all(math.isfinite(n) for n in (peso_total, horas, material, maquina, coste, precio)):
        raise ValueError("presupuesto: los valores exceden el rango permitido")

    return {
        "peso_g": round(peso_total, 1),
        "horas": round(horas, 1),
        "material": round(material, 2),
        "maquina": round(maquina, 2),
        "preparacion": round(float(cfg["preparacion"]), 2),
        "coste": round(coste, 2),
        "precio": round(precio, 2),
        "moneda": cfg["moneda"],
        "configurado": cfg.get("configurado", False),
    }


def resumen(p):
    lineas = [
        "peso con mermas  %.1f g" % p["peso_g"],
        "tiempo aprox     %.1f h" % p["horas"],
        "material         %.2f %s" % (p["material"], p["moneda"]),
        "maquina          %.2f %s" % (p["maquina"], p["moneda"]),
        "preparacion      %.2f %s" % (p["preparacion"], p["moneda"]),
        "coste            %.2f %s  (mermas incluidas)" % (p["coste"], p["moneda"]),
        "PRECIO           %.2f %s" % (p["precio"], p["moneda"]),
    ]
    if not p["configurado"]:
        lineas.append("")
        lineas.append("OJO: son los numeros de ejemplo, no los tuyos. Pon los de verdad en")
        lineas.append("config_local.json (precio_filamento_kg, coste_hora_maquina, margen...)")
        lineas.append("o este precio no vale para cobrar.")
    return "\n".join(lineas)
