"""El juez compara la referencia y conserva incertidumbre si falta un veredicto."""
import sys,types,importlib,unittest
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not PKG.exists():PKG=ROOT/'custom_nodes/exo_filaments'
pkg=types.ModuleType('exo_juez_test');pkg.__path__=[str(PKG)];sys.modules[pkg.__name__]=pkg
m=importlib.import_module('exo_juez_test.revision_pieza')
class Juez(unittest.TestCase):
    def setUp(self):
        m.hoja_de_vistas=lambda mesh,lado:Image.new('RGB',(lado*2,lado*2),'red')
        m.medir_llenado=lambda mesh:.4
        self.ref=Image.new('RGB',(64,96),'orange')
    def test_compara_regiones_y_referencia(self):
        import json
        seen=[]
        def fake(image,prompt,**kwargs):
            seen.append((image.size,prompt));return 'JSON: '+json.dumps({'color_no_coincide':True,'textura_corrupta':False}),''
        m._preguntar=fake
        result,_=m.revisar_pieza(None,lado=256,referencia=self.ref)
        self.assertIn('color_no_coincide',result['defectos']);self.assertFalse(result['apto'])
        self.assertEqual(seen[0][0],(768,548));self.assertIn('cara, orejas, cuello, manos',seen[0][1])
    def test_veredicto_incompleto_no_aprueba(self):
        m._preguntar=lambda *a,**k:('JSON: {}','')
        result,_=m.revisar_pieza(None,lado=256,referencia=self.ref)
        self.assertIsNone(result['apto']);self.assertTrue(result['avisos'])
    def test_servidor_no_disponible(self):
        m._preguntar=lambda *a,**k:('','No disponible')
        result,_=m.revisar_pieza(None,lado=256,referencia=self.ref)
        self.assertIsNone(result['apto']);self.assertTrue(result['avisos'])
if __name__=='__main__':unittest.main(verbosity=2)
