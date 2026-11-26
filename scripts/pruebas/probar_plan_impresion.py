"""Diez casos de resultado conocido para el diagnostico Creality."""
import sys,types,importlib,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/"ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments"
if not PKG.exists():PKG=ROOT/"custom_nodes/exo_filaments"
m=types.ModuleType("exo_plan_test");m.__path__=[str(PKG)];sys.modules[m.__name__]=m
mod=importlib.import_module("exo_plan_test.plan_impresion")
def cube(rgb=(1,0,0),offset=(0,0,0),scale=20):
    v=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],float)*scale+offset
    f=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    return v,f,np.tile(rgb,(8,1))
def combine(*parts):
    vs=[];fs=[];cs=[];count=0
    for v,f,c in parts:vs.append(v);fs.append(f+count);cs.append(c);count+=len(v)
    return np.concatenate(vs),np.concatenate(fs),np.concatenate(cs)
class Plan(unittest.TestCase):
    def test_01_monocolor(self):
        p=mod.analizar(*cube());self.assertEqual(p['colores'],1);self.assertEqual(p['coexistencia_pct'],0)
    def test_02_colores_lado_a_lado(self):
        p=mod.analizar(*combine(cube(),cube((0,0,1),(30,0,0))))
        self.assertEqual(p['colores'],2);self.assertEqual(p['coexistencia_pct'],100);self.assertGreaterEqual(p['candidatas'],2)
    def test_03_colores_por_altura(self):
        p=mod.analizar(*combine(cube(),cube((0,0,1),(0,25,0))))
        self.assertLess(p['coexistencia_pct'],2)
    def test_04_mismo_color_distintas_regiones(self):
        p=mod.analizar(*combine(cube(),cube(offset=(30,0,0))))
        self.assertEqual(p['regiones_total'],2);self.assertEqual(p['colores'],1)
    def test_05_detalle_pequeno(self):
        p=mod.analizar(*combine(cube(),cube((0,0,1),(30,0,0),1)))
        self.assertEqual(p['candidatas'],1)
    def test_06_capacidad_cfs(self):
        p=mod.analizar(*combine(cube(),cube((0,0,1),(30,0,0))),plazas=1)
        self.assertTrue(any('Mas colores' in a for a in p['advertencias']))
    def test_07_tpu(self):
        p=mod.analizar(*cube(),material='TPU')
        self.assertTrue(any('TPU no compatible' in a for a in p['advertencias']))
    def test_08_fuera_cama(self):
        self.assertFalse(mod.analizar(*cube(scale=400))['cabe'])
    def test_09_validacion(self):
        for value in [0,-1,float('nan'),2]:
            with self.subTest(value=value),self.assertRaises(ValueError):mod.analizar(*cube(),capa_mm=value)
        v,f,c=cube();v[0,0]=float('nan')
        with self.assertRaises(ValueError):mod.analizar(v,f,c)
    def test_10_ausencia_color_y_no_inventa_costes(self):
        v,f,c=cube();self.assertIsNone(mod.analizar(v,f)['colores'])
        p=mod.analizar(v,f,c)
        for k in ['purga_g','tiempo_h','ahorro']:self.assertIsNone(p[k])
if __name__=='__main__':unittest.main(verbosity=2)
