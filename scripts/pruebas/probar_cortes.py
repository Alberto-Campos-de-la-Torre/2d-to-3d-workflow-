"""Regresion de corte cerrado y exportacion completa."""
import sys,types,importlib,unittest,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from probar_plan_impresion import cube,combine,PKG
m=types.ModuleType("exo_cortes_test");m.__path__=[str(PKG)];sys.modules[m.__name__]=m
mod=importlib.import_module("exo_cortes_test.separacion")
class Cortes(unittest.TestCase):
    def test_ejes_y_volumen(self):
        for eje in 'xyz':
            with self.subTest(eje=eje):
                parts,report=mod.cortar(*cube(),eje=eje)
                self.assertLess(report['error_volumen_pct'],.001)
                self.assertEqual(len(parts),2)
                for p in parts:self.assertAlmostEqual(p['volumen_mm3'],4000,places=3)
    def test_tamano_no_cambia(self):
        p,info=mod.cortar(*cube(),porcentaje=25)
        self.assertAlmostEqual(sum(x['volumen_mm3'] for x in p),8000)
        self.assertAlmostEqual(min(x['dimensiones_mm'][2] for x in p),5)
    def test_normales_invertidas(self):
        v,f,c=cube();f[::2]=f[::2,::-1]
        p,info=mod.cortar(v,f,c)
        self.assertLess(info['error_volumen_pct'],.001)
    def test_rechaza_agujeros(self):
        v,f,c=cube()
        with self.assertRaises(ValueError):mod.cortar(v,f[:-1],c)
    def test_rechaza_plano_fuera(self):
        for pct in [0,100,float('nan')]:
            with self.subTest(pct=pct),self.assertRaises(ValueError):mod.cortar(*cube(),porcentaje=pct)
    def test_hueco_se_conserva(self):
        from manifold3d import Manifold
        shell=Manifold.cube((20,20,20))-Manifold.cube((10,10,10)).translate((5,5,5))
        mesh=shell.to_mesh();parts,report=mod.cortar(mesh.vert_properties,mesh.tri_verts)
        self.assertAlmostEqual(sum(p['volumen_mm3'] for p in parts),7000,places=2)
    def test_colores_y_posicion(self):
        v,f,c=cube();parts,report=mod.cortar(v,f,c)
        for p in parts:
            self.assertTrue(np.allclose(p['colores'],[1,0,0]))
            self.assertAlmostEqual(p['stl_vertices'][:,2].min(),0)
            self.assertAlmostEqual(np.linalg.det(p['rotacion']),1)
    def test_exportar_no_sobrescribe(self):
        with tempfile.TemporaryDirectory(prefix='exo_corte_test_') as tmp:
            root=Path(tmp);v,f,c=cube();source=root/'original.obj'
            source.write_text(''.join('v %s %s %s %s %s %s\n'%tuple(row) for row in np.c_[v,c])+''.join('f %d %d %d\n'%tuple(row+1) for row in f))
            result=mod.ejecutar(source,root/'resultado','y',50)
            self.assertEqual(len(result['archivos']),7)
            self.assertTrue((root/'resultado/montaje.json').is_file())
            with self.assertRaises(FileExistsError):mod.ejecutar(source,root/'resultado','y',50)
    def test_componentes_se_reportan(self):
        parts,report=mod.cortar(*combine(cube(),cube(offset=(30,0,0))))
        self.assertEqual([p['componentes'] for p in parts],[2,2])
if __name__=='__main__':unittest.main(verbosity=2)
