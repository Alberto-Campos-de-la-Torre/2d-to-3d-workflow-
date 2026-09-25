// Panel lateral "Bobinas": inventario de filamentos con selector de color.
// Escribe la paleta en el widget del nodo "Paleta de filamentos (Exo)" seleccionado,
// para elegir los colores viendo las bobinas en vez de escribir hex a mano.
import { app } from "../../scripts/app.js";

const CLAVE = "exo.bobinas";
const POR_DEFECTO = [
  { nombre: "PLA negro", hex: "#1a1a1a" },
  { nombre: "PLA blanco", hex: "#f2f2f2" },
  { nombre: "PLA gris", hex: "#8a8d8c" },
  { nombre: "PLA amarillo", hex: "#ffd500" },
];

function cargar() {
  try {
    const guardadas = JSON.parse(localStorage.getItem(CLAVE) || "null");
    if (Array.isArray(guardadas) && guardadas.length) return guardadas;
  } catch (e) { /* almacenamiento no disponible */ }
  return POR_DEFECTO.slice();
}

function guardar(bobinas) {
  try { localStorage.setItem(CLAVE, JSON.stringify(bobinas)); } catch (e) { /* sin guardar */ }
}

function nodosPaleta() {
  return app.graph?._nodes?.filter((n) => n.comfyClass === "ExoPaletaFilamentos") ?? [];
}

function aplicar(bobinas, activas, aviso) {
  const paleta = bobinas.filter((_, i) => activas.has(i)).map((b) => b.hex).join(",");
  const nodos = nodosPaleta();
  if (!nodos.length) {
    aviso.textContent = "Añade el nodo «Paleta de filamentos (Exo)» al flujo.";
    return;
  }
  const elegidos = nodos.filter((n) => n.is_selected) .length ? nodos.filter((n) => n.is_selected) : nodos;
  for (const nodo of elegidos) {
    const widget = nodo.widgets?.find((w) => w.name === "paleta");
    if (widget) {
      widget.value = paleta;
      widget.callback?.(paleta);
    }
  }
  app.graph.setDirtyCanvas(true, true);
  aviso.textContent = paleta
    ? `Paleta aplicada a ${elegidos.length} nodo(s): ${activas.size} filamento(s).`
    : "Paleta vacía: el nodo elegirá los colores por su cuenta.";
}

function construir(raiz) {
  let bobinas = cargar();
  const activas = new Set(bobinas.map((_, i) => i));

  raiz.innerHTML = "";
  raiz.style.cssText = "padding:12px; display:flex; flex-direction:column; gap:12px; overflow-y:auto; height:100%;";

  const intro = document.createElement("p");
  intro.textContent = "Las bobinas cargadas en la impresora. Marca las que vas a usar y aplícalas al nodo de paleta.";
  intro.style.cssText = "margin:0; font-size:12px; opacity:.75; line-height:1.5;";

  const lista = document.createElement("div");
  lista.style.cssText = "display:flex; flex-direction:column; gap:6px;";

  const aviso = document.createElement("p");
  aviso.style.cssText = "margin:0; font-size:11px; opacity:.7; min-height:2.4em; line-height:1.4;";

  function pintar() {
    lista.innerHTML = "";
    bobinas.forEach((bobina, i) => {
      const fila = document.createElement("div");
      fila.style.cssText = "display:flex; align-items:center; gap:8px;";

      const marca = document.createElement("input");
      marca.type = "checkbox";
      marca.checked = activas.has(i);
      marca.title = "Usar esta bobina en la paleta";
      marca.addEventListener("change", () => {
        marca.checked ? activas.add(i) : activas.delete(i);
      });

      const color = document.createElement("input");
      color.type = "color";
      color.value = bobina.hex;
      color.style.cssText = "width:34px; height:26px; padding:1px; background:transparent; border:1px solid #4444; border-radius:5px; cursor:pointer;";
      color.addEventListener("input", () => {
        bobina.hex = color.value;
        hex.textContent = color.value;
        guardar(bobinas);
      });

      const nombre = document.createElement("input");
      nombre.type = "text";
      nombre.value = bobina.nombre;
      nombre.style.cssText = "flex:1; min-width:0; background:#0003; color:inherit; border:1px solid #4444; border-radius:5px; padding:4px 6px; font-size:12px;";
      nombre.addEventListener("change", () => { bobina.nombre = nombre.value; guardar(bobinas); });

      const hex = document.createElement("span");
      hex.textContent = bobina.hex;
      hex.style.cssText = "font-family:monospace; font-size:11px; opacity:.7;";

      const quitar = document.createElement("button");
      quitar.textContent = "×";
      quitar.title = "Quitar bobina";
      quitar.style.cssText = "background:transparent; color:inherit; border:0; cursor:pointer; font-size:15px; opacity:.6;";
      quitar.addEventListener("click", () => {
        bobinas.splice(i, 1);
        activas.clear();
        bobinas.forEach((_, j) => activas.add(j));
        guardar(bobinas);
        pintar();
      });

      fila.append(marca, color, nombre, hex, quitar);
      lista.appendChild(fila);
    });
  }

  const botones = document.createElement("div");
  botones.style.cssText = "display:flex; gap:8px; flex-wrap:wrap;";

  const anadir = document.createElement("button");
  anadir.textContent = "Añadir bobina";
  anadir.style.cssText = "flex:1; padding:6px 10px; border-radius:6px; cursor:pointer;";
  anadir.addEventListener("click", () => {
    bobinas.push({ nombre: "PLA nuevo", hex: "#cccccc" });
    activas.add(bobinas.length - 1);
    guardar(bobinas);
    pintar();
  });

  const aplicarBoton = document.createElement("button");
  aplicarBoton.textContent = "Aplicar al nodo";
  aplicarBoton.style.cssText = "flex:1; padding:6px 10px; border-radius:6px; cursor:pointer; font-weight:600;";
  aplicarBoton.addEventListener("click", () => aplicar(bobinas, activas, aviso));

  botones.append(anadir, aplicarBoton);

  const nota = document.createElement("p");
  nota.innerHTML = "Al importar el OBJ en Creality Print, pulsa <strong>Color match</strong> antes de aceptar: si no, añade los colores como filamentos nuevos que la máquina no tiene.";
  nota.style.cssText = "margin:0; font-size:11px; opacity:.6; line-height:1.5;";

  pintar();
  raiz.append(intro, lista, botones, aviso, nota);
}

app.registerExtension({
  name: "exo.filaments.bobinas",
  async setup() {
    app.extensionManager?.registerSidebarTab?.({
      id: "exo-bobinas",
      icon: "pi pi-palette",
      title: "Bobinas",
      tooltip: "Inventario de filamentos de Exo filaments",
      type: "custom",
      render: (el) => construir(el),
    });
  },
});
