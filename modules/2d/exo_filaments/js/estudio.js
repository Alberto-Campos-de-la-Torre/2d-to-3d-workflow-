// Panel lateral "Estudio Qwen": acceso a la pagina /exo/estudio (generar con
// Qwen-Image 2.1 y revisar resultados), que necesita mas sitio que la barra lateral.
import { app } from "../../scripts/app.js";

app.registerExtension({
  name: "exo.filaments.estudio",
  async setup() {
    app.extensionManager?.registerSidebarTab?.({
      id: "exo-estudio",
      icon: "pi pi-images",
      title: "Estudio Qwen",
      tooltip: "Generar imágenes con Qwen-Image 2.1 y revisarlas",
      type: "custom",
      render: (el) => {
        el.innerHTML = "";
        el.style.cssText = "padding:12px; display:flex; flex-direction:column; gap:10px;";
        const texto = document.createElement("p");
        texto.textContent = "Genera imágenes con Qwen-Image 2.1 (GGUF) y revísalas: veredicto, estrellas, notas y comparación lado a lado.";
        texto.style.cssText = "margin:0; font-size:12px; opacity:.75; line-height:1.5;";
        const abrir = document.createElement("button");
        abrir.textContent = "Abrir el estudio";
        abrir.style.cssText = "padding:8px 10px; border-radius:6px; cursor:pointer; font-weight:600;";
        abrir.addEventListener("click", () => window.open("/exo/estudio", "exo-estudio"));
        el.append(texto, abrir);
      },
    });
  },
});
