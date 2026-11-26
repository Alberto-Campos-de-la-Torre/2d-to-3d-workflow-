import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('exo_instalar',ROOT/'instalar.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class Instalador(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.comfy=Path(self.tmp.name);(self.comfy/'main.py').write_text('# mock ComfyUI\n')
    def test_perfiles_independientes(self):
        for perfil in ['2d','3d','ambos']:
            with self.subTest(perfil=perfil):
                mods,files=mod.preparar(perfil)
                self.assertEqual(Path('nodes_2d.py') in files,perfil in ('2d','ambos'))
                self.assertEqual(Path('nodes.py') in files,perfil in ('3d','ambos'))
                self.assertIn(Path('resultados.py'),files)
    def test_no_sobrescribe_sin_bandera(self):
        target=mod.instalar(self.comfy,'2d');before=(target/'perfil.py').read_bytes()
        with self.assertRaises(ValueError):mod.instalar(self.comfy,'3d')
        self.assertEqual((target/'perfil.py').read_bytes(),before)
    def test_agregar_segundo_modulo_con_respaldo(self):
        target=mod.instalar(self.comfy,'2d');before=(target/'perfil.py').read_bytes()
        mod.instalar(self.comfy,'ambos',actualizar=True)
        backups=list((self.comfy/'user/default/exo_backups').iterdir())
        self.assertEqual(len(backups),1)
        self.assertEqual((backups[0]/'perfil.py').read_bytes(),before)
        self.assertEqual(json.loads((target/'perfil.json').read_text())['modulos'],['2d','3d'])
    def test_retirar_modulo_requiere_instalacion_nueva(self):
        target=mod.instalar(self.comfy,'ambos');before=(target/'perfil.py').read_bytes()
        with self.assertRaises(ValueError):mod.instalar(self.comfy,'2d',actualizar=True)
        self.assertEqual((target/'perfil.py').read_bytes(),before)
    def test_no_instala_modelos_ni_datos(self):
        target=mod.instalar(self.comfy,'ambos')
        prohibidos={'.gguf','.safetensors','.ckpt','.stl','.obj','.glb','.png','.jpg','.pyc'}
        self.assertFalse(any(p.suffix.lower() in prohibidos for p in target.rglob('*') if p.is_file()))
        self.assertFalse((self.comfy/'config_local.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
