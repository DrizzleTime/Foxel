"""Tests for the x-foxel-current-path header codec.

See ``domain.agent.current_path`` for the encoding contract.
"""

from types import SimpleNamespace

import pytest

from domain.agent.current_path import (
    CURRENT_PATH_ENCODING_PREFIX,
    CURRENT_PATH_HEADER,
    decode_current_path,
    encode_current_path,
    ensure_ascii_header_value,
)
from domain.agent.mcp import _header_current_path

PATHS = [
    "/",
    "/docs/plain",
    "/docs/示例目录",
    "/shared/季度总结",
    "/photos/ünïcødé",
    "/emoji/🎉",
    # Percent signs in a real file name are the interesting case.
    "/photos/100%.png",
    "/photos/100%20a.png",
    "/photos/a%2Fb.png",
    "/a b/c#d?e",
    "/a//b/",
    "/trailing/slash/",
    # A path that itself looks like the marker must not be confused for one.
    "/foxel-cp1:/nested",
    "/" + "deep/" * 50 + "leaf",
    "/" + "长" * 200,
]


@pytest.mark.parametrize("path", PATHS)
def test_encode_is_ascii(path):
    encoded = encode_current_path(path)
    assert encoded.isascii()
    assert encoded.startswith(CURRENT_PATH_ENCODING_PREFIX)


@pytest.mark.parametrize("path", PATHS)
def test_round_trip(path):
    assert decode_current_path(encode_current_path(path)) == path


def test_encode_escapes_the_marker_separator():
    """safe='' means the payload can never contain the marker or a slash."""
    encoded = encode_current_path("/docs/示例目录")
    assert encoded == "foxel-cp1:%2Fdocs%2F%E7%A4%BA%E4%BE%8B%E7%9B%AE%E5%BD%95"


def test_marker_is_not_confused_with_path_content():
    """A path whose first segment equals the marker still round-trips."""
    path = "/foxel-cp1:/nested"
    encoded = encode_current_path(path)
    assert encoded.count(CURRENT_PATH_ENCODING_PREFIX) == 1
    assert decode_current_path(encoded) == path


def test_legacy_unmarked_value_is_passed_through():
    """Values from older clients are read as raw paths."""
    assert decode_current_path("/docs/示例目录") == "/docs/示例目录"
    assert decode_current_path("/docs/plain") == "/docs/plain"


def test_legacy_value_containing_percent_is_not_double_decoded():
    """The ambiguity that motivates the version marker.

    A bare unquote() would turn this legacy value into '/photos/100 a.png'.
    """
    assert decode_current_path("/photos/100%20a.png") == "/photos/100%20a.png"
    # Whereas a correctly marked value round-trips to the same name.
    assert decode_current_path(encode_current_path("/photos/100%20a.png")) == "/photos/100%20a.png"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_values_decode_to_none(raw):
    assert decode_current_path(raw) is None


def test_surrounding_whitespace_is_tolerated():
    assert decode_current_path(f"  {encode_current_path('/docs/示例目录')}  ") == "/docs/示例目录"


def test_header_value_guard_accepts_encoded_output():
    for path in PATHS:
        assert ensure_ascii_header_value(CURRENT_PATH_HEADER, encode_current_path(path))


def test_header_value_guard_rejects_raw_non_ascii():
    with pytest.raises(ValueError, match="must be ASCII"):
        ensure_ascii_header_value(CURRENT_PATH_HEADER, "/docs/示例目录")


def _context_with_header(value):
    """Build the minimal Context shape that _header_current_path() reads."""
    request = SimpleNamespace(headers={CURRENT_PATH_HEADER: value} if value is not None else {})
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest.mark.parametrize("path", PATHS)
def test_server_side_round_trip(path):
    """What the MCP server decodes back out of the header it was sent."""
    ctx = _context_with_header(encode_current_path(path))
    decoded = _header_current_path(ctx)
    # _normalize_path() collapses duplicate and trailing slashes, so compare
    # against the normalized form rather than the raw input.
    expected = "/" + "/".join(part for part in path.replace("\\", "/").split("/") if part)
    assert decoded == (expected or "/")


def test_server_side_reads_legacy_unmarked_header():
    """An external MCP client on an older version sends the raw path."""
    ctx = _context_with_header("/docs/示例目录")
    assert _header_current_path(ctx) == "/docs/示例目录"


def test_server_side_rejects_traversal_in_header():
    """A malformed header degrades to 'no current directory', never a crash."""
    ctx = _context_with_header(encode_current_path("/docs/../../etc"))
    assert _header_current_path(ctx) is None


def test_server_side_without_context():
    assert _header_current_path(None) is None
    assert _header_current_path(SimpleNamespace(request_context=None)) is None


def test_server_side_without_header():
    assert _header_current_path(_context_with_header(None)) is None
