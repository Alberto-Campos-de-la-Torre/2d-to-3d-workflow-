import asyncio
import io
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestServer
from PIL import Image,PngImagePlugin

from portal.backend import Backend,MotorError
from portal.queue import Queue,LeaseLost,retry
from portal.store import Store,ErrorPortal
from portal.worker import Worker,resolve_lost


class FakeComfy:
    """Protocolo HTTP y archivos reales de prueba; NO simula inferencia de modelos."""
    def __init__(self,root):
        self.root=root;self.submissions=[];self.active=[];self.pending=[];self.history={};self.canceled=[]
        app=web.Application();app.add_routes([web.get('/queue',self.queue),web.post('/prompt',self.submit),
            web.get('/history/{pid}',self.get_history),web.post('/history',self.delete_history),
            web.post('/queue',self.delete_queue),web.post('/interrupt',self.interrupt)])
        self.server=TestServer(app)
    async def queue(self,_):return web.json_response({'queue_running':self.active,'queue_pending':self.pending})
    async def submit(self,request):
        d=await request.json();self.submissions.append(d);self.active=[[0,d['prompt_id']]]
        return web.json_response({'prompt_id':d['prompt_id'],'node_errors':{}})
    async def get_history(self,request):
        pid=request.match_info['pid'];return web.json_response({pid:self.history[pid]} if pid in self.history else {})
    async def delete_history(self,request):
        for pid in (await request.json()).get('delete',[]):self.history.pop(pid,None)
        return web.json_response({})
    async def delete_queue(self,request):
        ids=(await request.json()).get('delete',[]);self.pending=[r for r in self.pending if r[1] not in ids]
        return web.json_response({})
    async def interrupt(self,request):
        pid=(await request.json())['prompt_id'];self.canceled.append(pid);self.active=[r for r in self.active if r[1]!=pid]
        return web.json_response({})
    def complete(self,kind='2d',success=True,foreign=None):
        d=self.submissions[-1];pid=d['prompt_id'];g=d['prompt'];outputs={}
        node='9' if kind=='2d' else '231';prefix=g[node]['inputs']['filename_prefix']
        p=self.root/'output'/(prefix+'_00001_.png');p.parent.mkdir(parents=True,exist_ok=True)
        info=PngImagePlugin.PngInfo();info.add_text('prompt','metadata de prueba que no debe llegar al cliente')
        Image.new('RGB',(8,8),(40,120,80)).save(p,pnginfo=info)
        outputs[node]={'images':[{'filename':p.name,'subfolder':p.parent.relative_to(self.root/'output').as_posix(),'type':'output'}]}
        if kind=='3d':
            target=self.root/'output'/(g['203']['inputs']['nombre']+'_00001.stl');target.write_bytes(b'solid fixture\nendsolid fixture\n')
            colored=target.with_suffix('.3mf');colored.write_bytes(b'fixture del protocolo, no geometria')
            outputs['203']={'text':[str(target)+'\n'+str(colored)]}
        if foreign:outputs[node]['images'][0]['filename']=str(foreign)
        self.history[pid]={'prompt':[0,pid,g],'outputs':outputs,'status':{'status_str':'success' if success else 'error'}}
        self.active=[r for r in self.active if r[1]!=pid]


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name);self.store=Store(base/'private')
        pwd=secrets.token_urlsafe(20);self.a=self.store.create_user('persona_a',pwd);self.a['role']='cliente'
        self.b=self.store.create_user('persona_b',pwd);self.b['role']='cliente'
        self.comfy=base/'comfy';self.comfy.mkdir();(self.comfy/'main.py').write_text('# fixture')
        (self.comfy/'input').mkdir();(self.comfy/'output').mkdir()
        self.fake=FakeComfy(self.comfy);await self.fake.server.start_server()
        self.backend=Backend(str(self.fake.server.make_url('/')),self.comfy);await self.backend.open()
        self.worker=Worker(self.store,self.backend);self.assertTrue(self.worker.queue.acquire())
    async def asyncTearDown(self):
        self.worker.queue.release();await self.backend.close();await self.fake.server.close();self.temp.cleanup()
    def job(self,kind='2d',owner=None,options=None):
        refs=[]
        if kind=='3d':
            out=io.BytesIO();Image.new('RGB',(8,8)).save(out,format='PNG')
            f=self.store.save_file((owner or self.a)['id'],out.getvalue(),'image/png');refs=[f['id']]
        return self.store.create_job(owner or self.a,{'tipo':kind,'prompt':'figura de prueba','referencias':refs,'opciones':options or {}})
    def state(self,j):return self.store.job(j['id'],self.a)['state']
    async def finish(self,kind='2d'):
        self.fake.complete(kind);await self.worker.tick();await self.worker.tick()
    async def test_2d_de_cola_a_archivo_privado_y_limpieza(self):
        j=self.job();await self.worker.tick();self.assertEqual(self.state(j),'ejecutando')
        await self.finish();result=self.store.job(j['id'],self.a);self.assertEqual(result['state'],'terminado')
        f=self.store.file(result['resultados'][0],self.a)
        with Image.open(self.store.path(f)) as im:self.assertNotIn('prompt',im.info)
        with self.assertRaises(ErrorPortal):self.store.file(f['id'],self.b)
        self.assertFalse(self.fake.history);self.assertFalse(list((self.comfy/'output').rglob('*.png')))
    async def test_referencias_2d_llegan_al_grafo_y_se_limpian(self):
        for count in (1,2):
            with self.subTest(referencias=count):
                refs=[]
                for i in range(count):
                    out=io.BytesIO();Image.new('RGB',(8,8),(50+i*60,80,120)).save(out,format='PNG')
                    refs.append(self.store.save_file(self.a['id'],out.getvalue(),'image/png')['id'])
                job=self.store.create_job(self.a,{'tipo':'2d','prompt':'Cambiar el fondo','referencias':refs})
                await self.worker.tick();graph=self.fake.submissions[-1]['prompt']
                linked=self.store.job(job['id'],self.a)['referencias']
                self.assertEqual(set(linked),set(refs));self.assertNotIn('5',graph)
                self.assertEqual(graph['6']['inputs']['latent_image'],['4',2])
                for i,ident in enumerate(linked):
                    key=str(20+i);self.assertEqual(graph['4']['inputs'][f'images.image_{i+1}'],[key,0])
                    path=self.comfy/'input'/graph[key]['inputs']['image']
                    self.assertTrue(path.is_file())
                    self.assertEqual(path.read_bytes(),self.store.path(self.store.file(ident,self.a)).read_bytes())
                await self.finish();self.assertEqual(self.state(job),'terminado')
                self.assertFalse(list((self.comfy/'input').rglob('*.png')))
                self.assertTrue(all(self.store.path(self.store.file(ident,self.a)).is_file() for ident in refs))

    async def test_3d_plantilla_y_exportacion_sin_malla_bruta(self):
        j=self.job('3d');await self.worker.tick();graph=self.fake.submissions[-1]['prompt']
        self.assertNotIn('82',graph);self.assertEqual(graph['62']['inputs']['resolucion'],384)
        self.assertFalse(graph['203']['inputs']['guardar_obj']);self.assertTrue(graph['203']['inputs']['guardar_3mf_experimental'])
        await self.finish('3d');result=self.store.job(j['id'],self.a)
        self.assertEqual(result['state'],'terminado');self.assertEqual(len(result['resultados']),3)
        self.assertFalse(list((self.comfy/'input').rglob('*.png')))
    async def test_una_sola_reserva_gpu(self):
        other=Queue(self.store);self.assertFalse(other.acquire())
        self.job();await self.worker.tick();self.job(owner=self.b);await self.worker.tick()
        self.assertEqual(len(self.fake.submissions),1)
    async def test_motor_ocupado_no_reserva_ni_envia(self):
        j=self.job();self.fake.active=[[0,'trabajo_externo']];await self.worker.tick()
        self.assertEqual(self.state(j),'pendiente');self.assertFalse(self.fake.submissions)
    async def test_recupera_identificador_sin_duplicar(self):
        j=self.job();await self.worker.tick();pid=self.fake.submissions[0]['prompt_id']
        self.worker.queue.release();self.worker=Worker(self.store,self.backend);self.assertTrue(self.worker.queue.acquire())
        await self.worker.tick();self.assertEqual(len(self.fake.submissions),1)
        self.assertEqual(self.worker.queue.internal(j['id'])['runtime']['prompt_id'],pid)
        await self.finish();self.assertEqual(self.state(j),'terminado')
    async def test_respuesta_perdida_no_reenvia(self):
        j=self.job();original=self.backend.submit
        async def lost(*args):await original(*args);raise asyncio.TimeoutError()
        self.backend.submit=lost
        with self.assertRaises(asyncio.TimeoutError):await self.worker.tick()
        self.backend.submit=original;await self.worker.tick()
        self.assertEqual(len(self.fake.submissions),1);await self.finish();self.assertEqual(self.state(j),'terminado')
    async def test_desaparicion_no_reenvia_a_ciegas(self):
        j=self.job();await self.worker.tick();self.fake.active=[];await self.worker.tick()
        self.assertEqual(self.state(j),'requiere_revision');await self.worker.tick();self.assertEqual(len(self.fake.submissions),1)
        with self.assertRaises(ErrorPortal):retry(self.store,j['id'],self.a)
    async def test_cancelacion_no_interrumpe_otros(self):
        j=self.job();await self.worker.tick();pid=self.fake.submissions[0]['prompt_id']
        self.fake.pending=[[1,'otro_trabajo']];self.store.cancel(j['id'],self.a)
        await self.worker.tick();await self.worker.tick()
        self.assertEqual(self.fake.canceled,[pid]);self.assertEqual(self.fake.pending,[[1,'otro_trabajo']]);self.assertEqual(self.state(j),'cancelado')
    async def test_limite_tiempo_solicita_cancelacion(self):
        j=self.job();await self.worker.tick()
        with self.store.connect() as db:db.execute('UPDATE job_runtime SET started=? WHERE job=?',(time.time()-3000,j['id']))
        await self.worker.tick();await self.worker.tick()
        self.assertEqual(self.state(j),'cancelado');self.assertEqual(self.store.job(j['id'],self.a)['error'],'tiempo_agotado')
    async def test_reintentos_limitados_y_no_automaticos(self):
        j=self.job(options={'max_intentos':2});await self.worker.tick();self.fake.complete(success=False);await self.worker.tick()
        self.assertEqual(self.state(j),'fallido');await self.worker.tick();self.assertEqual(len(self.fake.submissions),1)
        retry(self.store,j['id'],self.a);await self.worker.tick();self.fake.complete(success=False);await self.worker.tick()
        with self.assertRaises(ErrorPortal):retry(self.store,j['id'],self.a)
    async def test_no_publica_importacion_parcial(self):
        j=self.job();await self.worker.tick();self.fake.complete();await self.worker.tick()
        self.assertEqual(self.state(j),'importando');self.assertEqual(self.store.job(j['id'],self.a)['resultados'],[])
        self.assertEqual(self.store.files(self.a),[]);await self.worker.tick();self.assertEqual(self.state(j),'terminado')
    async def test_recupera_importacion_antes_de_publicar(self):
        j=self.job();await self.worker.tick();self.fake.complete();await self.worker.tick()
        self.fake.history.clear();self.backend.clean_files(self.worker.queue.internal(j['id']))
        self.worker.queue.release();self.worker=Worker(self.store,self.backend);self.assertTrue(self.worker.queue.acquire())
        await self.worker.tick();self.assertEqual(self.state(j),'terminado');self.assertEqual(len(self.fake.submissions),1)
    async def test_salidas_ajenas_no_se_importan(self):
        j=self.job();await self.worker.tick();outside=self.comfy/'output'/'externo.png';Image.new('RGB',(8,8)).save(outside)
        self.fake.complete(foreign=outside);await self.worker.tick()
        self.assertEqual(self.state(j),'fallido');self.assertTrue(outside.exists());self.assertEqual(self.store.files(self.a),[])
    async def test_referencia_resultado_2d_puede_alimentar_3d(self):
        j=self.job();await self.worker.tick();await self.finish();f=self.store.job(j['id'],self.a)['resultados'][0]
        child=self.store.create_job(self.a,{'tipo':'3d','referencias':[f]})
        with self.assertRaises(ErrorPortal):self.store.delete_job(j['id'],self.a)
        self.store.delete_job(child['id'],self.a);self.store.delete_job(j['id'],self.a)
    async def test_cuota_e_idempotencia(self):
        self.job();self.job()
        with self.assertRaises(ErrorPortal) as error:self.job()
        self.assertEqual(error.exception.status,429)
    async def test_no_acepta_opciones_con_rutas(self):
        with self.assertRaises(ErrorPortal):self.job(options={'modelo':'archivo_local'})
        with self.assertRaises(ErrorPortal):self.job(options={'max_intentos':200})
    async def test_reserva_caducada_impide_escritura_tardia(self):
        self.job()
        with self.store.connect() as db:db.execute('UPDATE worker_lease SET expires=0')
        other=Queue(self.store);self.assertTrue(other.acquire())
        with self.assertRaises(LeaseLost):self.worker.queue.claim()
        with self.assertRaises(LeaseLost):self.store.save_file(self.a['id'],b'prueba','image/png','resultado',guard=self.worker.queue.guard)
        other.release()
    async def test_migracion_de_trabajo_etapa1(self):
        j=self.job()
        with self.store.connect() as db:db.execute("UPDATE jobs SET state='pendiente_de_motor' WHERE id=?",(j['id'],));db.execute('DELETE FROM job_runtime WHERE job=?',(j['id'],))
        fresh=Store(self.store.root);self.assertEqual(fresh.job(j['id'],self.a)['state'],'pendiente')
    async def test_cancelar_durante_importacion_no_publica_archivos(self):
        j=self.job();await self.worker.tick();self.fake.complete();await self.worker.tick()
        self.store.cancel(j['id'],self.a);await self.worker.tick()
        self.assertEqual(self.state(j),'cancelado');self.assertEqual(self.store.files(self.a),[])
        self.assertFalse(list((self.store.root/'usuarios').rglob('*.png')))
    async def test_motor_desconectado_no_consume_intentos(self):
        j=self.job();self.worker.queue.release();await self.fake.server.close()
        backend=Backend(self.backend.url,self.comfy);worker=Worker(self.store,backend)
        await worker.run(once=True)
        self.assertEqual(worker.status,'motor_desconectado');self.assertEqual(self.state(j),'pendiente')
        self.assertEqual(self.store.job(j['id'],self.a)['intento'],0)
    async def test_perdida_se_resuelve_solo_con_reserva_y_motor_vacio(self):
        j=self.job();await self.worker.tick();self.fake.active=[];await self.worker.tick()
        self.assertEqual(self.state(j),'requiere_revision')
        with self.assertRaises(RuntimeError):await resolve_lost(self.store,Backend(self.backend.url,self.comfy),j['id'])
        self.worker.queue.release()
        await resolve_lost(self.store,Backend(self.backend.url,self.comfy),j['id'])
        self.assertEqual(self.state(j),'fallido');self.assertEqual(len(self.fake.submissions),1)
    async def test_imagen_corrupta_falla_sin_bucle_ni_publicacion(self):
        j=self.job();await self.worker.tick();self.fake.complete()
        for path in (self.comfy/'output').rglob('*.png'):path.write_bytes(b'archivo_incompleto')
        await self.worker.tick()
        self.assertEqual(self.state(j),'fallido');self.assertEqual(self.store.files(self.a),[])
        self.assertEqual(self.store.job(j['id'],self.a)['error'],'resultado_imagen_invalido')

if __name__=='__main__':unittest.main(verbosity=2)
