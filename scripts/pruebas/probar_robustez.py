"""Regresion: presupuestos invalidos, archivo completo y limpieza por conjuntos."""
import ast
import asyncio
import importlib.util
import math
import os
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments"
if not PKG.exists():
    PKG = ROOT / "custom_nodes/exo_filaments"
sys.path.insert(0, str(PKG))
import archivos
import presupuesto
spec = importlib.util.spec_from_file_location("limpieza", ROOT / "scripts/limpiar.py")
limpieza = importlib.util.module_from_spec(spec)
spec.loader.exec_module(limpieza)
package = types.ModuleType("exo_test")
package.__path__ = [str(PKG)]
sys.modules["exo_test"] = package

class Robustez(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="exo_regresion_")
        self.root = Path(self.temp.name)
        self.out = self.root / "output"
        self.out.mkdir()
    def tearDown(self):
        self.temp.cleanup()
    def fixture(self):
        folder = self.out / "model"
        folder.mkdir()
        (folder / "modelo.obj").write_text("mtllib material.mtl\nv 0 0 0\n")
        (folder / "material.mtl").write_text("newmtl color\nmap_Kd textura.png\n")
        (folder / "textura.png").write_bytes(b"texture")
        return folder
    def test_presupuesto_normal(self):
        p = presupuesto.calcular(100, dict(presupuesto.POR_DEFECTO))
        self.assertEqual(p["precio"], 24.32)
        self.assertEqual(p["peso_g"], 100)
    def test_soportes(self):
        self.assertEqual(presupuesto.calcular(100, dict(presupuesto.POR_DEFECTO), 20)["peso_g"], 120)
    def test_invalidos(self):
        for x in [-1, float("nan"), float("inf"), "abc", None]:
            with self.subTest(peso=x), self.assertRaises(ValueError):
                presupuesto.calcular(x, dict(presupuesto.POR_DEFECTO))
        for key in ["gramos_por_hora", "margen", "precio_filamento_kg", "preparacion", "coste_hora_maquina", "fallos_pct"]:
            for x in [-1, float("nan"), float("inf")]:
                with self.subTest(key=key, value=x), self.assertRaises(ValueError):
                    presupuesto.calcular(100, {**presupuesto.POR_DEFECTO, key: x})
        for key in ["gramos_por_hora", "margen"]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                presupuesto.calcular(100, {**presupuesto.POR_DEFECTO, key: 0})
        with self.assertRaises(ValueError):
            presupuesto.calcular(100, dict(presupuesto.POR_DEFECTO), -10)
        with self.assertRaises(ValueError):
            presupuesto.calcular(1e308, dict(presupuesto.POR_DEFECTO), 1e308)
    def test_dependencias_completas(self):
        folder = self.fixture()
        self.assertEqual({p.name for p in archivos.reunir([folder/"modelo.obj"], self.out)}, {"modelo.obj", "material.mtl", "textura.png"})
    def test_dependencia_ausente(self):
        folder = self.fixture()
        (folder / "textura.png").unlink()
        with self.assertRaises(ValueError):
            archivos.reunir([folder/"modelo.obj"], self.out)
    def test_escape(self):
        folder = self.fixture()
        (self.root / "externo.mtl").write_text("newmtl x")
        (folder / "modelo.obj").write_text("mtllib ../../externo.mtl")
        with self.assertRaises(ValueError):
            archivos.reunir([folder/"modelo.obj"], self.out)
    def test_archivo_y_colisiones(self):
        folder = self.fixture()
        inp = self.root / "input"
        inp.mkdir()
        (inp/"source.png").write_bytes(b"source")
        tree = ast.parse((PKG/"pieza.py").read_text(encoding="utf-8-sig"))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "guardar_encargo")
        fn.decorator_list = []
        web = Mock()
        web.json_response.side_effect = lambda data, status=200: (status, data)
        fp = Mock()
        fp.get_input_directory.return_value = str(inp)
        env = {"__package__": "exo_test", "RAIZ": self.root, "Path": Path, "uuid": uuid, "web": web,
               "folder_paths": fp, "_salida": lambda: self.out,
               "_trabajos": {"t": {"terminado": True, "archivos": [{"ruta": "model/modelo.obj"}], "imagen": "source.png"}}}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "archive", "exec"), env)
        class Request:
            async def json(self): return {"id": "t", "nombre": "Cliente"}
        results = [asyncio.run(env["guardar_encargo"](Request())) for _ in range(2)]
        self.assertNotEqual(results[0][1]["carpeta"], results[1][1]["carpeta"])
        for status, data in results:
            self.assertEqual(status, 200)
            saved = Path(data["carpeta"])/"archivos/model/modelo.obj"
            self.assertEqual(len(archivos.reunir([saved], Path(data["carpeta"])/"archivos")), 3)
    def test_limpieza_conjunto_y_compartidos(self):
        folder = self.fixture()
        (folder/"segundo.obj").write_text("mtllib material.mtl")
        for f in folder.iterdir(): os.utime(f, (1, 1))
        os.utime(folder/"modelo.obj", None)
        borrar, conservar, size = limpieza.revisar("test", self.out, 7, 0)
        self.assertEqual(borrar, [])
        self.assertEqual(conservar, 4)
        for f in folder.iterdir(): os.utime(f, (1, 1))
        borrar, conservar, size = limpieza.revisar("test", self.out, 7, 0)
        self.assertEqual(len(borrar), 4)
        self.assertEqual(limpieza.revisar("test", self.out, 7, 1)[0], [])
    def test_protegidos_y_incompletos(self):
        protected = self.out/"encargos"
        protected.mkdir()
        (protected/"keep.obj").write_text("v 0 0 0")
        f = self.out/"broken.obj"
        f.write_text("mtllib missing.mtl")
        os.utime(f, (1, 1))
        self.assertEqual(limpieza.revisar("test", self.out, 7, 0)[0], [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
