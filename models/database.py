from tortoise import fields
from tortoise.models import Model


class StorageAdapter(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    type = fields.CharField(max_length=30)
    config = fields.JSONField()
    enabled = fields.BooleanField(default=True)
    path = fields.CharField(max_length=255, unique=True)
    sub_path = fields.CharField(max_length=1024, null=True)

    class Meta:
        table = "storage_adapters"


class UserAccount(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    email = fields.CharField(max_length=100, unique=True, null=True)
    full_name = fields.CharField(max_length=100, null=True)
    hashed_password = fields.CharField(max_length=128)
    disabled = fields.BooleanField(default=False)

    class Meta:
        table = "user"


class Configuration(Model):
    id = fields.IntField(pk=True)
    key = fields.CharField(max_length=100, unique=True)
    value = fields.TextField()

    class Meta:
        table = "configurations"


class AIProvider(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    identifier = fields.CharField(max_length=100, unique=True)
    provider_type = fields.CharField(max_length=50, null=True)
    api_format = fields.CharField(max_length=20)
    base_url = fields.CharField(max_length=512, null=True)
    api_key = fields.CharField(max_length=512, null=True)
    logo_url = fields.CharField(max_length=512, null=True)
    extra_config = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_providers"


class AIModel(Model):
    id = fields.IntField(pk=True)
    provider: fields.ForeignKeyRelation[AIProvider] = fields.ForeignKeyField(
        "models.AIProvider", related_name="models", on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=255)
    display_name = fields.CharField(max_length=255, null=True)
    description = fields.TextField(null=True)
    capabilities = fields.JSONField(null=True)
    context_window = fields.IntField(null=True)
    metadata = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_models"
        unique_together = ("provider", "name")

    @property
    def embedding_dimensions(self) -> int | None:
        metadata = self.metadata or {}
        if not isinstance(metadata, dict):
            return None
        value = metadata.get("embedding_dimensions")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @embedding_dimensions.setter
    def embedding_dimensions(self, value: int | None) -> None:
        base_metadata = self.metadata if isinstance(self.metadata, dict) else {}
        metadata = dict(base_metadata or {})
        if value is None:
            metadata.pop("embedding_dimensions", None)
        else:
            try:
                metadata["embedding_dimensions"] = int(value)
            except (TypeError, ValueError):
                metadata.pop("embedding_dimensions", None)
        self.metadata = metadata or None


class AIDefaultModel(Model):
    id = fields.IntField(pk=True)
    ability = fields.CharField(max_length=50, unique=True)
    model: fields.ForeignKeyRelation[AIModel] = fields.ForeignKeyField(
        "models.AIModel", related_name="default_for", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ai_default_models"


class AutomationTask(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    event = fields.CharField(max_length=50)

    path_pattern = fields.CharField(max_length=1024, null=True)
    filename_regex = fields.CharField(max_length=255, null=True)

    processor_type = fields.CharField(max_length=100)
    processor_config = fields.JSONField()

    enabled = fields.BooleanField(default=True)

    class Meta:
        table = "automation_tasks"


class AuditLog(Model):
    id = fields.IntField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    action = fields.CharField(max_length=50)
    description = fields.TextField(null=True)
    user_id = fields.IntField(null=True)
    username = fields.CharField(max_length=100, null=True)
    client_ip = fields.CharField(max_length=64, null=True)
    method = fields.CharField(max_length=10)
    path = fields.CharField(max_length=1024)
    status_code = fields.IntField()
    duration_ms = fields.FloatField(null=True)
    success = fields.BooleanField(default=True)
    request_params = fields.JSONField(null=True)
    request_body = fields.JSONField(null=True)
    error = fields.TextField(null=True)

    class Meta:
        table = "audit_logs"


class ShareLink(Model):
    id = fields.IntField(pk=True)
    token = fields.CharField(max_length=100, unique=True, index=True)
    name = fields.CharField(max_length=255)
    paths = fields.JSONField()
    user: fields.ForeignKeyRelation[UserAccount] = fields.ForeignKeyField(
        "models.UserAccount", related_name="shares", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(null=True)
    access_type = fields.CharField(max_length=20, default="public")
    hashed_password = fields.CharField(max_length=128, null=True)

    class Meta:
        table = "share_links"


class Plugin(Model):
    id = fields.IntField(pk=True)
    key = fields.CharField(max_length=100, unique=True)  # 插件唯一标识
    name = fields.CharField(max_length=255, null=True)
    version = fields.CharField(max_length=50, null=True)
    description = fields.TextField(null=True)
    author = fields.CharField(max_length=255, null=True)
    website = fields.CharField(max_length=2048, null=True)
    github = fields.CharField(max_length=2048, null=True)
    license = fields.CharField(max_length=100, null=True)

    # 完整 manifest 存储
    manifest = fields.JSONField(null=True)

    # 前端相关配置（从 manifest.frontend 提取）
    open_app = fields.BooleanField(default=False)
    supported_exts = fields.JSONField(null=True)
    default_bounds = fields.JSONField(null=True)
    default_maximized = fields.BooleanField(null=True)
    icon = fields.CharField(max_length=2048, null=True)

    # 已加载的组件追踪
    loaded_routes = fields.JSONField(null=True)  # ["/api/plugins/xxx", ...]
    loaded_processors = fields.JSONField(null=True)  # ["processor_type", ...]

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "plugins"
