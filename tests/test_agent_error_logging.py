"""Tests that the agent domain logs failures instead of discarding them.

Every agent error path returns a generic error code to the model, so without a
server-side log record a real defect is indistinguishable from a rejected
argument. These tests pin that behaviour, including the requirement that
routine control-flow errors stay quiet.
"""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domain.agent.execution as execution
from domain.agent.execution import execute_tool, is_expected_error
from domain.agent.service import _execute_mcp_call
from domain.permission.execution import ExecutionError


class _FailingSession:
    """MCP session stub whose tool call blows up at the transport level."""

    async def call_tool(self, name, arguments):
        raise RuntimeError("transport exploded: 报告.txt")


def test_mcp_call_failure_is_logged_with_the_tool_name(caplog):
    session = _FailingSession()
    with caplog.at_level(logging.WARNING, logger="domain.agent.service"):
        text = asyncio.run(_execute_mcp_call(session, "vfs_read_text", {"path": "/报告.txt"}))

    records = [r for r in caplog.records if r.name == "domain.agent.service"]
    assert records, "a failed MCP tool call must leave a log record"
    assert "vfs_read_text" in records[0].getMessage()
    assert records[0].exc_info, "the traceback must be attached"


def test_mcp_call_failure_does_not_leak_exception_text(caplog):
    session = _FailingSession()
    with caplog.at_level(logging.WARNING, logger="domain.agent.service"):
        text = asyncio.run(_execute_mcp_call(session, "vfs_read_text", {"path": "/报告.txt"}))

    assert "execution_failed" in text
    assert "transport exploded" not in text
    assert "报告.txt" not in text


@pytest.mark.parametrize(
    "exc",
    [
        ExecutionError("permission_denied"),
        ValueError("bad"),
        TypeError("bad"),
        FileNotFoundError("nope"),
        HTTPException(status_code=403),
        HTTPException(status_code=404),
    ],
)
def test_expected_errors_are_classified_as_expected(exc):
    assert is_expected_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("boom"),
        AttributeError("missing"),
        # UnicodeEncodeError subclasses ValueError, so it is classified as a
        # defect on purpose -- it is the exception issue #137 was about.
        UnicodeEncodeError("ascii", "x", 0, 1, "ordinal not in range(128)"),
    ],
)
def test_unexpected_errors_are_not_expected(exc):
    assert is_expected_error(exc) is False


def test_permission_denial_stays_quiet(caplog):
    """A disabled account is normal control flow, not a defect."""
    user = SimpleNamespace(disabled=True, id=1)
    with caplog.at_level(logging.ERROR, logger="domain.agent.execution"):
        result = asyncio.run(execute_tool("vfs_stat", {"path": "/x"}, user, None))

    assert result["error"]["code"] == "permission_denied"
    assert [r for r in caplog.records if r.name == "domain.agent.execution"] == []


def test_defect_is_logged(monkeypatch, caplog):
    """Anything outside the known set gets a traceback and the tool name."""
    def boom(name, arguments):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr(execution, "validate_arguments", boom)
    user = SimpleNamespace(disabled=False, id=1)

    with caplog.at_level(logging.ERROR, logger="domain.agent.execution"):
        result = asyncio.run(execute_tool("vfs_stat", {"path": "/x"}, user, None))

    assert result["error"]["code"] == "execution_failed"
    records = [r for r in caplog.records if r.name == "domain.agent.execution"]
    assert records and "vfs_stat" in records[0].getMessage()
    assert records[0].exc_info


def test_unencodable_value_is_logged_not_swallowed(monkeypatch, caplog):
    """A UnicodeEncodeError must not be dismissed as a bad argument."""
    def boom(name, arguments):
        raise UnicodeEncodeError("ascii", "x", 6, 9, "ordinal not in range(128)")

    monkeypatch.setattr(execution, "validate_arguments", boom)
    user = SimpleNamespace(disabled=False, id=1)

    with caplog.at_level(logging.ERROR, logger="domain.agent.execution"):
        asyncio.run(execute_tool("vfs_stat", {"path": "/示例目录"}, user, None))

    assert [r for r in caplog.records if r.name == "domain.agent.execution"]
