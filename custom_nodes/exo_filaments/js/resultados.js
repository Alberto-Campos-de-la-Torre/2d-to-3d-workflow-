// Compartido por Estudio Qwen e imagen a pieza, en escritorio y movil.
(function () {
  async function api(url, datos) {
    const r=await fetch(url,datos ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(datos)} : {});
    const d=await r.json().catch(()=>({error:"No se pudo leer la respuesta del servidor"}));
    if (!r.ok || d.error) throw new Error(d.error || `Error ${r.status}`);
    return d;
  }
  window.exoBorrarResultado=async function (seleccion) {
    try {
      const plan=await api("/exo/resultados/preparar-borrado",seleccion);
      const nombres=plan.archivos.slice(0,12).map(p=>p.split(":",2)[1]).join("\n");
      const mas=plan.archivos.length>12 ? `\n… y ${plan.archivos.length-12} archivos más` : "";
      const compartidos=plan.conservados.length ? `\nSe conservarán ${plan.conservados.length} archivos compartidos con otros resultados.` : "";
      const antiguo=plan.antiguo ? "\nResultado anterior al catálogo: solo se borrarán los archivos asociados que aparecen en esta lista; no se inferirán otros archivos de aquella ejecución." : "";
      if (!window.confirm(`Borrado permanente de ${plan.archivos.length} archivos (${(plan.bytes/1048576).toFixed(1)} MB), incluidas ${plan.referencias.length} referencias locales, y ${plan.historial.length} entradas de historial.\n\n${nombres}${mas}${compartidos}${antiguo}\n\n¿Borrar estos archivos de la PC?`)) return false;
      const resultado=await api("/exo/resultados/borrar",{id:plan.id,token:plan.token});
      window.dispatchEvent(new CustomEvent("exo-resultados-borrados",{detail:resultado}));
      return true;
    } catch(e) { window.alert("No se pudo completar el borrado: "+e.message);return false; }
  };
  function urlImagen(key) {
    const [type,path]=key.split(":",2),pos=path.lastIndexOf("/");
    return "/view?"+new URLSearchParams({type,filename:path.slice(pos+1),subfolder:pos<0 ? "" : path.slice(0,pos),preview:"webp;60"});
  }
  async function cargarResultados() {
    const contenedor=document.querySelector('[data-exo-resultados="3d"]');
    if (!contenedor) return;
    contenedor.replaceChildren();
    try {
      const datos=await api("/exo/resultados");
      const lista=datos.resultados.filter(r=>r.archivos.some(p=>p.startsWith("output:3d/exo/")));
      if (!lista.length) {contenedor.textContent="No hay resultados 3D guardados.";return;}
      for (const r of lista) {
        const fila=document.createElement("div");
        fila.style.cssText="display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 0;border-bottom:1px solid #555";
        if (r.miniatura) {const img=document.createElement("img");img.src=urlImagen(r.miniatura);img.loading="lazy";img.alt=r.nombre;img.style.cssText="width:84px;height:84px;object-fit:contain";fila.append(img);}
        const texto=document.createElement("span");texto.textContent=`${r.nombre} · ${r.archivos.length} archivos`+(r.antiguo ? " · anterior al catálogo" : "");texto.style.cssText="flex:1;min-width:140px;overflow-wrap:anywhere";
        const boton=document.createElement("button");boton.type="button";boton.textContent="Borrar resultado";boton.style.cssText="min-height:44px;color:#ffaaa0";
        boton.addEventListener("click",async()=>{boton.disabled=true;try {await window.exoBorrarResultado({id:r.id});} finally {boton.disabled=false;}});
        fila.append(texto,boton);contenedor.append(fila);
      }
    } catch(e) {contenedor.textContent="No se pudo cargar el catálogo: "+e.message;}
  }
  const recargar=document.getElementById("actualizar-resultados");
  if (recargar) recargar.addEventListener("click",cargarResultados);
  window.addEventListener("exo-resultados-borrados",cargarResultados);
  window.addEventListener("exo-resultados-actualizar",cargarResultados);
  cargarResultados();
})();
