let sesion=null,solicitudPendiente=null,monitorOcupado=false,ultimoEstado="",versionSesion=0;
const $=id=>document.getElementById(id);
function mensaje(texto){$("mensaje").textContent=texto;}
async function api(path,method="GET",data=null){
  const version=versionSesion;
  const headers={};if(sesion?.csrf)headers["X-CSRF-Token"]=sesion.csrf;
  let body=data;if(data && !(data instanceof FormData)){headers["Content-Type"]="application/json";body=JSON.stringify(data);}
  const r=await fetch(path,{method,headers,body,credentials:"same-origin"});
  const result=await r.json().catch(()=>({error:"Respuesta no válida"}));
  if(version!==versionSesion)throw new Error("La sesión cambió; vuelve a actualizar");
  if(!r.ok){if(r.status===401){sesion=null;mostrarSesion();}throw new Error(result.error||`Error ${r.status}`);}return result;
}
function boton(texto,action){const b=document.createElement("button");b.type="button";b.textContent=texto;b.addEventListener("click",async()=>{b.disabled=true;try{await action();}catch(e){mensaje(e.message);}finally{b.disabled=false;}});return b;}
function mostrarSesion(){
  versionSesion++;
  $("acceso").hidden=!!sesion;$("panel").hidden=!sesion;$("salir").hidden=!sesion;
  $("identidad").textContent=sesion ? `${sesion.login} · ${sesion.role}` : "Acceso a tus referencias y trabajos.";
  $("administracion").hidden=sesion?.role!=="administrador";
  if(!sesion){ultimoEstado="";solicitudPendiente=null;$("referencias").replaceChildren();$("trabajos").replaceChildren();$("usuarios").replaceChildren();}
}
$("login").addEventListener("submit",async(e)=>{e.preventDefault();const f=e.target;try{sesion=await api("/api/login","POST",{usuario:f.usuario.value,password:f.password.value});f.password.value="";mostrarSesion();await actualizar();mensaje("");}catch(error){mensaje(error.message);}});
$("salir").addEventListener("click",async()=>{try{await api("/api/logout","POST",{});sesion=null;mostrarSesion();mensaje("Sesión cerrada");}catch(e){mensaje(e.message);}});
$("subida").addEventListener("submit",async(e)=>{e.preventDefault();const button=e.target.querySelector("button");button.disabled=true;try{await api("/api/referencias","POST",new FormData(e.target));e.target.reset();await actualizar();mensaje("Referencia guardada de forma privada");}catch(error){mensaje(error.message);}finally{button.disabled=false;}});
$("solicitud").addEventListener("submit",async(e)=>{
  e.preventDefault();const f=e.target,b=f.querySelector("button");b.disabled=true;
  try{
    const refs=[...$("referencias").querySelectorAll("input:checked")].map(n=>n.value);
    const opciones={pasos:+f.pasos.value,max_intentos:+f.intentos.value,...(f.tipo.value==="2d" ? {resolucion:+f.resolucion.value} : {altura_mm:+f.altura.value,color:f.color.checked})};
    const data={tipo:f.tipo.value,prompt:f.prompt.value,referencias:refs,opciones};const firma=JSON.stringify(data);
    if(!solicitudPendiente || solicitudPendiente.firma!==firma)solicitudPendiente={firma,id:crypto.randomUUID()};
    await api("/api/trabajos","POST",{...data,request_id:solicitudPendiente.id});solicitudPendiente=null;
    await trabajos();mensaje("Trabajo guardado en la cola. El trabajador lo procesará cuando haya GPU disponible.");
  }catch(error){mensaje(error.message+". Revisa el historial antes de volver a enviar.");}finally{b.disabled=false;}
});
$("nuevo-usuario").addEventListener("submit",async(e)=>{e.preventDefault();const f=e.target;try{await api("/api/usuarios","POST",{usuario:f.usuario.value,password:f.password.value,rol:f.rol.value});f.reset();await usuarios();mensaje("Cuenta creada");}catch(error){mensaje(error.message);}});
async function referencias(){
  const seleccion=new Set([...$("referencias").querySelectorAll("input:checked")].map(n=>n.value));
  const datos=await api("/api/archivos");$("referencias").replaceChildren();
  for(const file of datos.archivos.filter(f=>f.type==="referencia" || f.mime==="image/png")){
    const card=document.createElement("div");card.className="tarjeta";
    const img=document.createElement("img");img.src=`/api/archivos/${file.id}/vista`;img.alt="Referencia privada";img.loading="lazy";
    const label=document.createElement("label"),check=document.createElement("input");check.type="checkbox";check.value=file.id;
    // Un administrador ve todas las referencias, pero solo mezcla las propias en solicitudes nuevas.
    check.disabled=file.owner!==sesion.id;check.checked=seleccion.has(file.id);label.append(check,document.createTextNode(" Usar esta imagen"));
    card.append(img,label);
    if(file.type==="referencia")card.append(boton("Borrar referencia",async()=>{if(!confirm("¿Borrar este archivo de referencia de la PC?"))return;await api(`/api/archivos/${file.id}`,"DELETE");await actualizar();}));
    else {const nota=document.createElement("p");nota.textContent="Imagen generada: se borra desde su trabajo.";card.append(nota);}
    $("referencias").append(card);
  }
}
async function trabajos(){
  const version=versionSesion;
  const datos=await api("/api/trabajos");$("trabajos").replaceChildren();
  const firma=datos.trabajos.map(j=>j.id+j.state).join("|");
  if(ultimoEstado && firma!==ultimoEstado)await referencias();ultimoEstado=firma;
  if(version!==versionSesion)return;
  if(!datos.trabajos.length){$("trabajos").textContent="Todavía no hay trabajos.";return;}
  for(const job of datos.trabajos){
    const row=document.createElement("article");row.className="trabajo";
    const h=document.createElement("h3");h.textContent=`${job.kind.toUpperCase()} · ${job.state.replaceAll("_"," ")}`;
    const p=document.createElement("p");p.textContent=job.prompt||"Conversión desde imagen";
    const actions=document.createElement("div");actions.className="acciones";
    if(["pendiente","preparando","enviando","ejecutando","importando"].includes(job.state))actions.append(boton("Cancelar",async()=>{await api(`/api/trabajos/${job.id}/cancelar`,"POST",{});await trabajos();}));
    if(["fallido","cancelado"].includes(job.state) && job.intento<job.opciones.max_intentos)actions.append(boton("Reintentar",async()=>{await api(`/api/trabajos/${job.id}/reintentar`,"POST",{});await trabajos();}));
    if(["pendiente","cancelado","terminado","fallido"].includes(job.state))actions.append(boton("Borrar trabajo y archivos",async()=>{if(!confirm("¿Borrar este trabajo, sus resultados y sus referencias sin otros usos? El borrado es permanente."))return;await api(`/api/trabajos/${job.id}`,"DELETE");await actualizar();}));
    const avance=document.createElement("p");avance.textContent=`Intento ${job.intento}/${job.opciones.max_intentos} · etapa: ${job.etapa || job.state}`+(job.error ? ` · ${job.error.replaceAll("_"," ")}` : "");
    if(job.state==="requiere_revision")avance.textContent+=" · Un operador debe revisar el motor; no se reenviará automáticamente.";
    for(const id of job.resultados){const a=document.createElement("a");a.href=`/api/archivos/${id}/descargar`;a.textContent="Descargar resultado";actions.append(a);}
    row.append(h,p,avance,actions);$("trabajos").append(row);
  }
}
async function usuarios(){if(sesion.role!=="administrador")return;const datos=await api("/api/usuarios");$("usuarios").replaceChildren();for(const user of datos.usuarios){const row=document.createElement("p");row.append(document.createTextNode(`${user.login} · ${user.role} · ${user.active ? "activo" : "desactivado"} `),boton(user.active ? "Desactivar" : "Activar",async()=>{await api(`/api/usuarios/${user.id}`,"PATCH",{activo:!user.active});await usuarios();}));$("usuarios").append(row);}}
async function estadoMotor(){const m=await api("/api/motor");$("motor").textContent=m.trabajador_activo ? "Trabajador: "+m.estado.replaceAll("_"," ")+". Revisa los resultados antes de imprimir." : "Trabajador desconectado. Las solicitudes se conservan en la cola.";}
async function actualizar(){const cap=await api("/api/capacidades");const select=$("solicitud").tipo;const old=select.value;select.replaceChildren();for(const tipo of cap.flujos){const option=document.createElement("option");option.value=tipo;option.textContent=tipo==="2d" ? "Imagen 2D" : "Modelo 3D desde una imagen";select.append(option);}if(cap.flujos.includes(old))select.value=old;await referencias();await trabajos();await usuarios();await estadoMotor();}
setInterval(async()=>{if(!sesion || monitorOcupado)return;monitorOcupado=true;try{await trabajos();await estadoMotor();}catch(e){mensaje(e.message);}finally{monitorOcupado=false;}},3000);
$("actualizar").addEventListener("click",()=>actualizar().catch(e=>mensaje(e.message)));
api("/api/me").then(async(user)=>{sesion=user;mostrarSesion();await actualizar();}).catch(e=>{mostrarSesion();if(sesion)mensaje(e.message);});
