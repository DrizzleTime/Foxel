from typing import List, Dict, Tuple, AsyncIterator
import asyncio
import base64
import io
import os
import struct
from models import StorageAdapter
from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import StringSession
from telethon.tl import types
import socks

_SESSION_LOCKS: Dict[str, asyncio.Lock] = {}


def _get_session_lock(session_string: str) -> asyncio.Lock:
    lock = _SESSION_LOCKS.get(session_string)
    if lock is None:
        lock = asyncio.Lock()
        _SESSION_LOCKS[session_string] = lock
    return lock


class _NamedFile:
    def __init__(self, file_obj, name: str):
        self._file = file_obj
        self.name = name

    def read(self, *args, **kwargs):
        return self._file.read(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self._file.seek(*args, **kwargs)

    def tell(self):
        return self._file.tell()

    def seekable(self):
        return self._file.seekable()

    def close(self):
        return self._file.close()

    def __getattr__(self, name):
        return getattr(self._file, name)

# 适配器类型标识
ADAPTER_TYPE = "telegram"

# 适配器配置项定义
CONFIG_SCHEMA = [
    {"key": "api_id", "label": "API ID", "type": "string", "required": True, "help_text": "从 my.telegram.org 获取"},
    {"key": "api_hash", "label": "API Hash", "type": "password", "required": True, "help_text": "从 my.telegram.org 获取"},
    {"key": "session_string", "label": "Session String", "type": "password", "required": True, "help_text": "通过 generate_session.py 生成"},
    {"key": "chat_id", "label": "Chat ID", "type": "string", "required": True, "placeholder": "频道/群组的ID或用户名, 例如: -100123456789 或 'channel_username'"},
    {"key": "proxy_protocol", "label": "代理协议", "type": "string", "required": False, "placeholder": "例如: socks5, http"},
    {"key": "proxy_host", "label": "代理主机", "type": "string", "required": False, "placeholder": "例如: 127.0.0.1"},
    {"key": "proxy_port", "label": "代理端口", "type": "number", "required": False, "placeholder": "例如: 1080"},
]

class TelegramAdapter:
    """Telegram 存储适配器 (使用用户 Session)"""

    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.api_id = int(cfg.get("api_id"))
        self.api_hash = cfg.get("api_hash")
        self.session_string = cfg.get("session_string")
        self.chat_id_str = cfg.get("chat_id")
        
        # 代理设置
        self.proxy_protocol = cfg.get("proxy_protocol")
        self.proxy_host = cfg.get("proxy_host")
        self.proxy_port = cfg.get("proxy_port")
        
        self.proxy = None
        if self.proxy_protocol and self.proxy_host and self.proxy_port:
            proto_map = {
                "socks5": socks.SOCKS5,
                "http": socks.HTTP,
            }
            proxy_type = proto_map.get(self.proxy_protocol.lower())
            if proxy_type:
                self.proxy = (proxy_type, self.proxy_host, int(self.proxy_port))

        try:
            self.chat_id = int(self.chat_id_str)
        except (ValueError, TypeError):
            self.chat_id = self.chat_id_str

        if not all([self.api_id, self.api_hash, self.session_string, self.chat_id]):
            raise ValueError("Telegram 适配器需要 api_id, api_hash, session_string 和 chat_id")

    @staticmethod
    def _parse_legacy_session_string(value: str) -> StringSession:
        """
        兼容旧版 session_string 格式:
        - version(1B char) + base64(data)
        - data: dc_id(1B) + ip_len(2B) + ip(ASCII, ip_len bytes) + port(2B) + auth_key(256B)
        """
        s = (value or "").strip()
        if not s:
            raise ValueError("session_string 为空")

        body = s[1:] if s.startswith("1") else s
        raw = base64.urlsafe_b64decode(body)
        if len(raw) < 1 + 2 + 2 + 256:
            raise ValueError("legacy session 数据长度不足")

        dc_id = raw[0]
        ip_len = struct.unpack(">H", raw[1:3])[0]
        expected_len = 1 + 2 + ip_len + 2 + 256
        if len(raw) != expected_len:
            raise ValueError("legacy session 数据长度不匹配")

        ip_start = 3
        ip_end = ip_start + ip_len
        ip = raw[ip_start:ip_end].decode("utf-8")
        port = struct.unpack(">H", raw[ip_end : ip_end + 2])[0]
        key = raw[ip_end + 2 : ip_end + 2 + 256]

        sess = StringSession()
        sess.set_dc(dc_id, ip, port)
        sess.auth_key = AuthKey(key)
        return sess

    @staticmethod
    def _pick_photo_thumb(thumbs: list | None):
        if not thumbs:
            return None

        cached = []
        others = []
        for t in thumbs:
            if isinstance(t, (types.PhotoCachedSize, types.PhotoStrippedSize)):
                cached.append(t)
            elif isinstance(t, (types.PhotoSize, types.PhotoSizeProgressive)):
                if not isinstance(t, types.PhotoSizeEmpty):
                    others.append(t)

        if cached:
            cached.sort(key=lambda x: len(getattr(x, "bytes", b"") or b""))
            return cached[-1]

        if others:
            def _sz(x):
                if isinstance(x, types.PhotoSizeProgressive):
                    return max(x.sizes or [0])
                return int(getattr(x, "size", 0) or 0)

            others.sort(key=_sz)
            return others[-1]

        return None

    def _build_session(self) -> StringSession:
        s = (self.session_string or "").strip()
        if not s:
            raise ValueError("Telegram 适配器 session_string 为空")

        try:
            return StringSession(s)
        except Exception:
            pass

        # 少数工具可能去掉了 version 前缀，这里做一次兼容
        if not s.startswith("1"):
            try:
                return StringSession("1" + s)
            except Exception:
                pass

        try:
            return self._parse_legacy_session_string(s)
        except Exception as exc:
            raise ValueError("Telegram session_string 无效，请使用 Telethon StringSession 重新生成") from exc

    def _get_client(self) -> TelegramClient:
        """创建一个新的 TelegramClient 实例"""
        return TelegramClient(self._build_session(), self.api_id, self.api_hash, proxy=self.proxy)

    def get_effective_root(self, sub_path: str | None) -> str:
        return ""

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        if rel:
            return [], 0

        client = self._get_client()
        entries = []
        try:
            await client.connect()
            messages = await client.get_messages(self.chat_id, limit=200)
            for message in messages:
                if not message:
                    continue

                media = message.document or message.video or message.photo
                if not media:
                    continue

                file_meta = message.file
                if not file_meta:
                    continue

                filename = file_meta.name
                if not filename:
                    if message.text and '.' in message.text and len(message.text) < 256 and '\n' not in message.text:
                        filename = message.text
                    else:
                        filename = f"unknown_{message.id}"

                size = file_meta.size
                if size is None:
                    # 兼容缺失 size 的情况
                    if hasattr(media, "size") and media.size is not None:
                        size = media.size
                    elif message.photo and getattr(message.photo, "sizes", None):
                        photo_size = message.photo.sizes[-1]
                        size = getattr(photo_size, "size", 0) or 0
                    else:
                        size = 0

                entries.append({
                    "name": f"{message.id}_{filename}",
                    "is_dir": False,
                    "size": size,
                    "mtime": int(message.date.timestamp()),
                    "type": "file",
                })
        finally:
            if client.is_connected():
                await client.disconnect()

        # 排序
        reverse = sort_order.lower() == "desc"
        def get_sort_key(item):
            key = (not item["is_dir"],)
            sort_field = sort_by.lower()
            if sort_field == "name":
                key += (item["name"].lower(),)
            elif sort_field == "size":
                key += (item["size"],)
            elif sort_field == "mtime":
                key += (item["mtime"],)
            else:
                key += (item["name"].lower(),)
            return key
        entries.sort(key=get_sort_key, reverse=reverse)
        
        total_count = len(entries)
        
        # 分页
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        page_entries = entries[start_idx:end_idx]
        
        return page_entries, total_count

    async def read_file(self, root: str, rel: str) -> bytes:
        try:
            message_id_str, _ = rel.split('_', 1)
            message_id = int(message_id_str)
        except (ValueError, IndexError):
            raise FileNotFoundError(f"无效的文件路径格式: {rel}")

        client = self._get_client()
        try:
            await client.connect()
            message = await client.get_messages(self.chat_id, ids=message_id)
            if not message or not (message.document or message.video or message.photo):
                raise FileNotFoundError(f"在频道 {self.chat_id} 中未找到消息ID为 {message_id} 的文件")
            
            file_bytes = await client.download_media(message, file=bytes)
            return file_bytes
        finally:
            if client.is_connected():
                await client.disconnect()

    async def write_file(self, root: str, rel: str, data: bytes):
        """将字节数据作为文件上传"""
        client = self._get_client()
        file_like = io.BytesIO(data)
        file_like.name = os.path.basename(rel) or "file"

        try:
            await client.connect()
            sent = await client.send_file(self.chat_id, file_like, caption=file_like.name)
            message = sent[0] if isinstance(sent, list) and sent else sent
            actual_rel = rel
            if message:
                stored_name = file_like.name
                file_meta = getattr(message, "file", None)
                if file_meta and getattr(file_meta, "name", None):
                    stored_name = file_meta.name
                if getattr(message, "id", None) is not None:
                    actual_rel = f"{message.id}_{stored_name}"
            return {"rel": actual_rel, "size": len(data)}
        finally:
            if client.is_connected():
                await client.disconnect()

    async def write_upload_file(self, root: str, rel: str, file_obj, filename: str | None, file_size: int | None = None, content_type: str | None = None):
        client = self._get_client()
        name = filename or os.path.basename(rel) or "file"
        file_like = _NamedFile(file_obj, name)

        try:
            await client.connect()
            sent = await client.send_file(
                self.chat_id,
                file_like,
                caption=file_like.name,
                file_size=file_size,
                mime_type=content_type,
            )
            message = sent[0] if isinstance(sent, list) and sent else sent
            actual_rel = rel
            size = file_size or 0
            if message:
                stored_name = file_like.name
                file_meta = getattr(message, "file", None)
                if file_meta and getattr(file_meta, "name", None):
                    stored_name = file_meta.name
                if getattr(message, "id", None) is not None:
                    actual_rel = f"{message.id}_{stored_name}"
                if file_meta and getattr(file_meta, "size", None):
                    size = int(file_meta.size)
            return {"rel": actual_rel, "size": size}
        finally:
            if client.is_connected():
                await client.disconnect()

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        """以流式方式上传文件"""
        client = self._get_client()
        filename = os.path.basename(rel) or "file"
        import tempfile
        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            temp_path = tf.name
        
        total_size = 0
        try:
            with open(temp_path, "wb") as f:
                async for chunk in data_iter:
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            await client.connect()
            sent = await client.send_file(self.chat_id, temp_path, caption=filename)
            message = sent[0] if isinstance(sent, list) and sent else sent
            actual_rel = rel
            if message:
                stored_name = filename
                file_meta = getattr(message, "file", None)
                if file_meta and getattr(file_meta, "name", None):
                    stored_name = file_meta.name
                if getattr(message, "id", None) is not None:
                    actual_rel = f"{message.id}_{stored_name}"

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if client.is_connected():
                await client.disconnect()
        return {"rel": actual_rel, "size": total_size}

    async def mkdir(self, root: str, rel: str):
        raise NotImplementedError("Telegram 适配器不支持创建目录。")

    async def get_thumbnail(self, root: str, rel: str, size: str = "medium"):
        try:
            message_id_str, _ = rel.split('_', 1)
            message_id = int(message_id_str)
        except (ValueError, IndexError):
            return None

        client = self._get_client()
        try:
            await client.connect()
            message = await client.get_messages(self.chat_id, ids=message_id)
            if not message:
                return None

            doc = message.document or message.video
            thumbs = None
            if doc and getattr(doc, "thumbs", None):
                thumbs = list(doc.thumbs or [])
            elif message.photo and getattr(message.photo, "sizes", None):
                thumbs = list(message.photo.sizes or [])

            thumb = self._pick_photo_thumb(thumbs)
            if not thumb:
                return None

            result = await client.download_media(message, bytes, thumb=thumb)
            if isinstance(result, (bytes, bytearray)):
                return bytes(result)
            return None
        except Exception:
            return None
        finally:
            if client.is_connected():
                await client.disconnect()

    async def delete(self, root: str, rel: str):
        """删除一个文件 (即一条消息)"""
        try:
            message_id_str, _ = rel.split('_', 1)
            message_id = int(message_id_str)
        except (ValueError, IndexError):
            raise FileNotFoundError(f"无效的文件路径格式，无法解析消息ID: {rel}")

        client = self._get_client()
        try:
            await client.connect()
            result = await client.delete_messages(self.chat_id, [message_id])
            if not result or not result[0].pts:
                 raise FileNotFoundError(f"在 {self.chat_id} 中删除消息 {message_id} 失败，可能消息不存在或无权限")
        finally:
            if client.is_connected():
                await client.disconnect()

    async def move(self, root: str, src_rel: str, dst_rel: str):
        raise NotImplementedError("Telegram 适配器不支持移动。")

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        raise NotImplementedError("Telegram 适配器不支持重命名。")

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        raise NotImplementedError("Telegram 适配器不支持复制。")

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        from fastapi.responses import StreamingResponse
        from fastapi import HTTPException

        try:
            message_id_str, _ = rel.split('_', 1)
            message_id = int(message_id_str)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail=f"无效的文件路径格式: {rel}")

        client = self._get_client()
        lock = _get_session_lock(self.session_string)
        await lock.acquire()
        
        try:
            await client.connect()
            message = await client.get_messages(self.chat_id, ids=message_id)
            media = message.document or message.video or message.photo
            if not message or not media:
                raise FileNotFoundError(f"在频道 {self.chat_id} 中未找到消息ID为 {message_id} 的文件")

            file_meta = message.file
            file_size = file_meta.size if file_meta and file_meta.size is not None else None
            if file_size is None:
                if hasattr(media, "size") and media.size is not None:
                    file_size = media.size
                elif message.photo and getattr(message.photo, "sizes", None):
                    photo_size = message.photo.sizes[-1]
                    file_size = getattr(photo_size, "size", 0) or 0
                else:
                    file_size = 0

            mime_type = None
            if file_meta and getattr(file_meta, "mime_type", None):
                mime_type = file_meta.mime_type
            if not mime_type:
                if hasattr(media, "mime_type") and media.mime_type:
                    mime_type = media.mime_type
                elif message.photo:
                    mime_type = "image/jpeg"
                else:
                    mime_type = "application/octet-stream"

            start = 0
            end = file_size - 1
            status = 200
            
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Type": mime_type,
            }

            if range_header:
                try:
                    range_val = range_header.strip().partition("=")[2]
                    s, _, e = range_val.partition("-")
                    start = int(s) if s else 0
                    end = int(e) if e else file_size - 1
                    if start >= file_size or end >= file_size or start > end:
                        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")
                    status = 206
                    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid Range header")

            async def iterator():
                try:
                    limit = end - start + 1
                    downloaded = 0
                    
                    async for chunk in client.iter_download(media, offset=start):
                        if downloaded + len(chunk) > limit:
                            yield chunk[:limit - downloaded]
                            break
                        yield chunk
                        downloaded += len(chunk)
                        if downloaded >= limit:
                            break
                finally:
                    try:
                        if client.is_connected():
                            await client.disconnect()
                    finally:
                        lock.release()

            return StreamingResponse(iterator(), status_code=status, headers=headers)

        except HTTPException:
            if client.is_connected():
                await client.disconnect()
            lock.release()
            raise
        except FileNotFoundError as e:
            if client.is_connected():
                await client.disconnect()
            lock.release()
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            if client.is_connected():
                await client.disconnect()
            lock.release()
            raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")

    async def stat_file(self, root: str, rel: str):
        try:
            message_id_str, filename = rel.split('_', 1)
            message_id = int(message_id_str)
        except (ValueError, IndexError):
            raise FileNotFoundError(f"无效的文件路径格式: {rel}")

        client = self._get_client()
        try:
            await client.connect()
            message = await client.get_messages(self.chat_id, ids=message_id)
            media = message.document or message.video or message.photo
            if not message or not media:
                raise FileNotFoundError(f"在频道 {self.chat_id} 中未找到消息ID为 {message_id} 的文件")

            file_meta = message.file
            size = file_meta.size if file_meta and file_meta.size is not None else None
            if size is None:
                if hasattr(media, "size") and media.size is not None:
                    size = media.size
                elif message.photo and getattr(message.photo, "sizes", None):
                    photo_size = message.photo.sizes[-1]
                    size = getattr(photo_size, "size", 0) or 0
                else:
                    size = 0

            return {
                "name": rel,
                "is_dir": False,
                "size": size,
                "mtime": int(message.date.timestamp()),
                "type": "file",
            }
        finally:
            if client.is_connected():
                await client.disconnect()

def ADAPTER_FACTORY(rec: StorageAdapter) -> TelegramAdapter:
    return TelegramAdapter(rec)
