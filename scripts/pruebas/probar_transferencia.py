import sys,unittest
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[2]
pkg=root/'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not pkg.exists():pkg=root/'custom_nodes/exo_filaments'
sys.path.insert(0,str(pkg))
from transferencia_color import transferir
class Transferencia(unittest.TestCase):
    def test_reparacion_no_toma_color_interior(self):
        ref=np.array([[0.,0,0],[0,1,0]])
        vox=np.array([[0.,0,0],[0,1,0],[.1,0,0],[.1,1,0]])
        rgb=np.array([[1,.5,.2],[1,.5,.2],[0,0,0],[0,0,0]])
        color,d=transferir(np.array([[.1,0,0],[.1,1,0]]),ref,vox,rgb)
        np.testing.assert_allclose(color,[[1,.5,.2],[1,.5,.2]])
    def test_detalles_no_se_promedian(self):
        v=np.array([[0.,0,0],[1,0,0]])
        rgb=np.array([[0,0,0],[1,.5,.2]])
        color,_=transferir(v,v,v,rgb)
        np.testing.assert_array_equal(color,rgb)
    def test_vertice_dual_conserva_voxel_propietario(self):
        vox=np.array([[0.,0,0],[.1,0,0]])
        ref=np.array([[.09,0,0],[.14,0,0]])
        rgb=np.array([[1,.5,.2],[0,0,0]])
        color,_=transferir(ref,ref,vox,rgb,resolucion=10)
        np.testing.assert_array_equal(color,rgb)
if __name__=='__main__':unittest.main(verbosity=2)
