import io
import secrets
import tempfile
import unittest
from pathlib import Path

from aiohttp import CookieJar,FormData
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image,PngImagePlugin

from portal.app import create_app,STORE
from portal.store import Store,token_hash


class Portal(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=create_app(self.root,secure_cookies=False);self.store=self.app[STORE]
        self.password=secrets.token_urlsafe(20)
        self.a=self.store.create_user('persona_a',self.password)
        self.b=self.store.create_user('persona_b',self.password)
        self.admin=self.store.create_user('administracion',self.password,'administrador')
        self.server=TestServer(self.app);await self.server.start_server()
        self.clients=[]
        for user in [self.a,self.b,self.admin]:
            client=TestClient(self.server,cookie_jar=CookieJar(unsafe=True));await client.start_server()
            response=await client.post('/api/login',json={'usuario':user['login'],'password':self.password})
            assert response.status==200,await response.text()
            user.update(await response.json());self.clients.append(client)
        self.ca,self.cb,self.cm=self.clients
    async def asyncTearDown(self):
        for c in self.clients:await c.close()
        self.temp.cleanup()
    def headers(self,user=None):return {'X-CSRF-Token':(user or self.a)['csrf']}
    def png(self,metadata=False):
        out=io.BytesIO();info=PngImagePlugin.PngInfo()
        if metadata:info.add_text('prompt','metadata solo para la prueba')
        Image.new('RGBA',(12,12),(130,90,60,128)).save(out,format='PNG',pnginfo=info);return out.getvalue()
    async def upload(self,client=None,user=None):
        data=FormData();data.add_field('imagen',self.png(True),filename='../../config_local.json',content_type='image/png')
        r=await (client or self.ca).post('/api/referencias',data=data,headers=self.headers(user))
        self.assertEqual(r.status,201,await r.text());return await r.json()
    async def job(self,refs=None,kind='2d',request_id=None):
        data={'tipo':kind,'prompt':'figura sencilla','referencias':refs or []}
        if request_id:data['request_id']=request_id
        r=await self.ca.post('/api/trabajos',json=data,headers=self.headers());self.assertEqual(r.status,201,await r.text());return await r.json()
    async def test_sin_sesion_no_hay_datos(self):
        client=TestClient(self.server,cookie_jar=CookieJar(unsafe=True));await client.start_server();self.clients.append(client)
        for path in ['/api/me','/api/trabajos','/api/archivos','/api/usuarios']:
            self.assertEqual((await client.get(path)).status,401)
    async def test_identidad_tailscale_no_sustituye_sesion(self):
        client=TestClient(self.server);await client.start_server();self.clients.append(client)
        r=await client.get('/api/me',headers={'Tailscale-User-Login':'persona_a@example.invalid'})
        self.assertEqual(r.status,401)
    async def test_referencia_privada_y_nombre_opaco(self):
        f=await self.upload();self.assertNotIn('path',f)
        self.assertFalse((self.root/'config_local.json').exists())
        for action in ['vista','descargar']:
            self.assertEqual((await self.ca.get(f"/api/archivos/{f['id']}/{action}")).status,200)
            self.assertEqual((await self.cb.get(f"/api/archivos/{f['id']}/{action}")).status,404)
        other=await (await self.cb.get('/api/archivos')).json();self.assertEqual(other['archivos'],[])
    async def test_limpia_metadata_y_conserva_alpha(self):
        f=await self.upload();response=await self.ca.get(f"/api/archivos/{f['id']}/descargar")
        with Image.open(io.BytesIO(await response.read())) as image:
            self.assertNotIn('prompt',image.info);self.assertEqual(image.mode,'RGBA')
    async def test_no_se_puede_borrar_referencia_ajena(self):
        f=await self.upload();r=await self.cb.delete('/api/archivos/'+f['id'],headers=self.headers(self.b));self.assertEqual(r.status,404)
        self.assertEqual((await self.ca.get('/api/archivos/'+f['id']+'/vista')).status,200)
    async def test_trabajo_y_cancelacion_por_propietario(self):
        job=await self.job();ident=job['id'];self.assertEqual(job['owner'],self.a['id'])
        self.assertEqual(job['state'],'pendiente_de_motor')
        self.assertEqual((await self.cb.get('/api/trabajos/'+ident)).status,404)
        self.assertEqual((await self.cb.post('/api/trabajos/'+ident+'/cancelar',headers=self.headers(self.b),json={})).status,404)
        self.assertEqual((await self.cb.delete('/api/trabajos/'+ident,headers=self.headers(self.b))).status,404)
        self.assertEqual((await self.ca.post('/api/trabajos/'+ident+'/cancelar',headers=self.headers(),json={})).status,200)
    async def test_no_permite_apropiar_referencias_ajenas(self):
        f=await self.upload()
        r=await self.cb.post('/api/trabajos',json={'tipo':'3d','referencias':[f['id']]},headers=self.headers(self.b))
        self.assertEqual(r.status,404)
    async def test_rechaza_grafos_y_propietarios_en_el_body(self):
        for extra in [{'owner':self.b['id']},{'grafo':{}},{'path':'../private'}]:
            r=await self.ca.post('/api/trabajos',json={'tipo':'2d','prompt':'prueba',**extra},headers=self.headers());self.assertEqual(r.status,400)
    async def test_referencias_compartidas_hasta_ultimo_trabajo(self):
        f=await self.upload();one=await self.job([f['id']]);two=await self.job([f['id']])
        self.assertEqual((await self.ca.delete('/api/archivos/'+f['id'],headers=self.headers())).status,409)
        self.assertEqual((await self.ca.delete('/api/trabajos/'+one['id'],headers=self.headers())).status,200)
        self.assertEqual((await self.ca.get('/api/archivos/'+f['id']+'/vista')).status,200)
        self.assertEqual((await self.ca.delete('/api/trabajos/'+two['id'],headers=self.headers())).status,200)
        self.assertEqual((await self.ca.get('/api/archivos/'+f['id']+'/vista')).status,404)
        self.assertEqual(len(list((self.root/'usuarios').rglob('*.png'))),0)
    async def test_resultados_descarga_y_borrado_sin_cruces(self):
        job=await self.job();file=self.store.save_file(self.a['id'],self.png(),'image/png','resultado',job['id'])
        self.assertEqual((await self.cb.get('/api/archivos/'+file['id']+'/descargar')).status,404)
        self.assertEqual((await self.cm.get('/api/archivos/'+file['id']+'/descargar')).status,200)
        self.assertEqual((await self.ca.delete('/api/trabajos/'+job['id'],headers=self.headers())).status,200)
        self.assertEqual((await self.ca.get('/api/trabajos/'+job['id'])).status,404)
        self.assertEqual(len(list((self.root/'usuarios').rglob('*.png'))),0)
    async def test_idempotencia(self):
        one=await self.job(request_id='misma-solicitud');two=await self.job(request_id='misma-solicitud');self.assertEqual(one['id'],two['id'])
        r=await self.ca.post('/api/trabajos',json={'tipo':'2d','prompt':'diferente','request_id':'misma-solicitud'},headers=self.headers());self.assertEqual(r.status,409)
    async def test_csrf_y_origen(self):
        r=await self.ca.post('/api/trabajos',json={'tipo':'2d','prompt':'prueba'});self.assertEqual(r.status,403)
        r=await self.ca.post('/api/trabajos',json={'tipo':'2d','prompt':'prueba'},headers={**self.headers(),'Origin':'https://otro.example.invalid'});self.assertEqual(r.status,403)
    async def test_administracion_no_accesible_a_clientes(self):
        self.assertEqual((await self.ca.get('/api/usuarios')).status,403)
        r=await self.ca.post('/api/usuarios',json={'usuario':'intruso','password':self.password,'rol':'administrador'},headers=self.headers());self.assertEqual(r.status,403)
    async def test_desactivar_revoca_sesiones(self):
        r=await self.cm.patch('/api/usuarios/'+self.a['id'],json={'activo':False},headers=self.headers(self.admin));self.assertEqual(r.status,200)
        self.assertEqual((await self.ca.get('/api/me')).status,401)
    async def test_no_desactivar_ultimo_administrador(self):
        r=await self.cm.patch('/api/usuarios/'+self.admin['id'],json={'activo':False},headers=self.headers(self.admin));self.assertEqual(r.status,409)
    async def test_sesion_caducada(self):
        with self.store.connect() as db:db.execute('UPDATE sessions SET expires=0 WHERE user_id=?',(self.a['id'],))
        self.assertEqual((await self.ca.get('/api/me')).status,401)
    async def test_logout_y_password_no_almacenado_en_claro(self):
        with self.store.connect() as db:
            row=db.execute('SELECT password FROM users WHERE id=?',(self.a['id'],)).fetchone()
            self.assertNotEqual(row[0],self.password);self.assertTrue(row[0].startswith('scrypt$'))
        self.assertEqual((await self.ca.post('/api/logout',headers=self.headers(),json={})).status,200)
        self.assertEqual((await self.ca.get('/api/me')).status,401)
    async def test_credenciales_erroneas_limitadas(self):
        for _ in range(5):
            r=await self.ca.post('/api/login',json={'usuario':'persona_a','password':'incorrecta'});self.assertEqual(r.status,401)
        r=await self.ca.post('/api/login',json={'usuario':'persona_a','password':'incorrecta'});self.assertEqual(r.status,429)
    async def test_ficheros_sin_escape_del_propietario(self):
        f=await self.upload()
        with self.store.connect() as db:db.execute('UPDATE files SET path=? WHERE id=?',('../externo.txt',f['id']))
        self.assertEqual((await self.ca.get('/api/archivos/'+f['id']+'/descargar')).status,404)
    async def test_no_hay_proxy_a_comfyui(self):
        for path in ['/history','/view?filename=config_local.json','/ws','/prompt']:
            self.assertEqual((await self.ca.get(path)).status,404)
    async def test_rechaza_archivo_no_imagen(self):
        data=FormData();data.add_field('imagen',b'not an image',filename='falso.png',content_type='image/png')
        r=await self.ca.post('/api/referencias',data=data,headers=self.headers());self.assertEqual(r.status,400)
    async def test_persistencia(self):
        f=await self.upload();job=await self.job([f['id']]);fresh=Store(self.root)
        self.assertEqual(fresh.job(job['id'],self.a)['owner'],self.a['id'])
    async def test_cookie_y_cabeceras(self):
        r=await self.ca.post('/api/login',json={'usuario':'persona_a','password':self.password})
        self.assertTrue(r.cookies['exo_session']['httponly']);self.assertEqual(r.cookies['exo_session']['samesite'],'Strict')
        self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
    async def test_cookie_secure_predeterminada(self):
        server=TestServer(create_app(self.root));client=TestClient(server);await client.start_server();self.clients.append(client)
        r=await client.post('/api/login',json={'usuario':'persona_a','password':self.password})
        self.assertEqual(r.status,200);self.assertTrue(r.cookies['exo_session']['secure'])
    async def test_administrador_crea_cuenta_sin_exponer_hash(self):
        r=await self.cm.post('/api/usuarios',json={'usuario':'nueva_persona','password':self.password,'rol':'operador'},headers=self.headers(self.admin))
        self.assertEqual(r.status,201);self.assertEqual((await r.json())['role'],'operador')
        result=await (await self.cm.get('/api/usuarios')).json()
        self.assertTrue(any(u['login']=='nueva_persona' for u in result['usuarios']))
        self.assertFalse(any('password' in u for u in result['usuarios']))
    async def test_login_de_otro_origen_rechazado(self):
        r=await self.ca.post('/api/login',json={'usuario':'persona_a','password':self.password},headers={'Origin':'https://otro.example.invalid'})
        self.assertEqual(r.status,403);self.assertNotIn('exo_session',r.cookies)

if __name__=='__main__':unittest.main(verbosity=2)
