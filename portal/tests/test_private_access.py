import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient,TestServer,make_mocked_request
from portal.app import create_app,STORE
from portal.private_access import PrivateAccess
from portal.pilot import prepare,publish,unpublish
from portal.pilot import port_free
from portal.store_errors import ErrorPortal


class PrivatePilot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=self.root/'acceso-privado.json'
        self.origin='https://portal.example.invalid:10000'
        self.data={'origen':self.origin,'identidades_permitidas':['operador@example.invalid']}
        self.write()
        self.app=create_app(self.root/'data',private_config=self.config)
        self.client=TestClient(TestServer(self.app));await self.client.start_server()
        self.headers={'Host':'portal.example.invalid:10000','Tailscale-User-Login':'operador@example.invalid'}
    def write(self):self.config.write_text(json.dumps(self.data),encoding='utf-8')
    async def asyncTearDown(self):await self.client.close();self.temp.cleanup()
    async def test_toda_ruta_requiere_identidad(self):
        for path in ('/','/assets/app.js','/api/me','/prompt','/history'):
            self.assertEqual((await self.client.get(path)).status,403)
    async def test_identidad_no_reemplaza_login(self):
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,200)
        self.assertEqual((await self.client.get('/api/me',headers=self.headers)).status,401)
    async def test_host_estricto(self):
        h={**self.headers,'Host':'otro.example.invalid:10000'}
        self.assertEqual((await self.client.get('/',headers=h)).status,403)
    async def test_origen_estricto_incluso_get(self):
        h={**self.headers,'Origin':'https://otro.example.invalid'}
        self.assertEqual((await self.client.get('/',headers=h)).status,403)
    async def test_identidad_no_permitida(self):
        h={**self.headers,'Tailscale-User-Login':'otra@example.invalid'}
        self.assertEqual((await self.client.get('/',headers=h)).status,403)
    async def test_cabeceras_identidad_duplicadas(self):
        h=[*self.headers.items(),('Tailscale-User-Login','otra@example.invalid')]
        self.assertEqual((await self.client.get('/',headers=h)).status,403)
    async def test_revocacion_inmediata(self):
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,200)
        self.data['identidades_permitidas']=[];self.write()
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,403)
    async def test_config_rota_o_eliminada_cierra_acceso(self):
        self.config.write_text('{',encoding='utf-8')
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,403)
        self.config.unlink()
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,403)
    async def test_cambio_origen_requiere_reinicio(self):
        self.data['origen']='https://otra.example.invalid:10000';self.write()
        self.assertEqual((await self.client.get('/',headers=self.headers)).status,403)
    async def test_cookie_segura_y_rol_independiente(self):
        password=secrets.token_urlsafe(20)
        self.app[STORE].create_user('persona',password,'cliente')
        r=await self.client.post('/api/login',headers={**self.headers,'Origin':self.origin},json={'usuario':'persona','password':password})
        self.assertEqual(r.status,200)
        self.assertTrue(r.cookies['exo_session']['secure']);self.assertTrue(r.cookies['exo_session']['httponly'])
        self.assertEqual((await r.json())['role'],'cliente')
    async def test_no_permite_cookie_insegura(self):
        with self.assertRaises(ValueError):create_app(self.root/'other',secure_cookies=False,private_config=self.config)
    async def test_no_acepta_proxy_remoto(self):
        req=make_mocked_request('GET','/',headers=self.headers)
        with self.assertRaises(ErrorPortal):PrivateAccess(self.config).check(req)
    async def test_no_expone_api_del_motor(self):
        for path in ('/prompt','/history','/view','/ws'):
            self.assertEqual((await self.client.get(path,headers=self.headers)).status,404)


