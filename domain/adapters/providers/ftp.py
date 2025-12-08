from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Dict, Tuple, AsyncIterator, Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from ftplib import FTP, error_perm
import mimetypes

from models import StorageAdapter


def _join_remote(root: str, rel: str) -> str:
    root = (root or "/").rstrip("/") or "/"
    rel = (rel or "").lstrip("/")
    if not rel:
        return root
    return f"{root}/{rel}"


def _parse_mlst_line(line: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        facts, _, name = line.partition(" ")
        for part in facts.split(";"):
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
        if name:
            out["name"] = name.strip()
    except Exception:
        pass
    return out


def _parse_modify_to_epoch(mod: str) -> int:
    # Formats we may see: YYYYMMDDHHMMSS or YYYYMMDDHHMMSS(.sss)
    try:
        mod = mod.strip()
        mod = mod.split(".")[0]
        if len(mod) >= 14:
            y = int(mod[0:4])
            m = int(mod[4:6])
            d = int(mod[6:8])
            hh = int(mod[8:10])
            mm = int(mod[10:12])
            ss = int(mod[12:14])
            import datetime as _dt
            return int(_dt.datetime(y, m, d, hh, mm, ss, tzinfo=_dt.timezone.utc).timestamp())
    except Exception:
        return 0
    return 0


@dataclass
class _Range:
    start: int
    end: Optional[int]  # inclusive


class FTPAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.host: str = cfg.get("host")
        self.port: int = int(cfg.get("port", 21))
        self.username: Optional[str] = cfg.get("username")
        self.password: Optional[str] = cfg.get("password")
        self.passive: bool = bool(cfg.get("passive", True))
        self.timeout: int = int(cfg.get("timeout", 15))
        self.root_path: str = cfg.get("root", "/") or "/"

        if not self.host:
            raise ValueError("FTP adapter requires 'host'")

    def get_effective_root(self, sub_path: str | None) -> str:
        base = self.root_path.rstrip("/") or "/"
        if sub_path:
            return _join_remote(base, sub_path)
        return base

    def _connect(self) -> FTP:
        ftp = FTP()
        ftp.connect(self.host, self.port, timeout=self.timeout)
        if self.username:
            ftp.login(self.username, self.password or "")
        else:
            ftp.login()
        ftp.set_pasv(self.passive)
        return ftp

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        path = _join_remote(root, rel.strip('/'))

        def _do_list() -> List[Dict]:
            ftp = self._connect()
            try:
                ftp.cwd(path)
            except error_perm as e:
                # path may be file
                ftp.quit()
                raise NotADirectoryError(rel) from e

            entries: List[Dict] = []
            # Try MLSD first
            try:
                for name, facts in ftp.mlsd():
                    if name in (".", ".."):
                        continue
                    is_dir = (facts.get("type") == "dir")
                    size = int(facts.get("size") or 0)
                    mtime = _parse_modify_to_epoch(facts.get("modify") or "")
                    entries.append({
                        "name": name,
                        "is_dir": is_dir,
                        "size": 0 if is_dir else size,
                        "mtime": mtime,
                        "type": "dir" if is_dir else "file",
                    })
                ftp.quit()
                return entries
            except Exception:
                # Fallback to NLST + probing
                pass

            names = []
            try:
                names = ftp.nlst()
            except Exception:
                ftp.quit()
                return []

            for name in names:
                if name in (".", ".."):
                    continue
                is_dir = False
                size = 0
                mtime = 0
                try:
                    # If we can CWD, it's a directory
                    ftp.cwd(_join_remote(path, name))
                    ftp.cwd(path)
                    is_dir = True
                except Exception:
                    is_dir = False
                    try:
                        size = ftp.size(_join_remote(path, name)) or 0
                    except Exception:
                        size = 0
                try:
                    mdtm = ftp.sendcmd("MDTM " + _join_remote(path, name))
                    # Example: '213 20241012XXXXXX'
                    if mdtm.startswith("213 "):
                        mtime = _parse_modify_to_epoch(mdtm.split(" ", 1)[1])
                except Exception:
                    pass
                entries.append({
                    "name": name,
                    "is_dir": is_dir,
                    "size": 0 if is_dir else int(size or 0),
                    "mtime": int(mtime or 0),
                    "type": "dir" if is_dir else "file",
                })
            ftp.quit()
            return entries

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
            ftp = self._connect()
            try:
                chunks: List[bytes] = []
                ftp.retrbinary("RETR " + path, lambda b: chunks.append(b))
                return b"".join(chunks)
            except error_perm as e:
                if str(e).startswith("550"):
                    raise FileNotFoundError(rel)
                raise
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        return await asyncio.to_thread(_do_read)

    async def write_file(self, root: str, rel: str, data: bytes):
        path = _join_remote(root, rel)

        def _ensure_dirs(ftp: FTP, dir_path: str):
            parts = [p for p in dir_path.strip("/").split("/") if p]
            cur = "/"
            for p in parts:
                cur = _join_remote(cur, p)
                try:
                    ftp.mkd(cur)
                except Exception:
                    pass

        def _do_write():
            ftp = self._connect()
            try:
                parent = "/" if "/" not in path.strip("/") else path.rsplit("/", 1)[0]
                _ensure_dirs(ftp, parent)
                from io import BytesIO
                bio = BytesIO(data)
                ftp.storbinary("STOR " + path, bio)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        await asyncio.to_thread(_do_write)

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        # KISS: 聚合后一次性写入
        buf = bytearray()
        async for chunk in data_iter:
            if chunk:
                buf.extend(chunk)
        await self.write_file(root, rel, bytes(buf))
        return len(buf)

    async def mkdir(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_mkdir():
            ftp = self._connect()
            try:
                parts = [p for p in path.strip("/").split("/") if p]
                cur = "/"
                for p in parts:
                    cur = _join_remote(cur, p)
                    try:
                        ftp.mkd(cur)
                    except Exception:
                        pass
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        await asyncio.to_thread(_do_mkdir)

    async def delete(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_delete():
            ftp = self._connect()
            try:
                # Try file delete
                try:
                    ftp.delete(path)
                    return
                except Exception:
                    pass

                # Recursively delete dir
                def _rm_tree(dir_path: str):
                    try:
                        ftp.cwd(dir_path)
                    except Exception:
                        return
                    items = []
                    try:
                        for name, facts in ftp.mlsd():
                            if name in (".", ".."):
                                continue
                            items.append((name, facts.get("type") == "dir"))
                    except Exception:
                        try:
                            names = ftp.nlst()
                        except Exception:
                            names = []
                        for n in names:
                            if n in (".", ".."):
                                continue
                            # Best-effort dir check
                            try:
                                ftp.cwd(_join_remote(dir_path, n))
                                ftp.cwd(dir_path)
                                items.append((n, True))
                            except Exception:
                                items.append((n, False))
                    for n, is_dir in items:
                        child = _join_remote(dir_path, n)
                        if is_dir:
                            _rm_tree(child)
                        else:
                            try:
                                ftp.delete(child)
                            except Exception:
                                pass
                    try:
                        ftp.rmd(dir_path)
                    except Exception:
                        pass

                _rm_tree(path)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        await asyncio.to_thread(_do_delete)

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src = _join_remote(root, src_rel)
        dst = _join_remote(root, dst_rel)

        def _do_move():
            ftp = self._connect()
            try:
                # Ensure dst parent exists
                parent = "/" if "/" not in dst.strip("/") else dst.rsplit("/", 1)[0]
                parts = [p for p in parent.strip("/").split("/") if p]
                cur = "/"
                for p in parts:
                    cur = _join_remote(cur, p)
                    try:
                        ftp.mkd(cur)
                    except Exception:
                        pass
                ftp.rename(src, dst)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        await asyncio.to_thread(_do_move)

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src = _join_remote(root, src_rel)
        dst = _join_remote(root, dst_rel)

        # naive implementation: download then upload; recursively for dirs
        async def _is_dir(path: str) -> bool:
            def _probe() -> bool:
                ftp = self._connect()
                try:
                    try:
                        ftp.cwd(path)
                        return True
                    except Exception:
                        return False
                finally:
                    try:
                        ftp.quit()
                    except Exception:
                        pass
            return await asyncio.to_thread(_probe)

        if await _is_dir(src):
            # list children, create dst dir, copy recursively
            await self.mkdir(root, dst_rel)

            children, _ = await self.list_dir(root, src_rel, page_num=1, page_size=10_000)
            for ent in children:
                child_src = f"{src_rel.rstrip('/')}/{ent['name']}"
                child_dst = f"{dst_rel.rstrip('/')}/{ent['name']}"
                await self.copy(root, child_src, child_dst, overwrite)
            return

        # file
        data = await self.read_file(root, src_rel)
        if not overwrite:
            # best-effort existence check
            try:
                await self.stat_file(root, dst_rel)
                raise FileExistsError(dst_rel)
            except FileNotFoundError:
                pass
        await self.write_file(root, dst_rel, data)

    async def stat_file(self, root: str, rel: str):
        path = _join_remote(root, rel)

        def _do_stat():
            ftp = self._connect()
            try:
                # Try MLST
                try:
                    resp: List[str] = []
                    ftp.retrlines("MLST " + path, resp.append)
                    # The last line usually contains facts
                    facts = {}
                    if resp:
                        facts = _parse_mlst_line(resp[-1])
                    name = rel.split("/")[-1]
                    t = facts.get("type") or "file"
                    is_dir = t == "dir"
                    size = int(facts.get("size") or 0)
                    mtime = _parse_modify_to_epoch(facts.get("modify") or "")
                    return {
                        "name": name,
                        "is_dir": is_dir,
                        "size": 0 if is_dir else size,
                        "mtime": mtime,
                        "type": "dir" if is_dir else "file",
                        "path": path,
                    }
                except Exception:
                    pass

                # Probe directory
                try:
                    ftp.cwd(path)
                    return {
                        "name": rel.split("/")[-1],
                        "is_dir": True,
                        "size": 0,
                        "mtime": 0,
                        "type": "dir",
                        "path": path,
                    }
                except Exception:
                    pass

                # Treat as file
                try:
                    size = ftp.size(path) or 0
                except Exception:
                    size = 0
                try:
                    mdtm = ftp.sendcmd("MDTM " + path)
                    mtime = _parse_modify_to_epoch(mdtm.split(" ", 1)[1]) if mdtm.startswith("213 ") else 0
                except Exception:
                    mtime = 0
                return {
                    "name": rel.split("/")[-1],
                    "is_dir": False,
                    "size": int(size or 0),
                    "mtime": int(mtime or 0),
                    "type": "file",
                    "path": path,
                }
            except error_perm as e:
                if str(e).startswith("550"):
                    raise FileNotFoundError(rel)
                raise
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        return await asyncio.to_thread(_do_stat)

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        path = _join_remote(root, rel)
        # Get size (best-effort)
        def _get_size() -> Optional[int]:
            ftp = self._connect()
            try:
                try:
                    return int(ftp.size(path) or 0)
                except Exception:
                    return None
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        total_size = await asyncio.to_thread(_get_size)
        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"

        rng: Optional[_Range] = None
        status = 200
        headers = {"Accept-Ranges": "bytes", "Content-Type": content_type}
        if range_header and range_header.startswith("bytes=") and total_size is not None:
            try:
                s, e = (range_header.removeprefix("bytes=").split("-", 1))
                start = int(s) if s.strip() else 0
                end = int(e) if e.strip() else (total_size - 1)
                if start >= total_size:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")
                if end >= total_size:
                    end = total_size - 1
                rng = _Range(start, end)
                status = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
                headers["Content-Length"] = str(end - start + 1)
            except ValueError:
                raise HTTPException(400, detail="Invalid Range header")
        elif total_size is not None:
            headers["Content-Length"] = str(total_size)

        queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=8)

        class _Stop(Exception):
            pass

        def _worker():
            ftp = self._connect()
            remaining = None
            if rng is not None:
                remaining = (rng.end - rng.start + 1) if rng.end is not None else None

            def _cb(chunk: bytes):
                nonlocal remaining
                if not chunk:
                    return
                try:
                    if remaining is not None:
                        if len(chunk) > remaining:
                            part = chunk[:remaining]
                            queue.put_nowait(part)
                            remaining = 0
                            raise _Stop()
                        else:
                            queue.put_nowait(chunk)
                            remaining -= len(chunk)
                            if remaining <= 0:
                                raise _Stop()
                    else:
                        queue.put_nowait(chunk)
                except _Stop:
                    raise
                except Exception:
                    # queue full or event loop closed
                    raise _Stop()

            try:
                if rng is not None:
                    ftp.retrbinary("RETR " + path, _cb, rest=rng.start)
                else:
                    ftp.retrbinary("RETR " + path, _cb)
                queue.put_nowait(None)
            except _Stop:
                try:
                    queue.put_nowait(None)
                except Exception:
                    pass
            except error_perm as e:
                try:
                    queue.put_nowait(None)
                except Exception:
                    pass
                if str(e).startswith("550"):
                    pass
            finally:
                try:
                    ftp.quit()
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


ADAPTER_TYPE = "ftp"

CONFIG_SCHEMA = [
    {"key": "host", "label": "主机", "type": "string", "required": True, "placeholder": "ftp.example.com"},
    {"key": "port", "label": "端口", "type": "number", "required": False, "default": 21},
    {"key": "username", "label": "用户名", "type": "string", "required": False},
    {"key": "password", "label": "密码", "type": "password", "required": False},
    {"key": "passive", "label": "被动模式", "type": "boolean", "required": False, "default": True},
    {"key": "timeout", "label": "超时(秒)", "type": "number", "required": False, "default": 15},
    {"key": "root", "label": "根路径", "type": "string", "required": False, "default": "/"},
]


def ADAPTER_FACTORY(rec: StorageAdapter):
    return FTPAdapter(rec)
