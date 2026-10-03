import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from domain.adapters.providers.smb import SMBAdapter


class SMBAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        return SMBAdapter(SimpleNamespace(config={"server": "nas", "share": "data", "username": "u", "password": "p"}))

    def test_no_network_in_constructor_and_sessions_are_isolated(self):
        first, second = self.make(), self.make()
        self.assertIsNot(first._options["connection_cache"], second._options["connection_cache"])
        self.assertEqual(first._path("docs", "a.txt"), r"\\nas\data\docs\a.txt")
        with self.assertRaises(ValueError):
            first._path("docs", "../secret")

    async def test_download_ranges_and_handle_cleanup(self):
        data = b"0123456789"
        for header, expected in [(None, data), ("bytes=2-4", b"234"), ("bytes=-3", b"789"), ("bytes=8-99", b"89")]:
            with self.subTest(header=header):
                file = io.BytesIO(data)
                adapter = self.make()
                with patch("domain.adapters.providers.smb.smbclient.stat", return_value=SimpleNamespace(
                    st_mode=0, st_size=10, st_mtime=0)), patch("domain.adapters.providers.smb.smbclient.open_file", return_value=file):
                    response = await adapter.stream_file("", "file", header)
                    self.assertEqual(b"".join([chunk async for chunk in response.body_iterator]), expected)
                    self.assertEqual(int(response.headers["content-length"]), len(expected))
                    self.assertTrue(file.closed)

    async def test_invalid_ranges_never_open_a_file(self):
        adapter = self.make()
        for header in ["bytes=9-", "bytes=-0", "bytes=2-1", "other=1-2", "bytes=1-2,3-4"]:
            with patch("domain.adapters.providers.smb.smbclient.stat", return_value=SimpleNamespace(
                st_mode=0, st_size=4, st_mtime=0)), patch("domain.adapters.providers.smb.smbclient.open_file") as opened:
                with self.assertRaises(HTTPException) as caught:
                    await adapter.stream_file("", "file", header)
                self.assertEqual(caught.exception.status_code, 416)
                opened.assert_not_called()

    async def test_stream_upload_is_incremental(self):
        written = []
        class File:
            closed = False
            def write(self, chunk): written.append(chunk); return len(chunk)
            def close(self): self.closed = True
        file = File()
        async def chunks():
            yield b"first"
            self.assertEqual(written, [b"first"])
            yield b"second"
        with patch("domain.adapters.providers.smb.smbclient.makedirs"), patch(
            "domain.adapters.providers.smb.smbclient.open_file", return_value=file):
            size = await self.make().write_file_stream("", "file", chunks())
        self.assertEqual(size, 11)
        self.assertTrue(file.closed)

    async def test_copy_uses_sdk_and_rejects_self_overwrite(self):
        adapter = self.make()
        with self.assertRaises(ValueError):
            await adapter.copy("", "file", "file", overwrite=True)
        with patch.object(adapter, "exists", return_value=False), patch.object(adapter, "stat_file", return_value={"is_dir": False}), patch(
            "domain.adapters.providers.smb.smbclient.makedirs"), patch("domain.adapters.providers.smb.smb_shutil.copyfile") as copy:
            await adapter.copy("", "src", "dst")
        self.assertEqual(copy.call_args.args, (r"\\nas\data\src", r"\\nas\data\dst"))
