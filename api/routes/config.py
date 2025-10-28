import httpx
import time
from fastapi import APIRouter, Depends, Form
from typing import Annotated
from services.config import ConfigCenter, VERSION
from services.auth import get_current_active_user, User, has_users
from api.response import success
router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/")
async def get_config(
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str
):
    value = await ConfigCenter.get(key)
    return success({"key": key, "value": value})


@router.post("/")
async def set_config(
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str = Form(...),
    value: str = Form(...)
):
    await ConfigCenter.set(key, value)
    return success({"key": key, "value": value})


@router.get("/all")
async def get_all_config(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    configs = await ConfigCenter.get_all()
    return success(configs)


@router.get("/status")
async def get_system_status():
    logo = await ConfigCenter.get("APP_LOGO", "/logo.svg")
    favicon = await ConfigCenter.get("APP_FAVICON", logo)
    system_info = {
        "version": VERSION,
        "title": await ConfigCenter.get("APP_NAME", "Foxel"),
        "logo": logo,
        "favicon": favicon,
        "is_initialized": await has_users(),
        "app_domain": await ConfigCenter.get("APP_DOMAIN"),
        "file_domain": await ConfigCenter.get("FILE_DOMAIN"),
    }
    return success(system_info)


latest_version_cache = {
    "timestamp": 0,
    "data": None
}


@router.get("/latest-version")
async def get_latest_version():
    current_time = time.time()
    if current_time - latest_version_cache["timestamp"] < 3600 and latest_version_cache["data"]:
        return success(latest_version_cache["data"])
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.github.com/repos/DrizzleTime/Foxel/releases/latest",
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
            version_info = {
                "latest_version": data.get("tag_name"),
                "body": data.get("body")
            }
            latest_version_cache["timestamp"] = current_time
            latest_version_cache["data"] = version_info
            return success(version_info)
    except httpx.RequestError as e:
        if latest_version_cache["data"]:
            return success(latest_version_cache["data"])
        return success({"latest_version": None, "body": None})
