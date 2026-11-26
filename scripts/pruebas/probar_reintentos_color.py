"""Reintentos de textura acotados, sin cambiar la geometria ni ocultar QC ausente."""
import ast,sys,types,unittest,asyncio,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not PKG.exists():PKG=ROOT/'custom_nodes/exo_filaments'
tree=ast.parse((PKG/'pieza.py').read_text(encoding='utf-8'))
fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_convertir')
class Response:
    def __init__(self,data):self.data=data
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass
    async def json(self):return self.data
class Test(unittest.TestCase):
    def run_case(self,flags):
        graphs=[];states={'x':{'terminado':False}};grafos={};collected=[]
        class Session:
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            def post(self,url,json):
                import copy
                graphs.append(copy.deepcopy(json['prompt']))
                return Response({'prompt_id':str(len(graphs)), 'node_errors':{}})
            def get(self,url):
                i=int(url.rsplit('/',1)[-1]);flag=flags[min(i-1,len(flags)-1)]
                qc={} if flag is None else {'revision_color':{'color_no_coincide':flag,'textura_corrupta':False}}
                return Response({str(i):{'status':{'status_str':'success'},'outputs':{'204':{'revision_pieza':[qc]}}}})
        async def no_wait(x):pass
        fake=types.ModuleType('aiohttp');fake.ClientSession=Session
        old=sys.modules.get('aiohttp');sys.modules['aiohttp']=fake
        env={'_trabajos':states,'_grafos_color':grafos,'time':time,'asyncio':types.SimpleNamespace(sleep=no_wait),
            'json':json,'_recoger':lambda state,data:collected.append(data)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'retry','exec'),env)
        graph={'66':{'inputs':{'seed':43,'steps':12}},'36':{'inputs':{'seed':42}},'82':{'inputs':{}}}
        try:asyncio.run(env['_convertir']('x',graph))
        finally:
            if old is None:sys.modules.pop('aiohttp',None)
            else:sys.modules['aiohttp']=old
        self.assertTrue(states['x']['terminado']);self.assertEqual(len(collected),1)
        for g in graphs:self.assertEqual(g['36'],graph['36']);self.assertEqual(g['66']['inputs']['steps'],12)
        return graphs,states['x']
    def test_approved_no_retry(self):
        graphs,state=self.run_case([False]);self.assertEqual(len(graphs),1);self.assertFalse(state['color_sin_verificar'])
    def test_retry_texture_only(self):
        graphs,state=self.run_case([True,False]);self.assertEqual(len(graphs),2)
        self.assertEqual(graphs[1]['66']['inputs']['seed'],44);self.assertNotIn('82',graphs[1]);self.assertFalse(state['color_requiere_revision'])
    def test_limit_two_retries(self):
        graphs,state=self.run_case([True]);self.assertEqual(len(graphs),3);self.assertTrue(state['color_requiere_revision'])
    def test_unknown_not_approved(self):
        graphs,state=self.run_case([None]);self.assertEqual(len(graphs),1);self.assertTrue(state['color_sin_verificar'])
if __name__=='__main__':unittest.main(verbosity=2)
