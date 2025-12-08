from fastapi import APIRouter, Depends, HTTPException, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.email.service import EmailService, EmailTemplateRenderer
from domain.email.types import (
    EmailTemplatePreviewPayload,
    EmailTemplateUpdate,
    EmailTestRequest,
)


router = APIRouter(prefix="/api/email", tags=["email"])


@router.post("/test")
@audit(action=AuditAction.CREATE, description="发送测试邮件")
async def trigger_test_email(
    request: Request,
    payload: EmailTestRequest,
    current_user: User = Depends(get_current_active_user),
):
    try:
        task = await EmailService.enqueue_email(
            recipients=[str(payload.to)],
            subject=payload.subject,
            template=payload.template,
            context=payload.context,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return success({"task_id": task.id})


@router.get("/templates")
@audit(action=AuditAction.READ, description="获取邮件模板列表")
async def list_email_templates(
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    templates = await EmailTemplateRenderer.list_templates()
    return success({"templates": templates})


@router.get("/templates/{name}")
@audit(action=AuditAction.READ, description="查看邮件模板")
async def get_email_template(
    request: Request,
    name: str,
    current_user: User = Depends(get_current_active_user),
):
    try:
        content = await EmailTemplateRenderer.load(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="模板不存在")
    return success({"name": name, "content": content})


@router.post("/templates/{name}")
@audit(action=AuditAction.UPDATE, description="更新邮件模板")
async def update_email_template(
    request: Request,
    name: str,
    payload: EmailTemplateUpdate,
    current_user: User = Depends(get_current_active_user),
):
    try:
        await EmailTemplateRenderer.save(name, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return success({"name": name})


@router.post("/templates/{name}/preview")
@audit(action=AuditAction.READ, description="预览邮件模板")
async def preview_email_template(
    request: Request,
    name: str,
    payload: EmailTemplatePreviewPayload,
    current_user: User = Depends(get_current_active_user),
):
    try:
        html = await EmailTemplateRenderer.render(name, payload.context)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="模板不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return success({"html": html})
