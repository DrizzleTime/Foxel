from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Protocol, Tuple


class StorageGateway(Protocol):
    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[list[Dict], int]:
        ...

    async def read_file(self, root: str, rel: str) -> bytes:
        ...

    async def write_file(self, root: str, rel: str, data: bytes):
        ...

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        ...

    async def mkdir(self, root: str, rel: str):
        ...

    async def delete(self, root: str, rel: str):
        ...

    async def move(self, root: str, src_rel: str, dst_rel: str):
        ...

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        ...

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        ...

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        ...

    async def stat_file(self, root: str, rel: str):
        ...

    def get_effective_root(self, sub_path: str | None) -> str:
        ...


class StorageGatewayRegistry(Protocol):
    async def refresh(self):
        ...

    def get(self, mount_id: int) -> StorageGateway | None:
        ...
