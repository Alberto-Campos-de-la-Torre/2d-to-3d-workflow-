import sys,unittest
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[2]
pkg=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not pkg.exists():pkg=root/'custom_nodes/exo_filaments'
sys.path.insert(0,str(pkg))
from proyeccion_color import proyectar
class Proyeccion(unittest.TestCase):
    def test_frente_y_espalda(self):
        v=np.array([[0.,0,1],[1,0,1],[1,1,1],[0,1,1],[0,0,0],[1,0,0],[1,1,0],[0,1,0]])
        f=np.array([[0,1,2],[0,2,3],[4,6,5],[4,7,6]])
        c=np.zeros((8,3));im=np.ones((5,5,3));m=np.ones((5,5))
        nuevo,vis=proyectar(v,f,c,im,m)
        self.assertTrue(vis[:4].all());self.assertFalse(vis[4:].any())
        np.testing.assert_array_equal(nuevo[:4],np.ones((4,3)))
        np.testing.assert_array_equal(nuevo[4:],np.zeros((4,3)))
    def test_mascara_vacia(self):
        with self.assertRaises(ValueError):proyectar(np.eye(3),np.array([[0,1,2]]),np.eye(3),np.zeros((5,5,3)),np.zeros((5,5)))
if __name__=='__main__':unittest.main(verbosity=2)