class Deployment(unittest.TestCase):
    def test_detecta_socket_ocupado(self):
        import socket
        with socket.socket() as sock:
            sock.bind(('localhost',0));sock.listen()
            self.assertFalse(port_free(sock.getsockname()[1]))
    def test_preparacion_solo_propietario_y_copia_previa(self):
        status={'BackendState':'Running','Self':{'Online':True,'DNSName':'portal.example.invalid.','UserID':42},
                'User':{'42':{'LoginName':'propietario@example.invalid'}}}
        before={'TCP':{'8443':{'HTTPS':True}}}
        with tempfile.TemporaryDirectory() as tmp,patch('portal.pilot.port_free',return_value=True),patch('portal.pilot.tailscale',side_effect=[json.dumps(status),json.dumps(before)]) as run:
            path=prepare(tmp,Path('tailscale'))
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['identidades_permitidas'],['propietario@example.invalid'])
            self.assertEqual(json.loads((Path(tmp)/'serve-anterior.json').read_text()),before)
            self.assertEqual(run.call_count,2)
    def test_publicacion_preserva_servicios_y_solo_serve(self):
        import urllib.error
        host='portal.example.invalid:10000';tcp={'HTTPS':True}
        before={'TCP':{'8443':tcp},'Web':{'otro.example.invalid:8443':{'Handlers':{'/':{'Proxy':'http://localhost:8788'}}}}}
        after={**before,'TCP':{**before['TCP'],'10000':tcp},'Web':{**before['Web'],host:{'Handlers':{'/':{'Proxy':'http://localhost:8090'}}}}}
        with tempfile.TemporaryDirectory() as tmp,patch('portal.pilot.port_free',return_value=True),patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('http://localhost',403,'Forbidden',None,None)),patch('portal.pilot.tailscale',side_effect=[json.dumps(before),'',json.dumps(after)]) as run:
            root=Path(tmp)
            (root/'acceso-privado.json').write_text(json.dumps({'origen':'https://'+host,'identidades_permitidas':[],'puerto_https':10000,'puerto_local':8090}))
            publish(root,Path('tailscale'))
            self.assertTrue((root/'serve-piloto.json').is_file())
            self.assertEqual(run.call_args_list[1].args[1:],('serve','--bg','--https=10000','http://localhost:8090'))
    def test_preparacion_no_reemplaza_puerto(self):
        status={'BackendState':'Running','Self':{'Online':True}}
        with tempfile.TemporaryDirectory() as tmp,patch('portal.pilot.tailscale',side_effect=[json.dumps(status),json.dumps({'TCP':{'10000':{'HTTPS':True}}})]) as run:
            with self.assertRaises(ErrorPortal):prepare(tmp,Path('tailscale'))
            self.assertEqual(run.call_count,2)
            self.assertFalse((Path(tmp)/'acceso-privado.json').exists())
    def test_no_guarda_config_en_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'.git').mkdir()
            with self.assertRaises(ErrorPortal):prepare(Path(tmp)/'private',Path('tailscale'))
    def test_retirada_no_borra_ruta_ajena(self):
        with tempfile.TemporaryDirectory() as tmp,patch('portal.pilot.tailscale',return_value='{}') as run:
            root=Path(tmp)
            (root/'acceso-privado.json').write_text(json.dumps({'origen':'https://portal.example.invalid:10000','identidades_permitidas':[]}))
            (root/'serve-piloto.json').write_text(json.dumps({'puerto':'10000','tcp':{'HTTPS':True},'web':{}}))
            with self.assertRaises(ErrorPortal):unpublish(root,Path('tailscale'))
            self.assertEqual(run.call_count,1)
    def test_publicacion_no_sobrescribe_ruta(self):
        with tempfile.TemporaryDirectory() as tmp,patch('portal.pilot.tailscale',return_value=json.dumps({'TCP':{'10000':{'HTTPS':True}}})) as run:
            root=Path(tmp)
            (root/'acceso-privado.json').write_text(json.dumps({'origen':'https://portal.example.invalid:10000','identidades_permitidas':[],'puerto_https':10000,'puerto_local':8090}))
            with self.assertRaises(ErrorPortal):publish(root,Path('tailscale'))
            self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()
