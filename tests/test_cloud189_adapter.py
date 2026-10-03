from types import SimpleNamespace
import io
import base64
import hashlib
import hmac
from urllib.parse import parse_qs
from unittest.mock import AsyncMock
import unittest

import httpx
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization, padding
from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from domain.adapters.providers.cloud189 import Cloud189Adapter


class Cloud189AdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, handler):
        adapter = Cloud189Adapter(SimpleNamespace(config={"cookie": "SESSION=one"}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        return adapter

    async def test_list_resolves_folders_and_files(self):
        def handler(request):
            self.assertEqual(request.headers["Cookie"], "SESSION=one")
            if request.url.path.endswith("listFiles.action"):
                return httpx.Response(200, json={"res_code": 0, "fileListAO": {
                    "count": 2, "folderList": [{"id": 1, "name": "docs"}],
                    "fileList": [{"id": 2, "name": "a.txt", "size": 3}]}})
            return httpx.Response(200, json={"res_code": 0, "fileDownloadUrl": "//download.test/a"})
        adapter = self.make_adapter(handler)
        items, total = await adapter.list_dir("-11", "")
        self.assertEqual((total, items[0]["name"], items[1]["name"]), (2, "docs", "a.txt"))
        url, headers = await adapter._download("-11", "a.txt")
        self.assertEqual(url, "https://download.test/a")
        self.assertNotIn("Cookie", headers)

    async def test_password_configuration_is_lazy(self):
        adapter = Cloud189Adapter(SimpleNamespace(config={"username": "a", "password": "b"}))
        self.assertFalse(adapter._authenticated)

    async def test_upload_failure_never_commits(self):
        adapter = self.make_adapter(lambda request: httpx.Response(500))
        adapter._parent = AsyncMock(return_value=({"id": "-11"}, "a.txt"))
        adapter._api = AsyncMock(side_effect=[{"sessionKey": "key"}, {"pubKey": "key", "pkId": 1}])
        adapter._upload_api = AsyncMock(side_effect=[{"data": {"uploadFileId": "up", "fileDataExists": 0}},
            {"uploadUrls": {"partNumber_1": {"requestURL": "https://put.test/", "requestHeader": "Content-MD5=a%2Bb%3D"}}}])
        with self.assertRaises(httpx.HTTPStatusError):
            await adapter.write_upload_file("-11", "a.txt", io.BytesIO(b"abc"))
        self.assertEqual(adapter._upload_api.await_count, 2)

    async def test_batch_failure_is_reported(self):
        adapter = self.make_adapter(lambda request: httpx.Response(200))
        adapter._api = AsyncMock(side_effect=[{"taskId": "task"}, {"taskStatus": 4, "failedCount": 1}])
        with self.assertRaises(HTTPException):
            await adapter._task("MOVE", {"id": "1", "name": "a", "is_dir": False}, "2")

    async def test_expired_cookie_has_bounded_attempts(self):
        count = 0
        def handler(request):
            nonlocal count
            count += 1
            return httpx.Response(200, json={"errorCode": "InvalidSessionKey"})
        adapter = self.make_adapter(handler)
        with self.assertRaises(HTTPException) as caught:
            await adapter._api("GET", "/test")
        self.assertEqual((caught.exception.status_code, count), (401, 1))

    async def test_signed_upload_can_be_decrypted_and_verified(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = base64.b64encode(private.public_key().public_bytes(serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        def handler(request):
            secret = private.decrypt(base64.b64decode(request.headers["EncryptionText"]), rsa_padding.PKCS1v15())
            encrypted = request.url.params["params"]
            decrypt = Cipher(algorithms.AES(secret[:16]), modes.ECB()).decryptor()
            padded = decrypt.update(bytes.fromhex(encrypted)) + decrypt.finalize()
            unpad = padding.PKCS7(128).unpadder()
            plain = (unpad.update(padded) + unpad.finalize()).decode()
            self.assertEqual(plain, "fileName=a%2Bb.txt&fileSize=3")
            signed = f"SessionKey=session&Operate=GET&RequestURI={request.url.path}&Date={request.headers['X-Request-Date']}&params={encrypted}"
            self.assertEqual(request.headers["Signature"], hmac.new(secret, signed.encode(), hashlib.sha1).hexdigest())
            return httpx.Response(200, json={"code": "SUCCESS"})
        adapter = self.make_adapter(handler)
        await adapter._upload_api("initMultiUpload", {"fileName": "a%2Bb.txt", "fileSize": 3}, "session", {"pubKey": public, "pkId": "1"})

    async def test_password_login_encrypts_credentials_and_follows_session_url(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = base64.b64encode(private.public_key().public_bytes(serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        def handler(request):
            path = request.url.path
            if path.endswith("loginUrl.action"):
                return httpx.Response(302, headers={"Location": "https://open.e.189.cn/login?appId=cloud&lt=lt&reqId=req"})
            if path == "/login":
                return httpx.Response(200)
            if path.endswith("appConf.do"):
                return httpx.Response(200, json={"result": "0", "data": {"clientType": 1}})
            if path.endswith("encryptConf.do"):
                return httpx.Response(200, json={"result": 0, "data": {"pubKey": public, "pre": "{RSA}"}})
            if path.endswith("loginSubmit.do"):
                body = parse_qs(request.content.decode())
                for key, expected in (("userName", "user"), ("epd", "password")):
                    cipher = bytes.fromhex(body[key][0].removeprefix("{RSA}"))
                    self.assertEqual(private.decrypt(cipher, rsa_padding.PKCS1v15()).decode(), expected)
                return httpx.Response(200, json={"result": 0, "toUrl": "https://cloud.189.cn/session"})
            if path == "/session":
                return httpx.Response(200, headers={"Set-Cookie": "SESSION=authenticated; Path=/"})
            self.assertIn("SESSION=authenticated", request.headers["Cookie"])
            return httpx.Response(200, json={"res_code": 0})
        adapter = Cloud189Adapter(SimpleNamespace(config={"username": "user", "password": "password"}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        await adapter._api("GET", "/test")
