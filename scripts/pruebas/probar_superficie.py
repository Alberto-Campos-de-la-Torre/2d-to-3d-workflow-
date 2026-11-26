import sys
from pathlib import Path
import unittest
import numpy as np
from scipy.spatial import cKDTree
root=Path(__file__).resolve().parents[2]
pkg=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not pkg.exists():pkg=root/'custom_nodes/exo_filaments'
sys.path.insert(0,str(pkg))
from superficie import reconstruir

class Superficie(unittest.TestCase):
    def comprobar(self, campo):
        v, f = reconstruir(campo, np.zeros(3), 1.0)
        e = np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
        _, cuenta = np.unique(e,axis=0,return_counts=True)
        self.assertTrue(np.all(cuenta==2))
        a,b,c = v[f[:,0]],v[f[:,1]],v[f[:,2]]
        self.assertGreater(np.einsum('ij,ij->i',a,np.cross(b,c)).sum(),0)
        return v,f
    def test_limite_rejilla(self):
        self.comprobar(np.ones((16,20,24),dtype=bool))
    def test_esfera(self):
        grid = np.indices((48,48,48)).transpose(1,2,3,0)
        campo = np.linalg.norm(grid-24,axis=-1)<16
        self.comprobar(campo)
    def test_ejes_y_escala(self):
        campo=np.zeros((16,20,24),dtype=bool);campo[2:8,3:13,4:20]=True
        v,_=reconstruir(campo,np.array([10,20,30]),2)
        np.testing.assert_allclose(v.max(0)-v.min(0),[3,5,8])
    def test_contacto_diagonal(self):
        campo=np.zeros((12,12,12),dtype=bool);campo[2:6,2:6,2:6]=True;campo[6:10,6:10,2:6]=True
        self.comprobar(campo)

if __name__=='__main__':unittest.main(verbosity=2)
