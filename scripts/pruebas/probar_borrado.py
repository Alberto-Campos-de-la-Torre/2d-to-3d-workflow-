import importlib,json,sys,tempfile,types,unittest
from pathlib import Path
from PIL import Image,PngImagePlugin

root=Path(__file__).resolve().parents[2]
pkg=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not pkg.exists():pkg=root/'custom_nodes/exo_filaments'
if not pkg.exists():pkg=Path(__file__).parent
module=types.ModuleType('exo_borrado_test');module.__path__=[str(pkg)]
sys.modules[module.__name__]=module
Catalogo=importlib.import_module('exo_borrado_test.resultados_archivos').Catalogo

class Borrado(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.out=self.base/'output';self.inp=self.base/'input'
        (self.out/'3d/exo').mkdir(parents=True);(self.out/'qwen21').mkdir();self.inp.mkdir()
        self.c=Catalogo(self.out,self.inp,self.base/'catalogo.json')
    def file(self,key,text='x'):
        p=self.c.ruta(key);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def png(self,key,refs=()):
        p=self.c.ruta(key)
        metadata=PngImagePlugin.PngInfo();metadata.add_text('prompt',json.dumps({str(i):{'class_type':'LoadImage','inputs':{'image':n}} for i,n in enumerate(refs)}))
        Image.new('RGB',(8,8)).save(p,pnginfo=metadata);return p
    def record(self,ident,files,refs=()):
        self.c.registros[ident]={'archivos':list(files),'referencias':list(refs),'historial':[ident],'antiguo':False}
    def delete(self,ident):return self.c.borrar(ident,self.c.plan(ident)['token'])
    def test_borra_exportaciones_textura_y_referencia(self):
        keys=['output:3d/exo/p.obj','output:3d/exo/p.mtl','output:3d/exo/t.png','input:foto.png']
        self.file(keys[0],'mtllib p.mtl');self.file(keys[1],'map_Kd t.png');self.png(keys[2]);self.png(keys[3])
        files=self.c.ampliar_archivos({keys[0]});self.record('a',files,[keys[3]])
        result=self.delete('a')
        self.assertEqual(set(result['eliminados']),set(keys));self.assertFalse(any(self.c.ruta(k).exists() for k in keys))
    def test_referencia_compartida_hasta_ultimo_resultado(self):
        for k in ['output:qwen21/a.png','output:qwen21/b.png','input:ref.png']:self.png(k)
        self.record('a',['output:qwen21/a.png'],['input:ref.png'])
        self.record('b',['output:qwen21/b.png'],['input:ref.png'])
        self.assertIn('input:ref.png',self.delete('a')['conservados'])
        self.assertTrue(self.c.ruta('input:ref.png').exists())
        self.delete('b');self.assertFalse(self.c.ruta('input:ref.png').exists())
    def test_referencias_en_cadena(self):
        self.png('input:uno.png',['dos.png']);self.png('input:dos.png');self.png('output:qwen21/a.png')
        self.record('a',['output:qwen21/a.png'],['input:uno.png'])
        self.assertEqual(set(self.delete('a')['referencias']),{'input:uno.png','input:dos.png'})
    def test_traversal_y_modelos_configuracion_prohibidos(self):
        for key in ['output:../secreto.png','input:../foo.png','output:models/a.glb','output:qwen21/a.safetensors','output:C:/datos.png','input:foo\\bar.png']:
            with self.assertRaises(ValueError,msg=key):self.c.ruta(key)
    def test_obj_externo_no_borra_archivo_externo(self):
        secret=self.base/'secret.mtl';secret.write_text('private')
        p=self.file('output:3d/exo/p.obj','mtllib ../../../secret.mtl')
        self.c.explorar();self.delete(self.c.buscar('output:3d/exo/p.obj'))
        self.assertTrue(secret.exists());self.assertFalse(p.exists())
    def test_confirmacion_caducada_no_borra(self):
        p=self.file('output:3d/exo/p.stl');self.record('a',['output:3d/exo/p.stl'])
        plan=self.c.plan('a');p.write_text('changed')
        with self.assertRaises(ValueError):self.c.borrar('a',plan['token'])
        self.assertTrue(p.exists())
    def test_no_borra_cache_compartida(self):
        for k in ['output:3d/exo/raw.glb','output:3d/exo/a.stl','output:3d/exo/b.stl']:self.file(k)
        self.record('a',['output:3d/exo/raw.glb','output:3d/exo/a.stl']);self.record('b',['output:3d/exo/raw.glb','output:3d/exo/b.stl'])
        self.delete('a');self.assertTrue(self.c.ruta('output:3d/exo/raw.glb').exists())
    def test_catalogo_sobrevive_reinicio(self):
        self.png('output:qwen21/a.png');self.png('input:ref.png');self.record('a',['output:qwen21/a.png'],['input:ref.png'])
        self.c.guardar();nuevo=Catalogo(self.out,self.inp,self.base/'catalogo.json')
        self.assertEqual(nuevo.registros,self.c.registros)
    def test_familias_no_borran_prefijos_parecidos(self):
        for key in ['output:3d/exo/p_1.obj','output:3d/exo/p_1.stl','output:3d/exo/p_10.stl']:self.file(key)
        self.c.explorar();self.delete(self.c.buscar('output:3d/exo/p_1.obj'))
        self.assertTrue(self.c.ruta('output:3d/exo/p_10.stl').exists())
    def test_copia_input_no_utilizada_se_borra(self):
        p=self.png('output:qwen21/a.png');self.c.ruta('input:qwen_a.png').write_bytes(p.read_bytes())
        self.record('a',['output:qwen21/a.png']);self.delete('a')
        self.assertFalse(self.c.ruta('input:qwen_a.png').exists())
    def test_historia_solo_salidas_de_guardado(self):
        p=self.png('output:qwen21/a.png');self.png('input:ref.png')
        self.file('output:3d/exo/ajeno.stl')
        graph={'1':{'class_type':'SaveImage','inputs':{}},'2':{'class_type':'ExoRevisarPieza','inputs':{}},'3':{'class_type':'LoadImage','inputs':{'image':'ref.png'}}}
        h={'prompt':[0,'a',graph],'outputs':{'1':{'images':[{'filename':p.name,'subfolder':'qwen21','type':'output'}]},'2':{'text':['3d/exo/ajeno.stl']}}}
        self.c.registrar_historia('a',h)
        self.assertEqual(self.c.registros['a']['archivos'],['output:qwen21/a.png'])
        self.assertEqual(self.c.registros['a']['referencias'],['input:ref.png'])
    def test_alias_de_referencia_se_normalizan(self):
        self.png('input:ref.png')
        graph={str(i):{'class_type':'LoadImage','inputs':{'image':name}} for i,name in enumerate(['ref.png','./ref.png','REF.PNG'])}
        self.assertEqual(self.c.referencias(graph),{'input:ref.png'})
    def test_no_borra_imagen_usada_por_otro_resultado(self):
        self.png('output:qwen21/a.png');self.png('output:qwen21/b.png');self.png('input:ref.png')
        self.record('a',['output:qwen21/a.png'],['input:ref.png'])
        self.record('b',['output:qwen21/b.png'],['output:qwen21/a.png'])
        with self.assertRaises(ValueError):self.c.plan('a')
        self.assertTrue(self.c.ruta('input:ref.png').exists())

if __name__=='__main__':unittest.main(verbosity=2)
