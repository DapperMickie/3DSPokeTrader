import http.client
from pathlib import Path
import tempfile
import threading
import unittest

from poketrader.backend import DemoBackend
from poketrader.server import Server
from poketrader.service import Service
from .fixtures import save,pokemon


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=Service(Path(self.temp.name),DemoBackend(pokemon(133)))
        self.server=Server(("127.0.0.1",0),self.service,"b"*32)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        for thread in self.service.threads: thread.join(5)
        self.temp.cleanup()
    def request(self,method,path,data=None,auth=True):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        headers={"Authorization":"Bearer "+"b"*32} if auth else {}
        connection.request(method,path,data,headers)
        response=connection.getresponse(); result=(response.status,response.read())
        connection.close(); return result

    def test_upload_box_trade_download_flow(self):
        code,body=self.request("POST","/v1/saves",save())
        self.assertEqual(code,200)
        save_id=body.decode().splitlines()[0]
        code,body=self.request("GET",f"/v1/saves/{save_id}/boxes/0")
        self.assertEqual(code,200); self.assertIn(b"PIKACHU",body)
        trade_id="c"*32; base="/v1/trades/"+trade_id
        code,body=self.request("PUT",base,f"{save_id}\n0\n".encode())
        self.assertEqual(code,200); self.assertIn(b"DEMO - NO SWITCH TRADE",body)
        self.assertEqual(self.request("POST",base+"/start")[0],200)
        for thread in self.service.threads: thread.join(5)
        code,body=self.request("POST",base+"/confirm")
        self.assertEqual(code,200); self.assertTrue(body.startswith(b"ready\n"))
        code,body=self.request("GET",base+"/result")
        self.assertEqual(code,200); self.assertEqual(len(body),131072)
        self.assertEqual(self.request("POST",base+"/applied")[0],200)

    def test_unauthorized_and_oversize_uploads(self):
        self.assertEqual(self.request("GET","/v1/health",auth=False)[0],401)
        self.assertEqual(self.request("POST","/v1/saves",bytes(131073))[0],413)

    def test_invalid_upload_and_path(self):
        self.assertEqual(self.request("POST","/v1/saves",b"not a save")[0],400)
        self.assertEqual(self.request("GET","/v1/trades/../../secrets")[0],404)


if __name__ == "__main__": unittest.main()
