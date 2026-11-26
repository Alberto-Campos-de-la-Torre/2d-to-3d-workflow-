import base64,importlib,sys,types,unittest
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[2]
pkg=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not pkg.exists():pkg=root/'custom_nodes/exo_filaments'
module=types.ModuleType('exo_segment_test');module.__path__=[str(pkg)]
sys.modules[module.__name__]=module
segmentar=importlib.import_module('exo_segment_test.segmentacion_imagen').segmentar

class Segmentacion(unittest.TestCase):
    def test_fondo_excluido_y_proporciones(self):
        im=np.zeros((100,100,3),np.float32);im[:]=[.8,0,.8]
        mask=np.zeros((100,100),np.float32);mask[40:60,40:60]=1
        colors=[[0,0,0],[.5,.5,.5],[.9,.7,.5],[0,.6,0]]
        for i,c in enumerate(colors):im[40+i*5:45+i*5,40:60]=c
        r=segmentar(im,mask,4)
        self.assertEqual(len(r['colores']),4)
        self.assertEqual({c['color'] for c in r['colores']},{'#000000','#7f7f7f','#e5b27f','#009900'})
        self.assertEqual([c['porcentaje'] for c in r['colores']],[25]*4)
        regions=np.frombuffer(base64.b64decode(r['regiones']),np.uint8).reshape(100,100)
        self.assertTrue((regions[mask==0]==0).all())
        self.assertTrue((regions[mask==1]>0).all())
    def test_monocolor_no_inventa_filamentos(self):
        r=segmentar(np.ones((20,20,3)),np.ones((20,20)),4)
        self.assertEqual(r['colores'],[{'color':'#ffffff','porcentaje':100.0}])
    def test_limite_y_fondo_vacio(self):
        with self.assertRaises(ValueError):segmentar(np.zeros((5,5,3)),np.zeros((5,5)),4)
        with self.assertRaises(ValueError):segmentar(np.zeros((5,5,3)),np.ones((5,5)),17)
    def test_maximo_colores_y_mapa(self):
        rng=np.random.default_rng(22)
        r=segmentar(rng.random((360,240,3)),np.ones((360,240)),3)
        labels=np.frombuffer(base64.b64decode(r['regiones']),np.uint8)
        self.assertLessEqual(len(r['colores']),3)
        self.assertEqual(len(labels),r['ancho']*r['alto'])
        self.assertLessEqual(labels.max(),len(r['colores']))
        self.assertAlmostEqual(sum(c['porcentaje'] for c in r['colores']),100,places=1)

if __name__=='__main__':unittest.main(verbosity=2)
