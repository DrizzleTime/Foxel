import base64
import hashlib
import mimetypes
from email.utils import formatdate
from urllib.parse import urlparse, unquote
from typing import Optional

from fastapi import APIRouter, Request, Response, HTTPException, Depends
import xml.etree.ElementTree as ET

from domain.audit import AuditAction, audit
from domain.auth import AuthService, User, UserInDB
from domain.config import ConfigService
from domain.virtual_fs import VirtualFSService


_WEBDAV_ENABLED_KEY = "WEBDAV_MAPPING_ENABLED"


async def _ensure_webdav_enabled() -> None:
    enabled = await ConfigService.get(_WEBDAV_ENABLED_KEY, "1")
    if str(enabled).strip().lower() in ("0", "false", "off", "no"):
        raise HTTPException(503, detail="WebDAV mapping disabled")


router = APIRouter(prefix="/webdav", tags=["webdav"])


def _dav_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "DAV": "1",
        "MS-Author-Via": "DAV",
        "Accept-Ranges": "bytes",
        "Allow": ", ".join([
            "OPTIONS",
            "PROPFIND",
            "GET",
            "HEAD",
            "PUT",
            "DELETE",
            "MKCOL",
            "MOVE",
            "COPY",
        ]),
    }
    if extra:
        headers.update(extra)
    return headers


