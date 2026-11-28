const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.value='';this.checked=false;this.disabled=false;this.files=[];}
  addEventListener(name,fn){this.events[name]=fn;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  querySelectorAll(selector){const all=this.children.flatMap(n=>n instanceof Element?[n,...n.querySelectorAll('*')]:[]);return selector==='input:checked'?all.filter(n=>n.tag==='input'&&n.checked):all;}
  querySelector(){return this.button;}
  reset(){if(this.imagen)this.imagen.files=[];}
}
async function fixture(){
  const elements=new Map(),requests=[],files=[];let failUpload=false,failJob=false;
  const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  el('subida').imagen=new Element('input');el('subida').button=new Element('button');
  const form=el('solicitud');form.button=new Element('button');
  for(const [key,value] of Object.entries({tipo:'2d',prompt:'Cambiar el fondo',pasos:'20',intentos:'2',resolucion:'1024',altura:'80'})){form[key]=new Element();form[key].value=value;}
  form.color={checked:true};
  class FormData {constructor(form){assert.equal(form.imagen.disabled,false,'el archivo debe entrar al FormData');this.file=form.imagen.files[0];}}
  const response=(data,status=200)=>({ok:status<400,status,json:async()=>data});
  const context=vm.createContext({document:{getElementById:el,createElement:tag=>new Element(tag),createTextNode:text=>text},FormData,setInterval(){},crypto:{randomUUID:()=> 'request_prueba'},console,
    async fetch(url,options){requests.push({url,...options});
      if(url==='/api/me')return response({error:'No hay sesion'},401);
      if(url==='/api/referencias'){
        await new Promise(resolve=>setImmediate(resolve));
        if(failUpload)return response({error:'Subida rechazada'},413);
        assert.ok(options.body.file);
        const saved={id:'ref_'+files.length,owner:'persona',type:'referencia',mime:'image/png'};files.push(saved);return response(saved,201);
      }
      if(url==='/api/archivos')return response({archivos:files});
      if(url==='/api/trabajos'){
        if(options.method==='POST'&&failJob){failJob=false;throw new Error('Conexion perdida');}
        return response(options.method==='POST'?{}:{trabajos:[]});
      }
      if(url==='/api/capacidades')return response({flujos:['2d','3d']});
      if(url==='/api/motor')return response({trabajador_activo:true,estado:'disponible'});
      throw new Error('Ruta inesperada '+url);
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8')+'\nglobalThis.qa={setUser(user){sesion=user;mostrarSesion();},subirReferenciaPendiente,referencias,referenciasMarcadas};',context);
  await new Promise(resolve=>setImmediate(resolve));
  context.qa.setUser({id:'persona',login:'persona',role:'cliente',csrf:'csrf_prueba'});
  return {el,requests,files,qa:context.qa,setFailUpload(){failUpload=true;},setFailJob(){failJob=true;},
    send:()=>form.events.submit({preventDefault(){},target:form}),
    upload:()=>el('subida').events.submit({preventDefault(){},target:el('subida')})};
}
async function test(){
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'foto.png'}];await f.send();
    const upload=f.requests.findIndex(r=>r.url==='/api/referencias'),job=f.requests.findIndex(r=>r.url==='/api/trabajos'&&r.method==='POST');
    assert.ok(upload>=0&&job>upload);assert.deepEqual(JSON.parse(f.requests[job].body).referencias,['ref_0']);
    assert.match(f.el('resumen-referencias').textContent,/1 referencia/);
  }
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'foto.png'}];await f.upload();await f.send();
    assert.equal(f.requests.filter(r=>r.url==='/api/referencias').length,1);
    assert.deepEqual(JSON.parse(f.requests.find(r=>r.url==='/api/trabajos'&&r.method==='POST').body).referencias,['ref_0']);
  }
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'foto.png'}];f.setFailUpload();await f.send();
    assert.equal(f.requests.filter(r=>r.url==='/api/trabajos'&&r.method==='POST').length,0);
    assert.equal(f.el('subida').imagen.files.length,1);assert.equal(f.el('subida').imagen.disabled,false);
  }
  {
    const f=await fixture();await f.send();
    assert.deepEqual(JSON.parse(f.requests.find(r=>r.url==='/api/trabajos'&&r.method==='POST').body).referencias,[]);
  }
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'foto.png'}];await Promise.all([f.upload(),f.send()]);
    assert.equal(f.requests.filter(r=>r.url==='/api/referencias').length,1);
    assert.deepEqual(JSON.parse(f.requests.find(r=>r.url==='/api/trabajos'&&r.method==='POST').body).referencias,['ref_0']);
  }
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'foto.png'}];f.setFailJob();await f.send();await f.send();
    assert.equal(f.requests.filter(r=>r.url==='/api/referencias').length,1);
    const jobs=f.requests.filter(r=>r.url==='/api/trabajos'&&r.method==='POST').map(r=>JSON.parse(r.body));
    assert.deepEqual(jobs[0],jobs[1]);
  }
  {
    const f=await fixture();f.el('subida').imagen.files=[{name:'privada.png'}];f.qa.setUser(null);
    assert.equal(f.el('subida').imagen.files.length,0);
  }
  console.log('OK: 7 casos de referencias, subida automatica, seleccion, errores, concurrencia y sesion');
}
test().catch(error=>{console.error(error);process.exitCode=1;});
