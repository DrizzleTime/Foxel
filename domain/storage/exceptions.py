class StorageDomainError(Exception):
    """基础存储领域异常。"""


class StorageMountNotFound(StorageDomainError):
    def __init__(self, path: str):
        super().__init__(f"No storage mount for path: {path}")
        self.path = path


class StorageGatewayNotReady(StorageDomainError):
    def __init__(self, mount_id: int):
        super().__init__(f"Storage gateway not ready: {mount_id}")
        self.mount_id = mount_id
