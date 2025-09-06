from __future__ import annotations
from typing import List, Dict, Tuple, AsyncIterator
import io
import os
from models import StorageAdapter
from telethon import TelegramClient
from telethon.sessions import StringSession
import socks

# 适配器类型标识
ADAPTER_TYPE = "Telegram"

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

    def _get_client(self) -> TelegramClient:
        """创建一个新的 TelegramClient 实例"""
        return TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash, proxy=self.proxy)

    def get_effective_root(self, sub_path: str | None) -> str:
        return ""

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        if rel:
            return [], 0

        client = self._get_client()
        entries = []
        try:
            await client.connect()
            messages = await client.get_messages(self.chat_id, limit=50)
            for message in messages:
                if not message:
                    continue
                
                media = message.document or message.video or message.photo
                if not media:
                    continue

                filename = None
                size = 0
                
                if message.photo:
                    photo_size = message.photo.sizes[-1]
                    size = photo_size.size if hasattr(photo_size, 'size') else 0
                    filename = f"photo_{message.id}.jpg"

                elif message.document or message.video:
                    size = media.size
                    if hasattr(media, 'attributes'):
                        for attr in media.attributes:
                            if hasattr(attr, 'file_name') and attr.file_name:
                                filename = attr.file_name
                                break
                
                if not filename:
                    if message.text and '.' in message.text and len(message.text) < 256 and '\n' not in message.text:
                        filename = message.text
                
                if not filename:
                    filename = f"unknown_{message.id}"

                entries.append({
                    "name": f"{message.id}_{filename}",
                    "is_dir": False,
                    "size": size,
                    "mtime": int(message.date.timestamp()),
                    "ctime": int(message.date.timestamp()),  # Telegram uses message date for both
                    "type": "file",
                })
        finally:
            if client.is_connected():
                await client.disconnect()

        # 实现排序功能
        def sort_key(x):
            if sort_by == "name":
                return x["name"].lower()
            elif sort_by == "size":
                return x["size"]
            elif sort_by in ["mtime", "ctime"]:
                return x["mtime"]  # Telegram uses mtime for both
            else:
                return x["name"].lower()
        
        # 排序（Telegram 只有文件，没有目录）
        reverse_order = sort_order == "desc"
        entries.sort(key=sort_key, reverse=reverse_order)

        return entries, len(entries)

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
            await client.send_file(self.chat_id, file_like, caption=file_like.name)
        finally:
            if client.is_connected():
                await client.disconnect()

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        """以流式方式上传文件"""
        client = self._get_client()
        filename = os.path.basename(rel) or "file"
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, filename)
        
        total_size = 0
        try:
            with open(temp_path, "wb") as f:
                async for chunk in data_iter:
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            await client.connect()
            await client.send_file(self.chat_id, temp_path, caption=filename)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if client.is_connected():
                await client.disconnect()
        return total_size

    async def mkdir(self, root: str, rel: str):
        raise NotImplementedError("Telegram 适配器不支持创建目录。")

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
        
        try:
            await client.connect()
            message = await client.get_messages(self.chat_id, ids=message_id)
            media = message.document or message.video or message.photo
            if not message or not media:
                raise FileNotFoundError(f"在频道 {self.chat_id} 中未找到消息ID为 {message_id} 的文件")

            if message.photo:
                photo_size = media.sizes[-1]
                file_size = photo_size.size if hasattr(photo_size, 'size') else 0
                mime_type = "image/jpeg"
            else:
                file_size = media.size
                mime_type = media.mime_type or "application/octet-stream"

            start = 0
            end = file_size - 1
            status = 200
            
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Type": mime_type,
                "Content-Length": str(file_size),
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
                    headers["Content-Length"] = str(end - start + 1)
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
                    if client.is_connected():
                        await client.disconnect()

            return StreamingResponse(iterator(), status_code=status, headers=headers)

        except FileNotFoundError as e:
            if client.is_connected():
                await client.disconnect()
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            if client.is_connected():
                await client.disconnect()
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

            if message.photo:
                photo_size = media.sizes[-1]
                size = photo_size.size if hasattr(photo_size, 'size') else 0
            else:
                size = media.size

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