async def _get_basic_user(request: Request) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth:
        raise HTTPException(401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic realm=webdav"})

    scheme, _, param = auth.partition(" ")
    scheme_lower = scheme.lower()
    if scheme_lower == "basic":
        try:
            decoded = base64.b64decode(param).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            raise HTTPException(401, detail="Invalid Basic auth", headers={"WWW-Authenticate": "Basic realm=webdav"})
        user_or_false: Optional[UserInDB] = await AuthService.authenticate_user_db(username, password)
        if not user_or_false:
            raise HTTPException(401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic realm=webdav"})
        u: UserInDB = user_or_false
        return User(id=u.id, username=u.username, email=u.email, full_name=u.full_name, disabled=u.disabled)
    elif scheme_lower == "bearer":
        if not param:
            raise HTTPException(401, detail="Invalid Bearer token")
        return User(id=0, username="bearer", email=None, full_name=None, disabled=False)
    else:
        raise HTTPException(401, detail="Unsupported auth", headers={"WWW-Authenticate": "Basic realm=webdav"})


def _httpdate(ts: int | float) -> str:
    return formatdate(ts, usegmt=True)


def _etag(path: str, size: int | None, mtime: int | None) -> str:
    raw = f"{path}|{size or 0}|{mtime or 0}".encode("utf-8")
    return '"' + hashlib.md5(raw).hexdigest() + '"'


def _href_for(path: str, is_dir: bool) -> str:
    from urllib.parse import quote
    p = "/webdav" + (path if path.startswith("/") else "/" + path)
    if is_dir and not p.endswith("/"):
        p += "/"
    return quote(p)


def _build_prop_response(path: str, name: str, is_dir: bool, size: Optional[int], mtime: Optional[int], content_type: Optional[str]):
    ns = "{DAV:}"
    resp = ET.Element(ns + "response")
    href = ET.SubElement(resp, ns + "href")
    href.text = _href_for(path, is_dir)

    propstat = ET.SubElement(resp, ns + "propstat")
    prop = ET.SubElement(propstat, ns + "prop")

    displayname = ET.SubElement(prop, ns + "displayname")
    displayname.text = name

    resourcetype = ET.SubElement(prop, ns + "resourcetype")
    if is_dir:
        ET.SubElement(resourcetype, ns + "collection")

    if not is_dir:
        if size is not None:
            gcl = ET.SubElement(prop, ns + "getcontentlength")
            gcl.text = str(size)
        if content_type:
            gct = ET.SubElement(prop, ns + "getcontenttype")
            gct.text = content_type

    if mtime is not None:
        glm = ET.SubElement(prop, ns + "getlastmodified")
        glm.text = _httpdate(mtime)

    etag = ET.SubElement(prop, ns + "getetag")
    etag.text = _etag(path, size, mtime)

    status = ET.SubElement(propstat, ns + "status")
    status.text = "HTTP/1.1 200 OK"
    return resp


def _multistatus_xml(responses: list[ET.Element]) -> bytes:
    ns = "{DAV:}"
    ms = ET.Element(ns + "multistatus")
    for r in responses:
        ms.append(r)
    return ET.tostring(ms, encoding="utf-8", xml_declaration=True)


def _normalize_fs_path(path: str) -> str:
    full = "/" + path if not path.startswith("/") else path
    return unquote(full)


@router.options("/{path:path}")
@audit(action=AuditAction.READ, description="WebDAV: OPTIONS", user_kw="user")
async def options_root(_request: Request, path: str = "", _enabled: None = Depends(_ensure_webdav_enabled)):
    return Response(status_code=200, headers=_dav_headers())


@router.api_route("/{path:path}", methods=["PROPFIND"])
@audit(action=AuditAction.READ, description="WebDAV: PROPFIND", user_kw="user")
async def propfind(
    request: Request,
    path: str,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    depth = request.headers.get("Depth", "1").lower()
    if depth not in ("0", "1", "infinity"):
        depth = "1"

    responses: list[ET.Element] = []

    # 先获取当前路径信息
    try:
        st = await VirtualFSService.stat_file(full_path)
        is_dir = bool(st.get("is_dir"))
        name = st.get("name") or full_path.rsplit("/", 1)[-1] or "/"
        size = None if is_dir else int(st.get("size", 0))
        mtime = int(st.get("mtime", 0)) if st.get("mtime") is not None else None
        ctype = None if is_dir else (mimetypes.guess_type(name)[0] or "application/octet-stream")
        responses.append(_build_prop_response(full_path, name, is_dir, size, mtime, ctype))
    except FileNotFoundError:
        raise HTTPException(404, detail="Not found")

    if depth in ("1", "infinity"):
        try:
            listing = await VirtualFSService.list_virtual_dir(full_path, page_num=1, page_size=1000)
            for ent in listing["items"]:
                is_dir = bool(ent.get("is_dir"))
                name = ent.get("name")
                child_path = full_path.rstrip("/") + "/" + name
                size = None if is_dir else int(ent.get("size", 0))
                mtime = int(ent.get("mtime", 0)) if ent.get("mtime") is not None else None
                ctype = None if is_dir else (mimetypes.guess_type(name)[0] or "application/octet-stream")
                responses.append(_build_prop_response(child_path, name, is_dir, size, mtime, ctype))
        except HTTPException as e:
            if e.status_code == 400:
                pass
            else:
                raise

    xml = _multistatus_xml(responses)
    return Response(content=xml, status_code=207, media_type='application/xml; charset="utf-8"', headers=_dav_headers())


@router.get("/{path:path}")
@audit(action=AuditAction.DOWNLOAD, description="WebDAV: GET", user_kw="user")
async def dav_get(
    path: str,
    request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    range_header = request.headers.get("Range")
    return await VirtualFSService.stream_file(full_path, range_header)


@router.head("/{path:path}")
@audit(action=AuditAction.READ, description="WebDAV: HEAD", user_kw="user")
async def dav_head(
    path: str,
    _request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    try:
        st = await VirtualFSService.stat_file(full_path)
    except FileNotFoundError:
        raise HTTPException(404, detail="Not found")
    is_dir = bool(st.get("is_dir"))
    headers = _dav_headers()
    if not is_dir:
        size = int(st.get("size", 0))
        name = st.get("name") or full_path.rsplit("/", 1)[-1]
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        mtime = int(st.get("mtime", 0)) if st.get("mtime") is not None else None
        headers.update({
            "Content-Length": str(size),
            "Content-Type": ctype,
            "ETag": _etag(full_path, size, mtime),
        })
    return Response(status_code=200, headers=headers)


@router.api_route("/{path:path}", methods=["PUT"])
@audit(action=AuditAction.UPLOAD, description="WebDAV: PUT", user_kw="user")
async def dav_put(
    path: str,
    request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    async def body_iter():
        async for chunk in request.stream():
            if chunk:
                yield chunk
    size = await VirtualFSService.write_file_stream(full_path, body_iter(), overwrite=True)
    return Response(status_code=201, headers=_dav_headers({"Content-Length": "0"}))


@router.api_route("/{path:path}", methods=["DELETE"])
@audit(action=AuditAction.DELETE, description="WebDAV: DELETE", user_kw="user")
async def dav_delete(
    path: str,
    _request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    await VirtualFSService.delete_path(full_path)
    return Response(status_code=204, headers=_dav_headers())


@router.api_route("/{path:path}", methods=["MKCOL"])
@audit(action=AuditAction.CREATE, description="WebDAV: MKCOL", user_kw="user")
async def dav_mkcol(
    path: str,
    _request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_path = _normalize_fs_path(path)
    await VirtualFSService.make_dir(full_path)
    return Response(status_code=201, headers=_dav_headers())


def _parse_destination(dest: str) -> str:
    if not dest:
        raise HTTPException(400, detail="Missing Destination header")
    p = urlparse(dest)
    path = p.path if p.scheme else dest 
    if path.startswith("/webdav"):
        rel = path[len("/webdav"):]
    else:
        rel = path
    return _normalize_fs_path(rel)


@router.api_route("/{path:path}", methods=["MOVE"])
@audit(action=AuditAction.UPDATE, description="WebDAV: MOVE", user_kw="user")
async def dav_move(
    path: str,
    request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_src = _normalize_fs_path(path)
    dest_header = request.headers.get("Destination")
    dst = _parse_destination(dest_header or "")
    overwrite = request.headers.get("Overwrite", "T").upper() != "F" 
    await VirtualFSService.move_path(full_src, dst, overwrite=overwrite)
    return Response(status_code=204, headers=_dav_headers())


@router.api_route("/{path:path}", methods=["COPY"])
@audit(action=AuditAction.CREATE, description="WebDAV: COPY", user_kw="user")
async def dav_copy(
    path: str,
    request: Request,
    _enabled: None = Depends(_ensure_webdav_enabled),
    user: User = Depends(_get_basic_user),
):
    full_src = _normalize_fs_path(path)
    dest_header = request.headers.get("Destination")
    dst = _parse_destination(dest_header or "")
    overwrite = request.headers.get("Overwrite", "T").upper() != "F"  
    await VirtualFSService.copy_path(full_src, dst, overwrite=overwrite)
    return Response(status_code=201 if not overwrite else 204, headers=_dav_headers())
