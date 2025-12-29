import base64
import datetime as dt
import hashlib
import hmac
import uuid
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Request, Response
from fastapi import HTTPException

from domain.audit import AuditAction, audit
from domain.config.service import ConfigService
from domain.virtual_fs.service import VirtualFSService


router = APIRouter(prefix="/s3", tags=["s3"])


FALSEY = {"0", "false", "off", "no"}
_XML_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


class S3Settings(Dict[str, str]):
    bucket: str
    region: str
    base_path: str
    access_key: str
    secret_key: str


def _now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _etag(key: str, size: Optional[int], mtime: Optional[int]) -> str:
    raw = f"{key}|{size or 0}|{mtime or 0}".encode("utf-8")
    return '"' + hashlib.md5(raw).hexdigest() + '"'


def _meta_headers() -> Tuple[str, Dict[str, str]]:
    req_id = uuid.uuid4().hex
    headers = {
        "x-amz-request-id": req_id,
        "x-amz-id-2": uuid.uuid4().hex,
        "Server": "FoxelS3",
    }
    return req_id, headers


def _s3_error(code: str, message: str, resource: str = "", status: int = 400) -> Response:
    req_id, headers = _meta_headers()
    xml = (
        f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<Error>"
        f"<Code>{code}</Code>"
        f"<Message>{message}</Message>"
        f"<Resource>{resource}</Resource>"
        f"<RequestId>{req_id}</RequestId>"
        f"</Error>"
    )
    return Response(content=xml, status_code=status, media_type="application/xml", headers=headers)


async def _ensure_enabled() -> Optional[Response]:
    flag = await ConfigService.get("S3_MAPPING_ENABLED", "1")
    if str(flag).strip().lower() in FALSEY:
        return _s3_error("ServiceUnavailable", "S3 mapping disabled", status=503)
    return None


async def _get_settings() -> Tuple[Optional[S3Settings], Optional[Response]]:
    bucket = (await ConfigService.get("S3_MAPPING_BUCKET", "foxel")) or "foxel"
    region = ((await ConfigService.get("S3_MAPPING_REGION", "")) or "").strip()
    base_path = (await ConfigService.get("S3_MAPPING_BASE_PATH", "/")) or "/"
    access_key = (await ConfigService.get("S3_MAPPING_ACCESS_KEY")) or ""
    secret_key = (await ConfigService.get("S3_MAPPING_SECRET_KEY")) or ""
    if not access_key or not secret_key:
        return None, _s3_error(
            "InvalidAccessKeyId",
            "S3 mapping access key/secret are not configured.",
            status=403,
        )
    settings: S3Settings = {
        "bucket": bucket,
        "region": region,
        "base_path": base_path,
        "access_key": access_key,
        "secret_key": secret_key,
    }
    return settings, None


def _canonical_uri(path: str) -> str:
    from urllib.parse import quote

    if not path:
        return "/"
    return quote(path, safe="/-_.~")


def _canonical_query(params: Iterable[Tuple[str, str]]) -> str:
    from urllib.parse import quote

    encoded = []
    for key, value in params:
        enc_key = quote(key, safe="-_.~")
        enc_val = quote(value or "", safe="-_.~")
        encoded.append((enc_key, enc_val))
    encoded.sort()
    return "&".join(f"{k}={v}" for k, v in encoded)


def _normalize_ws(value: str) -> str:
    return " ".join(value.strip().split())


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


