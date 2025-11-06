from fastapi import APIRouter, Depends, HTTPException

from services.auth import User, get_current_active_user
from services.email import EmailService, EmailTemplateRenderer
from schemas.email import EmailTestRequest, EmailTemplateUpdate, EmailTemplatePreviewPayload
from api.response import success
from services.logging import LogService


router = APIRouter(
    prefix="/api/email",
    tags=["email"],
)


@router.post("/test")
async def trigger_test_email(
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
    await LogService.action(
        "route:email",
        "Triggered email test",
        details={"task_id": task.id, "template": payload.template, "to": str(payload.to)},
        user_id=getattr(current_user, "id", None),
    )
    return success({"task_id": task.id})


@router.get("/templates")
async def list_email_templates(
    current_user: User = Depends(get_current_active_user),
):
    templates = await EmailTemplateRenderer.list_templates()
    return success({"templates": templates})


@router.get("/templates/{name}")
async def get_email_template(
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
async def update_email_template(
    name: str,
    payload: EmailTemplateUpdate,
    current_user: User = Depends(get_current_active_user),
):
    try:
        await EmailTemplateRenderer.save(name, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await LogService.action(
        "route:email",
        "Updated email template",
        details={"template": name},
        user_id=getattr(current_user, "id", None),
    )
    return success({"name": name})


@router.post("/templates/{name}/preview")
async def preview_email_template(
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
