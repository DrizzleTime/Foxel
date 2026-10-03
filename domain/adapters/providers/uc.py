import asyncio
import posixpath
import tempfile

from models import StorageAdapter

from .quark import QuarkAdapter


class UCAdapter(QuarkAdapter):
    api_base = "https://pc-api.uc.cn/1/clouddrive"
    referer = "https://drive.uc.cn"
    pr = "UCBrowser"
    product_name = "UC"
    client_name = "uc-cloud-drive"

    def __init__(self, record: StorageAdapter):
        super().__init__(record)
        self.use_transcoding_address = False

    @staticmethod
    def _path(value):
        parts = str(value or "").replace("\\", "/").split("/")
        if any(part in (".", "..") for part in parts):
            raise ValueError("Relative path components are not allowed")
        return "/".join(part for part in parts if part)

    def get_effective_root(self, sub_path):
        return "/".join(filter(None, (str(self.root_fid), self._path(sub_path))))

    async def _resolve_dir_fid_from(self, base_fid, rel):
        fid, _, sub_path = str(base_fid).partition("/")
        path = "/".join(filter(None, (self._path(sub_path), self._path(rel))))
        return await super()._resolve_dir_fid_from(fid, path)

    async def write_file_stream(self, root, rel, data_iter):
        rel = self._path(rel)
        with tempfile.TemporaryFile() as file:
            size = 0
            async for chunk in data_iter:
                if chunk:
                    await asyncio.to_thread(file.write, chunk)
                    size += len(chunk)
            file.seek(0)
            await self.write_upload_file(root, rel, file, posixpath.basename(rel), size)
            return size

    async def delete(self, root, rel):
        rel = self._path(rel)
        if not rel:
            raise ValueError("Cannot delete mount root")
        await super().delete(root, rel)
        self._dir_fid_cache.clear()

    async def move(self, root, src_rel, dst_rel):
        src, dst = self._path(src_rel), self._path(dst_rel)
        if not src or not dst or dst.startswith(src + "/"):
            raise ValueError("Invalid move destination")
        if src == dst:
            return
        if await self.exists(root, dst):
            raise FileExistsError(dst)
        await super().move(root, src, dst)
        self._dir_fid_cache.clear()

    async def rename(self, root, src_rel, dst_rel):
        return await self.move(root, src_rel, dst_rel)

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src, dst = self._path(src_rel), self._path(dst_rel)
        if not src or not dst or src == dst or dst.startswith(src + "/"):
            raise ValueError("Invalid copy destination")
        item = await self.stat_file(root, src)
        if await self.exists(root, dst):
            if not overwrite:
                raise FileExistsError(dst)
            await self.delete(root, dst)
        if item["is_dir"]:
            await self.mkdir(root, dst)
            page = 1
            while True:
                children, total = await self.list_dir(root, src, page, 100)
                for child in children:
                    await self.copy(root, src + "/" + child["name"], dst + "/" + child["name"])
                if page * 100 >= total:
                    break
                page += 1
        else:
            response = await self.stream_file(root, src, None)
            try:
                await self.write_file_stream(root, dst, response.body_iterator)
            finally:
                await response.body_iterator.aclose()
                if response.background:
                    await response.background()


ADAPTER_TYPE = "uc"
ADAPTER_FACTORY = UCAdapter
CONFIG_SCHEMA = [
    {"key": "cookie", "label": "Cookie", "type": "password", "required": True},
    {"key": "root_fid", "label": "Root FID", "type": "string", "default": "0"},
    {"key": "only_list_video_file", "label": "Videos only", "type": "boolean", "default": False},
]
