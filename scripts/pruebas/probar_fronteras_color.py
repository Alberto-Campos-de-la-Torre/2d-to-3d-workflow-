import sys, types, importlib, unittest
from pathlib import Path
import numpy as np

pkg=types.ModuleType('exo_test');root=Path(__file__).resolve().parents[2]; ruta=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not ruta.exists():ruta=root/'custom_nodes/exo_filaments'
pkg.__path__=[str(ruta)]
sys.modules[pkg.__name__]=pkg
paleta_por_cara=importlib.import_module('exo_test.colores_caras').paleta_por_cara

class Fronteras(unittest.TestCase):
    def test_mayoria_sin_mezclar(self):
        c=np.array([[1,0,0],[1,0,0],[0,0,1]],dtype=float)
        e,p=paleta_por_cara(np.array([[0,1,2]]),c,2,'#ff0000,#0000ff')
        np.testing.assert_array_equal(p[e],[c[0]])
    def test_tres_colores_no_crean_cuarto(self):
        c=np.eye(3)
        e,p=paleta_por_cara(np.array([[0,1,2]]),c,3,'#ff0000,#00ff00,#0000ff')
        self.assertTrue(any(np.array_equal(p[e[0]],rgb) for rgb in c))
    def test_preservar_negro_gris(self):
        c=np.array([[.03,.03,.03],[.35,.35,.35],[.9,.5,.2],[.2,.5,.2]])
        e,p=paleta_por_cara(np.array([[i,i,i] for i in range(4)]),c,4,'')
        self.assertEqual(len(np.unique(e)),4)

if __name__=='__main__':unittest.main(verbosity=2)
