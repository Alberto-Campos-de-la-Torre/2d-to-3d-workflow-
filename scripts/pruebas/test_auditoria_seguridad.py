import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('exo_auditor',ROOT/'scripts/auditar_seguridad.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class Auditor(unittest.TestCase):
    def scan(self,text):return audit.scan('fixture.py',text.encode())
    def test_clave_proveedor(self):self.assertTrue(any(f['regla']=='clave_proveedor' for f in self.scan('sk-'+'a'*40)))
    def test_correo_cualquier_dominio(self):self.assertTrue(any(f['regla']=='correo_no_ejemplo' for f in self.scan('persona'+'@'+'privado.test')))
    def test_ejemplo_no_es_cuenta_real(self):self.assertFalse(any(f['regla']=='correo_no_ejemplo' for f in self.scan('persona'+'@'+'example.invalid')))
    def test_ruta_personal(self):self.assertTrue(any(f['regla']=='ruta_usuario_unix' for f in self.scan('/home/'+'persona'+'/datos')))
    def test_host_tailnet(self):self.assertTrue(any(f['regla']=='host_privado' for f in self.scan('https://'+'equipo.red'+'.ts.net/')))
    def test_url_con_token(self):self.assertTrue(any(f['regla']=='secreto_en_query' for f in self.scan('https://service.invalid/?token='+'a'*24)))
    def test_credito_publico_distinto_de_secreto(self):
        value='agente'+'@'+'users.noreply.github.com'
        self.assertTrue(any(f['nivel']=='error' for f in self.scan(value)))
        result=audit.scan('metadata_git',value.encode(),attribution=True)
        self.assertTrue(result);self.assertTrue(all(f['nivel']=='info' for f in result))

if __name__=='__main__':unittest.main(verbosity=2)
