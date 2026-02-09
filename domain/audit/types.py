from enum import StrEnum


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    REGISTER = "register"
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESET_PASSWORD = "reset_password"
    SHARE = "share"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    OTHER = "other"
