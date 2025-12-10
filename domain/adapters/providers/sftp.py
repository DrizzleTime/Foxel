import asyncio
import mimetypes
import stat as statmod
from typing import List, Dict, Tuple, AsyncIterator, Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import paramiko

from models import StorageAdapter


def _join_remote(root: str, rel: str) -> str:
    root = (root or "/").rstrip("/") or "/"
    rel = (rel or "").lstrip("/")
    if not rel:
        return root
    return f"{root}/{rel}"


class SFTPAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.host: str = cfg.get("host")
        self.port: int = int(cfg.get("port", 22))
        self.username: str | None = cfg.get("username")
        self.password: str | None = cfg.get("password")
        self.timeout: int = int(cfg.get("timeout", 15))
        self.root_path: str = cfg.get("root")  # 必填
        self.allow_unknown_host: bool = bool(cfg.get("allow_unknown_host", True))

        if not self.host:
            raise ValueError("SFTP adapter requires 'host'")
        if not self.username or not self.password:
            raise ValueError("SFTP adapter requires 'username' and 'password'")
        if not self.root_path:
            raise ValueError("SFTP adapter requires 'root'")

    def get_effective_root(self, sub_path: str | None) -> str:
        base = self.root_path.rstrip("/") or "/"
        if sub_path:
            return _join_remote(base, sub_path)
        return base

    def _connect(self) -> paramiko.SFTPClient:
        ssh = paramiko.SSHClient()
        if self.allow_unknown_host:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        return ssh.open_sftp()

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        path = _join_remote(root, rel)

        def _do_list() -> List[Dict]:
            sftp = self._connect()
            try:
                attrs = sftp.listdir_attr(path)
                entries: List[Dict] = []
                for a in attrs:
                    name = a.filename
                    is_dir = statmod.S_ISDIR(a.st_mode)
                    entries.append({
                        "name": name,
                        "is_dir": is_dir,
                        "size": 0 if is_dir else int(a.st_size or 0),
                        "mtime": int(a.st_mtime or 0),
                        "type": "dir" if is_dir else "file",
                    })
                return entries
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        entries = await asyncio.to_thread(_do_list)

        reverse = sort_order.lower() == "desc"

        def get_sort_key(item):
            key = (not item["is_dir"],)
            f = sort_by.lower()
            if f == "name":
                key += (item["name"].lower(),)
            elif f == "size":
                key += (item.get("size", 0),)
            elif f == "mtime":
                key += (item.get("mtime", 0),)
            else:
                key += (item["name"].lower(),)
            return key

        entries.sort(key=get_sort_key, reverse=reverse)
        total = len(entries)
        start = (page_num - 1) * page_size
        end = start + page_size
        return entries[start:end], total

    async def read_file(self, root: str, rel: str) -> bytes:
        path = _join_remote(root, rel)

        def _do_read() -> bytes:
            sftp = self._connect()
            try:
                with sftp.open(path, "rb") as f:
                    return f.read()
            except FileNotFoundError:
                raise
            except IOError as e:
                if getattr(e, "errno", None) == 2:
                    raise FileNotFoundError(rel)
                raise
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        return await asyncio.to_thread(_do_read)

    async def write_file(self, root: str, rel: str, data: bytes):
        path = _join_remote(root, rel)

        def _ensure_dirs(sftp: paramiko.SFTPClient, dir_path: str):
            parts = [p for p in dir_path.strip("/").split("/") if p]
            cur = "/"
            for p in parts:
                cur = _join_remote(cur, p)
                try:
                    sftp.mkdir(cur)
                except IOError:
                    # likely exists
                    pass

        def _do_write():
            sftp = self._connect()
            try:
                parent = "/" if "/" not in path.strip("/") else path.rsplit("/", 1)[0]
                _ensure_dirs(sftp, parent)
                with sftp.open(path, "wb") as f:
                    f.write(data)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        await asyncio.to_thread(_do_write)

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        buf = bytearray()
        async for chunk in data_iter:
            if chunk:
                buf.extend(chunk)
        await self.write_file(root, rel, bytes(buf))
        return len(buf)

    async def mkdir(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_mkdir():
            sftp = self._connect()
            try:
                parts = [p for p in path.strip("/").split("/") if p]
                cur = "/"
                for p in parts:
                    cur = _join_remote(cur, p)
                    try:
                        sftp.mkdir(cur)
                    except IOError:
                        pass
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        await asyncio.to_thread(_do_mkdir)

    async def delete(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_delete():
            sftp = self._connect()
            try:
                # Try file remove first
                try:
                    sftp.remove(path)
                    return
                except IOError:
                    pass

                def _rm_tree(dp: str):
                    try:
                        for a in sftp.listdir_attr(dp):
                            child = _join_remote(dp, a.filename)
                            if statmod.S_ISDIR(a.st_mode):
                                _rm_tree(child)
                            else:
                                try:
                                    sftp.remove(child)
                                except Exception:
                                    pass
                        sftp.rmdir(dp)
                    except IOError:
                        pass

                _rm_tree(path)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        await asyncio.to_thread(_do_delete)

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src = _join_remote(root, src_rel)
        dst = _join_remote(root, dst_rel)

        def _do_move():
            sftp = self._connect()
            try:
                # ensure dst parent exists
                parent = "/" if "/" not in dst.strip("/") else dst.rsplit("/", 1)[0]
                parts = [p for p in parent.strip("/").split("/") if p]
                cur = "/"
                for p in parts:
                    cur = _join_remote(cur, p)
                    try:
                        sftp.mkdir(cur)
                    except IOError:
                        pass
                sftp.rename(src, dst)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        await asyncio.to_thread(_do_move)

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src = _join_remote(root, src_rel)
        dst = _join_remote(root, dst_rel)

        def _is_dir() -> bool:
            sftp = self._connect()
            try:
                st = sftp.stat(src)
                return statmod.S_ISDIR(st.st_mode)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        if await asyncio.to_thread(_is_dir):
            await self.mkdir(root, dst_rel)

            children, _ = await self.list_dir(root, src_rel, page_num=1, page_size=10_000)
            for ent in children:
                child_src = f"{src_rel.rstrip('/')}/{ent['name']}"
                child_dst = f"{dst_rel.rstrip('/')}/{ent['name']}"
                await self.copy(root, child_src, child_dst, overwrite)
            return

        # file copy
        data = await self.read_file(root, src_rel)
        if not overwrite:
            try:
                await self.stat_file(root, dst_rel)
                raise FileExistsError(dst_rel)
            except FileNotFoundError:
                pass
        await self.write_file(root, dst_rel, data)

    async def stat_file(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_stat():
            sftp = self._connect()
            try:
                st = sftp.stat(path)
                is_dir = statmod.S_ISDIR(st.st_mode)
                info = {
                    "name": rel.split("/")[-1],
                    "is_dir": is_dir,
                    "size": 0 if is_dir else int(st.st_size or 0),
                    "mtime": int(st.st_mtime or 0),
                    "type": "dir" if is_dir else "file",
                    "path": path,
                }
                return info
            except FileNotFoundError:
                raise
            except IOError as e:
                if getattr(e, "errno", None) == 2:
                    raise FileNotFoundError(rel)
                raise
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        return await asyncio.to_thread(_do_stat)

    async def exists(self, root: str, rel: str) -> bool:
        try:
            await self.stat_file(root, rel)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        path = _join_remote(root, rel)

        def _get_stat():
            sftp = self._connect()
            try:
                st = sftp.stat(path)
                return int(st.st_size or 0)
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        file_size = await asyncio.to_thread(_get_stat)
        if file_size is None:
            raise HTTPException(404, detail="File not found")

        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"

        start = 0
        end = file_size - 1
        status = 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
            "Content-Length": str(file_size),
        }

        if range_header and range_header.startswith("bytes="):
            try:
                s, e = (range_header.removeprefix("bytes=").split("-", 1))
                if s.strip():
                    start = int(s)
                if e.strip():
                    end = int(e)
                if start >= file_size:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")
                if end >= file_size:
                    end = file_size - 1
                status = 206
                headers["Content-Length"] = str(end - start + 1)
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            except ValueError:
                raise HTTPException(400, detail="Invalid Range header")

        queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=8)

        def _worker():
            sftp = self._connect()
            try:
                with sftp.open(path, "rb") as f:
                    f.seek(start)
                    remaining = end - start + 1
                    chunk_size = 64 * 1024
                    while remaining > 0:
                        to_read = chunk_size if remaining > chunk_size else remaining
                        data = f.read(to_read)
                        if not data:
                            break
                        try:
                            queue.put_nowait(data)
                        except Exception:
                            break
                        remaining -= len(data)
                try:
                    queue.put_nowait(None)
                except Exception:
                    pass
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass

        async def agen():
            worker_fut = asyncio.to_thread(_worker)
            try:
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break
                    yield chunk
            finally:
                try:
                    await worker_fut
                except Exception:
                    pass

        return StreamingResponse(agen(), status_code=status, headers=headers, media_type=content_type)


ADAPTER_TYPE = "sftp"

CONFIG_SCHEMA = [
    {"key": "host", "label": "主机", "type": "string", "required": True, "placeholder": "sftp.example.com"},
    {"key": "port", "label": "端口", "type": "number", "required": False, "default": 22},
    {"key": "username", "label": "用户名", "type": "string", "required": True},
    {"key": "password", "label": "密码", "type": "password", "required": True},
    {"key": "root", "label": "根路径", "type": "string", "required": True, "placeholder": "/data"},
    {"key": "timeout", "label": "超时(秒)", "type": "number", "required": False, "default": 15},
    {"key": "allow_unknown_host", "label": "允许未知主机指纹", "type": "boolean", "required": False, "default": True},
]


def ADAPTER_FACTORY(rec: StorageAdapter):
    return SFTPAdapter(rec)