async def _authorize_sigv4(request: Request, settings: S3Settings) -> Optional[Response]:
    auth = request.headers.get("authorization")
    if not auth:
        return _s3_error("AccessDenied", "Missing Authorization header", status=403)
    scheme = "AWS4-HMAC-SHA256"
    if not auth.startswith(scheme + " "):
        return _s3_error("InvalidRequest", "Signature Version 4 is required", status=400)

    parts: Dict[str, str] = {}
    for segment in auth[len(scheme) + 1 :].split(","):
        k, _, v = segment.strip().partition("=")
        parts[k] = v

    credential = parts.get("Credential")
    signed_headers = parts.get("SignedHeaders")
    signature = parts.get("Signature")
    if not credential or not signed_headers or not signature:
        return _s3_error("InvalidRequest", "Authorization header is malformed", status=400)

    cred_parts = credential.split("/")
    if len(cred_parts) != 5 or cred_parts[-1] != "aws4_request":
        return _s3_error("InvalidRequest", "Credential scope is invalid", status=400)

    access_key, datestamp, region, service, _ = cred_parts
    if access_key != settings["access_key"]:
        return _s3_error("InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", status=403)
    if service != "s3":
        return _s3_error("InvalidRequest", "Only service 's3' is supported", status=400)
    if settings.get("region") and region != settings["region"]:
        return _s3_error("AuthorizationHeaderMalformed", f"Region '{region}' is invalid", status=400)

    amz_date = request.headers.get("x-amz-date")
    if not amz_date or not amz_date.startswith(datestamp):
        return _s3_error("AuthorizationHeaderMalformed", "x-amz-date does not match credential scope", status=400)

    payload_hash = request.headers.get("x-amz-content-sha256")
    if not payload_hash:
        return _s3_error("AuthorizationHeaderMalformed", "Missing x-amz-content-sha256", status=400)
    if payload_hash.upper().startswith("STREAMING-AWS4-HMAC-SHA256"):
        return _s3_error("NotImplemented", "Chunked uploads are not supported", status=400)

    signed_header_names = [h.strip().lower() for h in signed_headers.split(";") if h.strip()]
    headers = {k.lower(): v for k, v in request.headers.items()}
    canonical_headers = []
    for name in signed_header_names:
        value = headers.get(name)
        if value is None:
            return _s3_error("AuthorizationHeaderMalformed", f"Signed header '{name}' missing", status=400)
        canonical_headers.append(f"{name}:{_normalize_ws(value)}\n")

    canonical_request = "\n".join(
        [
            request.method,
            _canonical_uri(request.url.path),
            _canonical_query(request.query_params.multi_items()),
            "".join(canonical_headers),
            ";".join(signed_header_names),
            payload_hash,
        ]
    )

    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    scope = "/".join([datestamp, region, "s3", "aws4_request"])
    string_to_sign = "\n".join([scheme, amz_date, scope, hashed_request])

    k_date = _sign(("AWS4" + settings["secret_key"]).encode("utf-8"), datestamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    expected = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    if expected != signature:
        return _s3_error("SignatureDoesNotMatch", "The request signature we calculated does not match the signature you provided.", status=403)
    return None


def _virtual_path(settings: S3Settings, key: str) -> str:
    key_norm = key.strip("/")
    base_norm = settings["base_path"].strip("/")
    segments = [seg for seg in [base_norm, key_norm] if seg]
    if not segments:
        return "/"
    return "/" + "/".join(segments)


def _join_virtual(base: str, name: str) -> str:
    if not base or base == "/":
        return "/" + name.strip("/")
    return base.rstrip("/") + "/" + name.strip("/")


async def _list_dir_all(path: str) -> List[Dict]:
    items: List[Dict] = []
    page_num = 1
    page_size = 1000
    while True:
        try:
            res = await VirtualFSService.list_virtual_dir(path, page_num=page_num, page_size=page_size)
        except HTTPException as exc:  # directory missing
            if exc.status_code in (400, 404):
                return []
            raise
        chunk = res.get("items", [])
        items.extend(chunk)
        total = int(res.get("total", len(items)))
        if len(items) >= total or not chunk or len(chunk) < page_size:
            break
        page_num += 1
    return items


async def _collect_objects(path: str, key_prefix: str, recursive: bool, collect_prefixes: bool) -> Tuple[List[Tuple[str, Dict]], List[str]]:
    entries = await _list_dir_all(path)
    files: List[Tuple[str, Dict]] = []
    prefixes: List[str] = []
    for entry in entries:
        name = entry.get("name")
        if not name:
            continue
        if entry.get("is_dir"):
            dir_key = f"{key_prefix}{name.strip('/')}/"
            if collect_prefixes:
                prefixes.append(dir_key)
            if recursive:
                sub_path = _join_virtual(path, name)
                sub_files, _ = await _collect_objects(sub_path, dir_key, True, False)
                files.extend(sub_files)
        else:
            key = f"{key_prefix}{name}"
            files.append((key, entry))
    files.sort(key=lambda item: item[0])
    prefixes.sort()
    return files, prefixes


def _encode_token(key: str) -> str:
    raw = base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def _decode_token(token: str) -> Optional[str]:
    if not token:
        return None
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(token + padding).decode("utf-8")
    except Exception:
        return None


def _apply_pagination(entries: List[Tuple[str, Dict]], prefixes: List[str], max_keys: int, start_after: Optional[str], continuation_token: Optional[str]) -> Tuple[List[Tuple[str, Dict]], List[str], bool, Optional[str]]:
    combined = [(key, data, True) for key, data in entries] + [(prefix, None, False) for prefix in prefixes]
    combined.sort(key=lambda item: item[0])

    start_key = start_after or _decode_token(continuation_token or "")
    if start_key:
        combined = [item for item in combined if item[0] > start_key]

    is_truncated = len(combined) > max_keys
    sliced = combined[:max_keys]
    next_token = _encode_token(sliced[-1][0]) if is_truncated and sliced else None

    contents = [(key, data) for key, data, is_file in sliced if is_file]
    next_prefixes = [key for key, _, is_file in sliced if not is_file]
    return contents, next_prefixes, is_truncated, next_token


def _format_contents(entries: List[Tuple[str, Dict]]) -> str:
    blocks = []
    for key, meta in entries:
        size = int(meta.get("size", 0))
        mtime = meta.get("mtime")
        if mtime is not None:
            try:
                mtime_val = int(mtime)
            except Exception:
                mtime_val = 0
        else:
            mtime_val = 0
        last_modified = dt.datetime.utcfromtimestamp(mtime_val or dt.datetime.utcnow().timestamp()).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        etag = _etag(key, size, mtime_val)
        blocks.append(
            f"<Contents><Key>{key}</Key><LastModified>{last_modified}</LastModified><ETag>{etag}</ETag><Size>{size}</Size><StorageClass>STANDARD</StorageClass></Contents>"
        )
    return "".join(blocks)


def _format_common_prefixes(prefixes: List[str]) -> str:
    return "".join(f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefixes)


def _resource_path(bucket: str, key: Optional[str] = None) -> str:
    if key:
        return f"/s3/{bucket}/{key}"
    return f"/s3/{bucket}"


@router.get("")
@audit(action=AuditAction.READ, description="S3: 列出桶")
async def list_buckets(request: Request):
    if (resp := await _ensure_enabled()) is not None:
        return resp
    settings, err = await _get_settings()
    if err:
        return err
    assert settings
    if (auth := await _authorize_sigv4(request, settings)) is not None:
        return auth
    req_id, headers = _meta_headers()
    xml = (
        f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<ListAllMyBucketsResult xmlns=\"{_XML_NS}\">"
        f"<Owner><ID>{settings['access_key']}</ID><DisplayName>Foxel</DisplayName></Owner>"
        f"<Buckets><Bucket><Name>{settings['bucket']}</Name><CreationDate>{_now_iso()}</CreationDate></Bucket></Buckets>"
        f"</ListAllMyBucketsResult>"
    )
    headers.update({"Content-Type": "application/xml"})
    return Response(content=xml, media_type="application/xml", headers=headers)


@router.get("/{bucket}")
@audit(action=AuditAction.READ, description="S3: 列出对象")
async def list_objects(request: Request, bucket: str):
    if (resp := await _ensure_enabled()) is not None:
        return resp
    settings, err = await _get_settings()
    if err:
        return err
    assert settings
    if bucket != settings["bucket"]:
        return _s3_error("NoSuchBucket", "The specified bucket does not exist.", _resource_path(bucket), status=404)
    if (auth := await _authorize_sigv4(request, settings)) is not None:
        return auth

    params = request.query_params
    if params.get("list-type", "2") != "2":
        return _s3_error("InvalidArgument", "Only ListObjectsV2 (list-type=2) is supported.", _resource_path(bucket), status=400)

    prefix = (params.get("prefix") or "").lstrip("/")
    delimiter = params.get("delimiter")
    recursive = not delimiter
    max_keys_raw = params.get("max-keys", "1000")
    try:
        max_keys = max(1, min(1000, int(max_keys_raw)))
    except ValueError:
        max_keys = 1000
    start_after = (params.get("start-after") or "").lstrip("/") or None
    continuation = params.get("continuation-token")

    # Exact file match if prefix is non-empty and does not end with '/'
    files: List[Tuple[str, Dict]] = []
    prefixes: List[str] = []
    if prefix and not prefix.endswith("/"):
        try:
            info = await VirtualFSService.stat_file(_virtual_path(settings, prefix))
            if not info.get("is_dir"):
                files = [(prefix, info)]
        except HTTPException as exc:
            if exc.status_code not in (400, 404):
                raise
        if files:
            contents, next_prefixes, is_truncated, next_token = _apply_pagination(files, [], max_keys, start_after, continuation)
            xml = _build_list_result(bucket, prefix, delimiter, contents, next_prefixes, max_keys, is_truncated, continuation, next_token, start_after)
            return xml

    dir_prefix = prefix if not prefix or prefix.endswith("/") else prefix + "/"
    virtual_dir = _virtual_path(settings, dir_prefix)
    files, prefixes = await _collect_objects(virtual_dir, dir_prefix, recursive, bool(delimiter))

    contents, next_prefixes, is_truncated, next_token = _apply_pagination(files, prefixes if delimiter else [], max_keys, start_after, continuation)
    return _build_list_result(bucket, prefix, delimiter, contents, next_prefixes if delimiter else [], max_keys, is_truncated, continuation, next_token, start_after)


@router.get("/{bucket}/", include_in_schema=False)
async def list_objects_with_slash(request: Request, bucket: str):
    return await list_objects(request, bucket)


def _build_list_result(
    bucket: str,
    prefix: str,
    delimiter: Optional[str],
    contents: List[Tuple[str, Dict]],
    prefixes: List[str],
    max_keys: int,
    is_truncated: bool,
    continuation: Optional[str],
    next_token: Optional[str],
    start_after: Optional[str],
):
    req_id, headers = _meta_headers()
    body = [f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>", f"<ListBucketResult xmlns=\"{_XML_NS}\">"]
    body.append(f"<Name>{bucket}</Name>")
    body.append(f"<Prefix>{prefix}</Prefix>")
    if delimiter:
        body.append(f"<Delimiter>{delimiter}</Delimiter>")
    if continuation:
        body.append(f"<ContinuationToken>{continuation}</ContinuationToken>")
    if start_after:
        body.append(f"<StartAfter>{start_after}</StartAfter>")
    body.append(f"<MaxKeys>{max_keys}</MaxKeys>")
    body.append(f"<KeyCount>{len(contents) + len(prefixes)}</KeyCount>")
    body.append(f"<IsTruncated>{str(is_truncated).lower()}</IsTruncated>")
    if next_token:
        body.append(f"<NextContinuationToken>{next_token}</NextContinuationToken>")
    body.append(_format_contents(contents))
    if prefixes:
        body.append(_format_common_prefixes(prefixes))
    body.append("</ListBucketResult>")
    xml = "".join(body)
    headers.update({"Content-Type": "application/xml"})
    return Response(content=xml, media_type="application/xml", headers=headers)


async def _ensure_bucket_and_auth(request: Request, bucket: str) -> Tuple[Optional[S3Settings], Optional[Response]]:
    if (resp := await _ensure_enabled()) is not None:
        return None, resp
    settings, err = await _get_settings()
    if err:
        return None, err
    assert settings
    if bucket != settings["bucket"]:
        return None, _s3_error("NoSuchBucket", "The specified bucket does not exist.", _resource_path(bucket), status=404)
    if (auth := await _authorize_sigv4(request, settings)) is not None:
        return None, auth
    return settings, None


def _object_headers(meta: Dict, key: str) -> Dict[str, str]:
    size = int(meta.get("size", 0))
    mtime = meta.get("mtime")
    if mtime is not None:
        try:
            mtime_val = int(mtime)
        except Exception:
            mtime_val = 0
    else:
        mtime_val = 0
    last_modified = dt.datetime.utcfromtimestamp(mtime_val or dt.datetime.utcnow().timestamp()).strftime("%a, %d %b %Y %H:%M:%S GMT")
    headers = {
        "Content-Length": str(size),
        "ETag": _etag(key, size, mtime_val),
        "Last-Modified": last_modified,
        "Accept-Ranges": "bytes",
        "x-amz-version-id": "null",
    }
    return headers


async def _stat_object(settings: S3Settings, key: str) -> Tuple[Optional[Dict], Optional[Response]]:
    try:
        info = await VirtualFSService.stat_file(_virtual_path(settings, key))
        if info.get("is_dir"):
            return None, _s3_error("NoSuchKey", "The specified key does not exist.", _resource_path(settings["bucket"], key), status=404)
        return info, None
    except HTTPException as exc:
        if exc.status_code == 404:
            return None, _s3_error("NoSuchKey", "The specified key does not exist.", _resource_path(settings["bucket"], key), status=404)
        raise


@router.api_route("/{bucket}/{object_path:path}", methods=["GET", "HEAD"])
@audit(action=AuditAction.DOWNLOAD, description="S3: 获取对象")
async def object_get_head(request: Request, bucket: str, object_path: str):
    settings, error = await _ensure_bucket_and_auth(request, bucket)
    if error:
        return error
    assert settings
    key = object_path.lstrip("/")
    meta, err = await _stat_object(settings, key)
    if err:
        return err
    assert meta
    _, base_headers = _meta_headers()
    base_headers.update(_object_headers(meta, key))
    if request.method == "HEAD":
        return Response(status_code=200, headers=base_headers)
    resp = await VirtualFSService.stream_file(_virtual_path(settings, key), request.headers.get("range"))
    safe_merge_keys = {"ETag", "Last-Modified", "x-amz-version-id", "Accept-Ranges"}
    for hk, hv in base_headers.items():
        if hk in safe_merge_keys:
            resp.headers.setdefault(hk, hv)
    resp.headers.setdefault("Content-Type", meta.get("mime") or "application/octet-stream")
    return resp


@router.put("/{bucket}/{object_path:path}")
@audit(action=AuditAction.UPLOAD, description="S3: 上传对象")
async def put_object(request: Request, bucket: str, object_path: str):
    settings, error = await _ensure_bucket_and_auth(request, bucket)
    if error:
        return error
    assert settings
    key = object_path.lstrip("/")
    await VirtualFSService.write_file_stream(_virtual_path(settings, key), request.stream(), overwrite=True)
    meta, err = await _stat_object(settings, key)
    if err:
        return err
    headers = _object_headers(meta, key)
    headers.pop("Content-Length", None)
    headers.pop("Accept-Ranges", None)
    headers["Content-Length"] = "0"
    _, extra = _meta_headers()
    headers.update(extra)
    return Response(status_code=200, headers=headers)


@router.delete("/{bucket}/{object_path:path}")
@audit(action=AuditAction.DELETE, description="S3: 删除对象")
async def delete_object(request: Request, bucket: str, object_path: str):
    settings, error = await _ensure_bucket_and_auth(request, bucket)
    if error:
        return error
    assert settings
    key = object_path.lstrip("/")
    try:
        await VirtualFSService.delete_path(_virtual_path(settings, key))
    except HTTPException as exc:
        if exc.status_code not in (400, 404):
            raise
    _, headers = _meta_headers()
    return Response(status_code=204, headers=headers)
