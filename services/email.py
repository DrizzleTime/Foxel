import asyncio
import json
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from enum import Enum
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationError

from services.config import ConfigCenter
from services.logging import LogService


class EmailSecurity(str, Enum):
    NONE = "none"
    SSL = "ssl"
    STARTTLS = "starttls"


class EmailConfig(BaseModel):
    host: str
    port: int = Field(..., gt=0)
    username: Optional[str] = None
    password: Optional[str] = None
    sender_email: EmailStr
    sender_name: Optional[str] = None
    security: EmailSecurity = EmailSecurity.NONE
    timeout: float = Field(default=30.0, gt=0.0)


class EmailSendPayload(BaseModel):
    recipients: List[EmailStr] = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    template: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class EmailTemplateRenderer:
    ROOT = Path("templates/email")

    @classmethod
    def _resolve_path(cls, template_name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", template_name):
            raise ValueError("Invalid template name")
        return cls.ROOT / f"{template_name}.html"

    @classmethod
    async def list_templates(cls) -> list[str]:
        cls.ROOT.mkdir(parents=True, exist_ok=True)
        return sorted(
            path.stem
            for path in cls.ROOT.glob("*.html")
            if path.is_file()
        )

    @classmethod
    async def load(cls, template_name: str) -> str:
        path = cls._resolve_path(template_name)
        if not path.is_file():
            raise FileNotFoundError(f"Email template '{template_name}' not found")
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    @classmethod
    async def save(cls, template_name: str, content: str) -> None:
        path = cls._resolve_path(template_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, content, encoding="utf-8")

    @classmethod
    async def render(cls, template_name: str, context: Dict[str, Any]) -> str:
        raw = await cls.load(template_name)
        context = {k: str(v) for k, v in (context or {}).items()}
        return Template(raw).safe_substitute(context)


class EmailService:
    CONFIG_KEY = "EMAIL_CONFIG"

    @classmethod
    async def _load_config(cls) -> EmailConfig:
        raw_config = await ConfigCenter.get(cls.CONFIG_KEY)
        if raw_config is None:
            raise ValueError("Email configuration not found")

        if isinstance(raw_config, str):
            raw_config = raw_config.strip()
            data: Any = json.loads(raw_config) if raw_config else {}
        elif isinstance(raw_config, dict):
            data = raw_config
        else:
            raise ValueError("Invalid email configuration format")

        try:
            return EmailConfig(**data)
        except ValidationError as exc:
            raise ValueError(f"Invalid email configuration: {exc}") from exc

    @staticmethod
    def _html_to_text(html: str) -> str:
        stripped = re.sub(r"<[^>]+>", " ", html)
        return " ".join(stripped.split())

    @classmethod
    async def _deliver(cls, config: EmailConfig, payload: EmailSendPayload, html_body: str):
        message = EmailMessage()
        message["Subject"] = payload.subject
        message["From"] = formataddr((config.sender_name or str(config.sender_email), str(config.sender_email)))
        message["To"] = ", ".join([str(addr) for addr in payload.recipients])

        plain_body = cls._html_to_text(html_body)
        message.set_content(plain_body or html_body)
        message.add_alternative(html_body, subtype="html")

        await asyncio.to_thread(cls._deliver_sync, config, message)

    @staticmethod
    def _deliver_sync(config: EmailConfig, message: EmailMessage):
        if config.security == EmailSecurity.SSL:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout)
        else:
            smtp = smtplib.SMTP(config.host, config.port, timeout=config.timeout)

        try:
            if config.security == EmailSecurity.STARTTLS:
                smtp.starttls()
            if config.username and config.password:
                smtp.login(config.username, config.password)
            smtp.send_message(message)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

    @classmethod
    async def enqueue_email(
        cls,
        recipients: List[str],
        subject: str,
        template: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        from services.task_queue import TaskProgress, task_queue_service

        payload = EmailSendPayload(
            recipients=recipients,
            subject=subject,
            template=template,
            context=context or {},
        )

        task = await task_queue_service.add_task(
            "send_email",
            payload.model_dump(mode="json"),
        )

        await task_queue_service.update_progress(
            task.id,
            TaskProgress(stage="queued", percent=0.0, detail="Waiting to send"),
        )
        await LogService.action(
            "email_service",
            "Email task enqueued",
            details={"task_id": task.id, "subject": subject, "template": template},
        )
        return task

    @classmethod
    async def send_from_task(cls, task_id: str, data: Dict[str, Any]):
        from services.task_queue import TaskProgress, task_queue_service

        payload = EmailSendPayload(**data)

        await task_queue_service.update_progress(
            task_id,
            TaskProgress(stage="preparing", percent=10.0, detail="Rendering template"),
        )

        config = await cls._load_config()
        html_body = await EmailTemplateRenderer.render(payload.template, payload.context)

        await task_queue_service.update_progress(
            task_id,
            TaskProgress(stage="sending", percent=60.0, detail="Sending message"),
        )

        await cls._deliver(config, payload, html_body)

        await task_queue_service.update_progress(
            task_id,
            TaskProgress(stage="completed", percent=100.0, detail="Email sent"),
        )
        await LogService.info(
            "email_service",
            "Email sent",
            details={"task_id": task_id, "subject": payload.subject},
        )
