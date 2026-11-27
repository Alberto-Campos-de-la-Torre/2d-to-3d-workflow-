const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const pending=[];const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',replaceChildren(){},addEventListener(){},querySelectorAll(){return [];}});return elements.get(id);}
const context=vm.createContext({document:{getElementById:element},setInterval(){},fetch(url){return new Promise(resolve=>pending.push({url,resolve}));},FormData:class{},URL,console});
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
vm.runInContext(source+"\nglobalThis.qa={api,setUser(user){sesion=user;mostrarSesion();},user(){return sesion;}}",context);
async function test(){
  context.qa.setUser({id:'actor_anterior',login:'anterior',role:'cliente',csrf:'csrf-prueba'});
  const old=context.qa.api('/api/archivos');const request=pending.find(r=>r.url==='/api/archivos');
  context.qa.setUser({id:'actor_nuevo',login:'nuevo',role:'cliente',csrf:'csrf-nuevo'});
  request.resolve({ok:true,status:200,json:async()=>({archivos:['datos_del_actor_anterior']})});
  await assert.rejects(old,/sesión cambió/);assert.equal(context.qa.user().id,'actor_nuevo');
  const stale=context.qa.api('/api/trabajos');const request2=pending.find(r=>r.url==='/api/trabajos');
  context.qa.setUser({id:'otro_actor',login:'otro',role:'cliente',csrf:'csrf-otro'});
  request2.resolve({ok:false,status:401,json:async()=>({error:'sesion anterior caducada'})});
  await assert.rejects(stale,/sesión cambió/);assert.equal(context.qa.user().id,'otro_actor');
  console.log('OK: las respuestas de una sesion anterior no muestran datos ni cierran la nueva sesion');
}
test().catch(error=>{console.error(error);process.exitCode=1;});
