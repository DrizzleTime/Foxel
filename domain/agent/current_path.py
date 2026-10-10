"""Codec for the current-directory value carried in an HTTP request header.

The built-in AI assistant tells its in-process MCP server which directory the
user is browsing through the ``x-foxel-current-path`` request header. HTTP
header values are restricted to ASCII, and httpx encodes them as such, so a
path containing non-ASCII characters raised ``UnicodeEncodeError`` while the
client was being constructed -- before any request was sent.

Encoding rules
--------------
* Values are percent-encoded UTF-8 with every reserved character escaped, so
  the payload is an opaque token and can never collide with the marker.
* Encoded values carry a version marker (``foxel-cp1:``) so that decoding is
  unambiguous. A bare ``quote``/``unquote`` pair would mis-decode a legacy
  sender whose file name literally contains ``%20``: ``100%20a.png`` would be
  read as ``100 a.png``.
* Values without the marker predate this codec and are treated as raw paths.
  ``unquote`` is the identity on strings without ``%``, so such values keep
  working unchanged, and external MCP clients on older Foxel versions are not
  broken.
"""

from urllib.parse import quote, unquote

CURRENT_PATH_HEADER = "x-foxel-current-path"

# Bump the suffix if the encoding ever changes, so that a server running a
# newer codec never silently mis-decodes a value from an older one.
CURRENT_PATH_ENCODING_PREFIX = "foxel-cp1:"


def encode_current_path(path: str) -> str:
    """Encode a Foxel path into an ASCII-safe ``x-foxel-current-path`` value."""
    return CURRENT_PATH_ENCODING_PREFIX + quote(str(path), safe="")


def decode_current_path(raw: str | None) -> str | None:
    """Decode a header value produced by :func:`encode_current_path`.

    Returns ``None`` for missing or blank values. Unmarked values are returned
    unchanged for backward compatibility.
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.startswith(CURRENT_PATH_ENCODING_PREFIX):
        return unquote(value[len(CURRENT_PATH_ENCODING_PREFIX):])
    return value


def ensure_ascii_header_value(name: str, value: str) -> str:
    """Reject a header value that httpx would fail to encode.

    Every path written through :func:`encode_current_path` is ASCII by
    construction, so this is a tripwire: if a future change bypasses the codec
    it fails here with an actionable message instead of resurfacing as a
    silent ``UnicodeEncodeError`` in production.
    """
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(
            f"HTTP header {name!r} must be ASCII, got {value!r}. "
            "Encode the value before assigning it."
        ) from None
    return value
