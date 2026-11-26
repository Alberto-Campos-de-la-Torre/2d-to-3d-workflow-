"""Verifica topología y materiales del archivo serializado para el laminador."""
import ast
import importlib
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import numpy as np
from manifold3d import Manifold, Mesh as MeshManifold

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments'
if not PKG.exists():
    PKG = ROOT / 'custom_nodes/exo_filaments'
if not PKG.exists():
    PKG = Path(r'D:\AI3D\ComfyUI_windows_portable\ComfyUI\custom_nodes\exo_filaments')
m = types.ModuleType('exo_export')
m.__path__ = [str(PKG)]
sys.modules[m.__name__] = m
pal = importlib.import_module('exo_export.paleta')
source = Path(__file__).with_name('nodes.py')
if not source.exists():
    source = PKG / 'nodes.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
funciones = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ('_malla_exportable', '_escribir_obj', '_escribir_stl')]
env = dict(__name__='exo_export.nodes', __package__='exo_export', np=np, os=os, Manifold=Manifold, MeshManifold=MeshManifold,
           agrupar=pal.agrupar, leer_paleta=pal.leer_paleta)
import struct
env['struct'] = struct
exec(compile(ast.Module(body=funciones, type_ignores=[]), 'export', 'exec'), env)

def cubo(offset=(0,0,0)):
    v = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],
                  [0,0,1],[1,0,1],[1,1,1],[0,1,1]], dtype=float) + offset
    f = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                  [1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    return v, f

class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='exo_export_')
        self.path = Path(self.tmp.name) / 'modelo.obj'
        cubos = [cubo((i*2,0,0)) for i in range(4)]
        self.v = np.concatenate([v for v,f in cubos])
        self.f = np.concatenate([f+i*8 for i,(v,f) in enumerate(cubos)])
        self.c = np.repeat([[.02,.02,.02],[.42,.45,.48],[.85,.50,.22],[.08,.55,.35]], 8, axis=0)

    def tearDown(self):
        self.tmp.cleanup()

    def run_export(self, n, paleta=''):
        before = self.c.copy()
        env['_escribir_obj'](str(self.path), self.v, self.f, self.c, n, paleta)
        np.testing.assert_array_equal(self.c, before)
        rows = self.path.read_text().splitlines()
        vr = [r.split() for r in rows if r.startswith('v ')]
        self.assertTrue(all(len(r)==4 for r in vr))
        v = np.array([[float(x) for x in r[1:]] for r in vr])
        f = np.array([[int(x)-1 for x in r.split()[1:]] for r in rows if r.startswith('f ')])
        self.assertEqual(len(f), len(self.f))
        edges = np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
        _, count = np.unique(edges, axis=0, return_counts=True)
        self.assertTrue(np.all(count==2), 'El OBJ debe permanecer cerrado en sus fronteras de color')
        triangles = lambda vv,ff: sorted(tuple(np.round(vv[c].ravel(),6)) for c in ff)
        self.assertEqual(triangles(v,f), triangles(self.v,self.f))
        lines = self.path.with_suffix('.mtl').read_text().splitlines()
        materials = {r.split()[1] for r in lines if r.startswith('newmtl ')}
        used = {r.split()[1] for r in rows if r.startswith('usemtl ')}
        self.assertTrue(used.issubset(materials))
        self.assertLessEqual(len(materials), n)
        self.assertTrue(all(r=='Ka 0.0000 0.0000 0.0000' for r in lines if r.startswith('Ka ')))
        return lines

    def test_four(self):
        lines = self.run_export(4)
        rgb = np.array([[float(x) for x in r.split()[1:]] for r in lines if r.startswith('Kd ')])
        self.assertEqual(len(rgb),4)
        self.assertTrue(np.any(rgb.max(axis=1)<.05))
        self.assertTrue(np.any((rgb.mean(axis=1)>.40)&(rgb.mean(axis=1)<.50)))

    def test_one(self): self.run_export(1)
    def test_sixteen(self): self.run_export(16)
    def test_user_palette(self):
        lines = self.run_export(2,'#ff0000,#0000ff')
        self.assertEqual([r for r in lines if r.startswith('Kd ')],
                         ['Kd 1.0000 0.0000 0.0000','Kd 0.0000 0.0000 1.0000'])

    def test_reject_too_many(self):
        with self.assertRaises(ValueError): self.run_export(1,'#ff0000,#0000ff')

    def test_shared_color_boundary(self):
        self.v,self.f = cubo()
        self.c = np.array([[1,0,0]]*4+[[0,0,1]]*4)
        self.run_export(2,'#ff0000,#0000ff')

    def test_touching_edge(self):
        v0,f0 = cubo(); v1,f1 = cubo((1,1,0))
        self.v = np.concatenate([v0,v1]); self.f=np.concatenate([f0,f1+8])
        self.c = np.array([[1,0,0]]*8+[[0,0,1]]*8)
        self.run_export(2,'#ff0000,#0000ff')

    def test_reject_open_mesh(self):
        self.f = self.f[:-1]
        with self.assertRaisesRegex(ValueError,'Reparar la malla'):
            self.run_export(4)

if __name__ == '__main__': unittest.main(verbosity=2)
