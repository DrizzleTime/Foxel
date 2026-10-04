import asyncio
import json
import unittest
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from tortoise import Tortoise

from api.response import cursor_page, page
from domain.agent.api import router
from domain.agent.approvals import create_batch, execute_call, load_batch, now
from domain.agent.execution import execute_tool, snapshot_tree, validate_arguments
from domain.agent.mcp import MCP_HTTP_APP, mcp_client_session
from domain.agent.service import AgentService, _choose_chat_ability, _list_mcp_tools
from domain.agent.tools import mcp_tool_descriptors
from domain.agent.tools.base import tool_error, tool_result_to_content
from domain.agent.types import AgentChatRequest
from domain.ai import MissingModelError
from domain.auth import User, get_current_active_user
from domain.permission.execution import ExecutionError, execution_context, guard_path, validate_scope
from domain.permission.service import PermissionService
from domain.tasks.task_queue import TaskQueueService, TaskStatus
from domain.virtual_fs import VirtualFSService
from models.database import AgentApprovalBatch, AgentApprovalCall, PathRule, Role, StorageAdapter, UserAccount, UserRole


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["models.database"]}, _enable_global_fallback=True)
        await Tortoise.generate_schemas()
        self.account = await UserAccount.create(username="member", hashed_password="unused")
        self.user = User(id=self.account.id, username="member")
        self.admin_account = await UserAccount.create(username="admin", hashed_password="unused", is_admin=True)
        self.admin = User(id=self.admin_account.id, username="admin", is_admin=True)
        self.role = await Role.create(name="member")
        await UserRole.create(user_id=self.user.id, role_id=self.role.id)
        await PathRule.create(role_id=self.role.id, path_pattern="/allowed/**", can_read=True, can_write=True, can_delete=True)
        await PathRule.create(role_id=self.role.id, path_pattern="/allowed/secret/**", can_read=False, can_write=False, can_delete=False, priority=10)
        PermissionService.clear_cache()

    async def asyncTearDown(self):
        PermissionService.clear_cache()
        await Tortoise.close_connections()

    def assert_error(self, result, code):
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["error"]["code"], code, result)


class BoundaryTests(DatabaseTests):
    async def test_real_processor_scan_uses_snapshot_and_child_scopes(self):
        from domain.adapters import runtime_registry
        from domain.adapters.providers.local import LocalAdapter
        from domain.processors import TYPE_MAP, ProcessorService
        from domain.tasks import task_queue_service
        processor = SimpleNamespace(produces_file=True, supported_exts=["jpg"], supports_directory=False, requires_input_bytes=True,
                                    process=AsyncMock(return_value=b"processed"))
        with tempfile.TemporaryDirectory() as temporary:
            mount = await StorageAdapter.create(name="local", type="local", path="/allowed", config={"root": temporary})
            adapter = LocalAdapter(mount)
            root = Path(temporary)
            (root / "photos").mkdir()
            (root / "photos/a.jpg").write_bytes(b"a")
            (root / "photos/b.jpg").write_bytes(b"b")
            queue = TaskQueueService()
            with patch.object(runtime_registry, "get", return_value=adapter), patch.dict(TYPE_MAP, {"image_watermark": lambda: processor}), patch.object(task_queue_service, "add_task", new=queue.add_task):
                result = await execute_tool("processors_run", {"path": "/allowed/photos", "processor_type": "image_watermark", "config": {"text": "x"}, "max_depth": 0, "overwrite": False, "suffix": "_out"}, self.user)
                self.assertTrue(result["ok"], result)
                scan = queue.get_task(result["data"]["task_id"])
                await queue._execute_task(scan)
                self.assertEqual(scan.status, TaskStatus.SUCCESS, scan.error)
                children = [task for task in queue.get_all_tasks() if task.name == "process_file"]
                self.assertEqual(len(children), 2)
                for child in children:
                    self.assertEqual(list(child.task_info["_execution_scope"]["trees"]), [child.task_info["path"]])
                    await queue._execute_task(child)
                    self.assertEqual(child.status, TaskStatus.SUCCESS, child.error)
                self.assertEqual((root / "photos/a_out.jpg").read_bytes(), b"processed")
                self.assertEqual((root / "photos/b_out.jpg").read_bytes(), b"processed")

    async def test_real_local_recursive_delete_and_copy(self):
        from domain.adapters import runtime_registry
        from domain.adapters.providers.local import LocalAdapter
        with tempfile.TemporaryDirectory() as temporary:
            mount = await StorageAdapter.create(name="local", type="local", path="/allowed", config={"root": temporary})
            adapter = LocalAdapter(mount)
            with patch.object(runtime_registry, "get", return_value=adapter):
                root = Path(temporary)
                (root / "source/sub").mkdir(parents=True)
                (root / "source/sub/a.txt").write_text("hello")
                result = await execute_tool("vfs_copy", {"src": "/allowed/source", "dst": "/allowed/copied"}, self.user)
                self.assertTrue(result["ok"], result)
                self.assertEqual((root / "copied/sub/a.txt").read_text(), "hello")
                result = await execute_tool("vfs_delete", {"path": "/allowed/copied"}, self.user)
                self.assertTrue(result["ok"], result)
                self.assertFalse((root / "copied").exists())
                (root / "source/secret").mkdir()
                (root / "source/secret/a.txt").write_text("private")
                await PathRule.create(role_id=self.role.id, path_pattern="/allowed/source/secret/**", can_read=False, can_write=False, can_delete=False, priority=20)
                denied = await execute_tool("vfs_delete", {"path": "/allowed/source"}, self.user)
                self.assert_error(denied, "permission_denied")
                self.assertTrue((root / "source/sub/a.txt").exists())

    async def test_real_cross_mount_task_preserves_scope(self):
        from domain.adapters import runtime_registry
        from domain.adapters.providers.local import LocalAdapter
        from domain.tasks import task_queue_service
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right, tempfile.TemporaryDirectory() as staging:
            source_mount = await StorageAdapter.create(name="source", type="local", path="/allowed/source", config={"root": left})
            target_mount = await StorageAdapter.create(name="target", type="local", path="/allowed/target", config={"root": right})
            source_adapter, target_adapter = LocalAdapter(source_mount), LocalAdapter(target_mount)
            (Path(left) / "folder").mkdir()
            (Path(left) / "folder/a.txt").write_text("cross mount")
            (Path(right) / "out").mkdir()
            (Path(right) / "out/old.txt").write_text("old")
            queue = TaskQueueService()
            instances = {source_mount.id: source_adapter, target_mount.id: target_adapter}
            with patch.object(runtime_registry, "get", side_effect=instances.get), patch.object(task_queue_service, "add_task", new=queue.add_task), patch.object(VirtualFSService, "CROSS_TRANSFER_TEMP_ROOT", Path(staging)):
                result = await execute_tool("vfs_move", {"src": "/allowed/source/folder", "dst": "/allowed/target/out", "overwrite": True}, self.user)
                self.assertTrue(result["ok"], result)
                task = queue.get_task(result["data"]["task_id"])
                self.assertEqual(task.task_info["_execution_scope"]["user_id"], self.user.id)
                await queue._execute_task(task)
                self.assertEqual(task.status, TaskStatus.SUCCESS, task.error)
                self.assertEqual((Path(right) / "out/a.txt").read_text(), "cross mount")
                self.assertFalse((Path(right) / "out/old.txt").exists())
                self.assertFalse((Path(left) / "folder").exists())


    async def test_all_file_tools_deny_before_storage_access(self):
        cases = [
            ("vfs_list_dir", {"path": "/private"}),
            ("vfs_stat", {"path": "/private"}),
            ("vfs_read_text", {"path": "/private"}),
            ("vfs_write_text", {"path": "/private", "content": "x"}),
            ("vfs_mkdir", {"path": "/private"}),
            ("vfs_delete", {"path": "/private"}),
            ("vfs_copy", {"src": "/private", "dst": "/allowed/out"}),
            ("vfs_move", {"src": "/private", "dst": "/allowed/out"}),
            ("vfs_rename", {"src": "/private", "dst": "/allowed/out"}),
            ("processors_run", {"path": "/private", "processor_type": "image_watermark"}),
        ]
        with patch.object(VirtualFSService, "stat", AsyncMock()) as stat:
            for name, args in cases:
                with self.subTest(tool=name):
                    self.assert_error(await execute_tool(name, args, self.user), "permission_denied")
            stat.assert_not_awaited()

    async def test_admin_can_write_and_paths_are_canonical(self):
        with patch.object(VirtualFSService, "write_file", AsyncMock()) as written:
            result = await execute_tool("vfs_write_text", {"path": "//allowed\\docs//a.txt/", "content": "hello"}, self.admin)
        self.assertTrue(result["ok"], result)
        written.assert_awaited_once_with("/allowed/docs/a.txt", b"hello")

    async def test_no_identity_and_disabled_identity_denied(self):
        self.assert_error(await execute_tool("time", {}, None), "permission_denied")
        self.assert_error(await execute_tool("time", {}, self.user.model_copy(update={"disabled": True})), "permission_denied")

    async def test_invalid_inputs_do_not_execute(self):
        cases = [
            ("vfs_stat", {"path": "/allowed/../private"}),
            ("vfs_stat", {"path": "/allowed/./a"}),
            ("vfs_stat", {"path": "/allowed/\x00a"}),
            ("vfs_read_text", {"path": "/allowed/a", "max_chars": 0}),
            ("vfs_read_text", {"path": "/allowed/a", "max_chars": 100001}),
            ("vfs_read_text", {"path": "/allowed/a", "encoding": "bad-encoding"}),
            ("vfs_list_dir", {"path": "/allowed", "page_size": 101}),
            ("vfs_list_dir", {"path": "/allowed", "page": True}),
            ("vfs_list_dir", {"path": "/allowed", "sort_by": "invalid"}),
            ("vfs_search", {"q": "x", "mode": "unknown"}),
            ("vfs_search", {"q": "x", "top_k": 101}),
            ("processors_run", {"path": "/allowed", "processor_type": "x", "max_depth": -1}),
            ("web_fetch", {"url": "file:///etc/passwd"}),
            ("web_fetch", {"url": "https://example.com", "method": "TRACE"}),
            ("vfs_write_text", {"path": "/allowed/a", "content": "x", "user_id": self.admin.id}),
        ]
        for name, args in cases:
            with self.subTest(tool=name, args=args):
                self.assert_error(await execute_tool(name, args, self.user), "invalid_arguments")

    async def test_directory_listing_filters_children_and_preserves_cursor(self):
        listing = cursor_page([{"name": "ok", "is_dir": False}, {"name": "secret", "is_dir": True}], 50, next_cursor="next")
        with patch.object(VirtualFSService, "list_virtual_dir", AsyncMock(return_value=listing)) as listed:
            result = await execute_tool("vfs_list_dir", {"path": "/allowed", "cursor": "start"}, self.user)
        self.assertEqual([item["name"] for item in result["data"]["entries"]], ["ok"])
        self.assertEqual(result["data"]["pagination"]["next_cursor"], "next")
        self.assertEqual(listed.await_args.args[-1], "start")

    async def test_search_filters_private_snippets(self):
        from domain.virtual_fs.types import SearchResultItem
        from domain.virtual_fs.search import VirtualFSSearchService
        items = [SearchResultItem(id="1", path="/allowed/a", score=1, snippet="public"),
                 SearchResultItem(id="2", path="/private/a", score=1, snippet="private-secret")]
        with patch.object(VirtualFSSearchService, "search", AsyncMock(return_value={"items": items})):
            result = await execute_tool("vfs_search", {"q": "x"}, self.user)
        self.assertEqual(result["data"]["items"][0]["path"], "/allowed/a")
        self.assertNotIn("private-secret", json.dumps(result))

    async def test_recursive_denial_has_zero_mutations(self):
        tree = {"/allowed": True, "/allowed/ok": False, "/allowed/secret": True, "/allowed/secret/a": False}
        with patch("domain.agent.execution.snapshot_tree", AsyncMock(return_value=tree)), patch.object(VirtualFSService, "delete", AsyncMock()) as deleted:
            result = await execute_tool("vfs_delete", {"path": "/allowed"}, self.user)
        self.assert_error(result, "permission_denied")
        deleted.assert_not_awaited()

    async def test_transfer_checks_source_read_delete_and_target_children(self):
        source = {"/allowed/from": True, "/allowed/from/a": False}
        with patch("domain.agent.execution.snapshot_tree", AsyncMock(return_value=source)), patch.object(VirtualFSService, "stat", AsyncMock(return_value={"is_dir": True})), patch.object(VirtualFSService, "copy", AsyncMock()) as copied:
            result = await execute_tool("vfs_copy", {"src": "/allowed/from", "dst": "/allowed/secret/out"}, self.user)
        self.assert_error(result, "permission_denied")
        copied.assert_not_awaited()

    async def test_snapshot_supports_cursor_and_rejects_repeated_cursor(self):
        with patch.object(VirtualFSService, "stat", AsyncMock(return_value={"is_dir": True})), patch.object(VirtualFSService, "list_virtual_dir", AsyncMock(side_effect=[cursor_page([{"name": "a"}], 100, next_cursor="x"), cursor_page([{"name": "b"}], 100)])):
            tree = await snapshot_tree("/allowed")
        self.assertEqual(set(tree), {"/allowed", "/allowed/a", "/allowed/b"})
        with patch.object(VirtualFSService, "stat", AsyncMock(return_value={"is_dir": True})), patch.object(VirtualFSService, "list_virtual_dir", AsyncMock(return_value=cursor_page([], 100, next_cursor="x"))):
            with self.assertRaisesRegex(ExecutionError, "permission_scope_unverifiable"):
                await snapshot_tree("/allowed")

    async def test_snapshot_unknown_total_fails_closed(self):
        with patch.object(VirtualFSService, "stat", AsyncMock(return_value={"is_dir": True})), patch.object(VirtualFSService, "list_virtual_dir", AsyncMock(return_value={"items": [], "total": None})):
            with self.assertRaisesRegex(ExecutionError, "permission_scope_unverifiable"):
                await snapshot_tree("/allowed")

    async def test_new_child_and_permission_revocation_stop_task(self):
        scope = {"user_id": self.user.id, "permissions": [["/allowed", "read"]], "trees": {"/allowed": {"/allowed": True}}}
        with execution_context(scope), patch("domain.agent.execution.snapshot_tree", AsyncMock(return_value={"/allowed": True, "/allowed/new": False})):
            with self.assertRaisesRegex(ExecutionError, "permission_scope_changed"):
                await validate_scope()
        await UserAccount.filter(id=self.user.id).update(disabled=True)
        with execution_context({"user_id": self.user.id, "permissions": [["/allowed", "write"]]}):
            with self.assertRaisesRegex(ExecutionError, "permission_denied"):
                await guard_path("/allowed", "write")

    async def test_background_scope_and_child_identity_are_preserved(self):
        queue = TaskQueueService()
        scope = {"user_id": self.user.id, "permissions": [["/allowed/a", "read"]], "trees": {"/allowed/a": {"/allowed/a": False}}}
        with execution_context(scope):
            task = await queue.add_task("process_file", {"path": "/allowed/a", "processor_type": "vector_index", "config": {}})
        self.assertEqual(task.task_info["_execution_scope"]["user_id"], self.user.id)
        scope["permissions"].clear()
        self.assertTrue(task.task_info["_execution_scope"]["permissions"])
        with patch("domain.agent.execution.snapshot_tree", AsyncMock(return_value={"/allowed/a": False})), patch.object(VirtualFSService, "process_file", AsyncMock()) as processed:
            await UserAccount.filter(id=self.user.id).update(disabled=True)
            await queue._execute_task(task)
        self.assertEqual(task.status, TaskStatus.FAILED)
        processed.assert_not_awaited()

    async def test_processor_requires_output_write_and_valid_config(self):
        with patch("domain.agent.execution.snapshot_tree", AsyncMock(return_value={"/allowed/a.jpg": False})), patch.object(VirtualFSService, "path_is_directory", AsyncMock(return_value=False)), patch("domain.agent.tools.processors.ProcessorService.process_file", AsyncMock()) as processed:
            self.assert_error(await execute_tool("processors_run", {"path": "/allowed/a.jpg", "processor_type": "image_watermark", "config": {"text": "x"}, "save_to": "/private/out.jpg"}, self.user), "permission_denied")
            self.assert_error(await execute_tool("processors_run", {"path": "/allowed/a.jpg", "processor_type": "image_watermark", "config": {}}, self.user), "invalid_arguments")
            self.assert_error(await execute_tool("processors_run", {"path": "/allowed/a.jpg", "processor_type": "image_watermark", "config": {"text": "x"}}, self.user), "permission_scope_unverifiable")
        processed.assert_not_awaited()

    async def test_web_methods_remain_unconfirmed_with_accurate_annotations(self):
        descriptor = next(d for d in mcp_tool_descriptors(include_agent_only=True) if d.name == "web_fetch")
        self.assertFalse(descriptor.requires_confirmation)
        self.assertFalse(descriptor.annotations["readOnlyHint"])
        self.assertTrue(descriptor.annotations["destructiveHint"])
        self.assertTrue(descriptor.annotations["openWorldHint"])
        transport = httpx.MockTransport(lambda req: httpx.Response(409, text="conflict", request=req))
        original_client = httpx.AsyncClient
        with patch("domain.agent.tools.web_fetch.httpx.AsyncClient", lambda **kw: original_client(transport=transport, **kw)):
            for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
                result = await execute_tool("web_fetch", {"url": "https://example.com", "method": method}, self.user)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["data"]["status_code"], 409)

    async def test_web_response_limit_and_timeout(self):
        original_client = httpx.AsyncClient
        for handler, code in [(lambda req: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)), "response_too_large"),
                              (lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("secret")), "request_timeout")]:
            with patch("domain.agent.tools.web_fetch.httpx.AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw)):
                self.assert_error(await execute_tool("web_fetch", {"url": "https://example.com"}, self.user), code)

    async def test_internal_exception_is_redacted(self):
        with patch.object(VirtualFSService, "read_file", AsyncMock(side_effect=RuntimeError("secret password /etc/private"))):
            result = await execute_tool("vfs_read_text", {"path": "/allowed/a"}, self.user)
        self.assert_error(result, "execution_failed")
        self.assertNotIn("password", json.dumps(result))

    async def test_real_mcp_resources_auth_context_and_tools(self):
        with patch("domain.agent.mcp.AuthService.create_access_token", AsyncMock(return_value="test-token")), patch("domain.agent.mcp.AuthService.get_current_user", AsyncMock(return_value=self.user)):
            async with MCP_HTTP_APP.router.lifespan_context(MCP_HTTP_APP):
                async with mcp_client_session(self.user, "//allowed//docs") as session:
                    tools = await session.list_tools()
                    self.assertEqual(len(tools.tools), 12)
                    self.assertFalse({"time", "web_fetch"} & {tool.name for tool in tools.tools})
                    agent_tools = await _list_mcp_tools(session)
                    self.assertEqual(len(agent_tools), 14)
                    self.assertTrue({"time", "web_fetch"} <= {tool["name"] for tool in agent_tools})
                    for name, arguments in (("time", {}), ("web_fetch", {"url": "https://example.com"})):
                        with self.subTest(tool=name), patch("domain.agent.mcp.execute_tool", AsyncMock()) as executed:
                            blocked = await session.call_tool(name, arguments)
                            self.assertTrue(blocked.is_error)
                            executed.assert_not_awaited()
                    prompts = await session.list_prompts()
                    self.assertNotIn("fetch_web_page", {prompt.name for prompt in prompts.prompts})
                    policy = await session.read_resource("foxel://policy/tool-confirmation")
                    policy_data = json.loads(policy.contents[0].text)
                    self.assertNotIn("web_fetch", policy_data)
                    for key in ("read_tools", "unconfirmed_tools", "write_tools"):
                        self.assertFalse({"time", "web_fetch"} & set(policy_data[key]))
                    read_tool = next(tool for tool in tools.tools if tool.name == "vfs_read_text")
                    bounds = read_tool.input_schema["properties"]["max_chars"]
                    self.assertIn("100000", json.dumps(bounds))
                    invalid = await session.call_tool("vfs_read_text", {"path": "/allowed/a", "max_chars": True})
                    self.assertTrue(invalid.is_error)
                    current = await session.read_resource("foxel://context/current-path")
                    self.assertEqual(json.loads(current.contents[0].text)["current_path"], "/allowed/docs")
                    denied = await session.call_tool("vfs_read_text", {"path": "/private"})
                    self.assert_error(json.loads(denied.content[0].text), "permission_denied")
                    denied_resource = await session.read_resource("foxel://vfs/text/private")
                    self.assert_error(json.loads(denied_resource.contents[0].text), "permission_denied")


class ApprovalTests(DatabaseTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.assistant = {"role": "assistant", "content": "", "mcp_calls": [
            {"id": "one", "name": "vfs_write_text", "arguments": {"path": "/allowed/one", "content": "original"}},
            {"id": "two", "name": "vfs_mkdir", "arguments": {"path": "/allowed/two"}},
        ]}
        self.index = {d.name: {"meta": d.meta} for d in mcp_tool_descriptors(include_agent_only=True)}
        self.executed = []

        async def call_tool(name, arguments):
            self.executed.append((name, arguments))
            return SimpleNamespace(content=[], structured_content={"ok": True, "data": arguments})

        @asynccontextmanager
        async def session(*args):
            yield SimpleNamespace(call_tool=call_tool)

        self.patches = [
            patch("domain.agent.service.mcp_client_session", session),
            patch("domain.agent.service._list_mcp_tools", AsyncMock(return_value=[{"name": k, **v} for k, v in self.index.items()])),
            patch("domain.agent.service._choose_chat_ability", AsyncMock(return_value="tools")),
        ]
        for p in self.patches:
            p.start()
        self.model = AsyncMock(return_value={"role": "assistant", "content": "done"})
        self.model_patch = patch("domain.agent.service.chat_completion", self.model)
        self.model_patch.start()

    async def asyncTearDown(self):
        self.model_patch.stop()
        for p in reversed(self.patches):
            p.stop()
        await super().asyncTearDown()

    async def batch(self):
        return await create_batch(self.user.id, self.assistant, self.index)

    def request(self, batch, approved=(), rejected=(), messages=None):
        return AgentChatRequest(messages=messages or [self.assistant], approval_batch_id=batch.id,
                                approved_mcp_call_ids=list(approved), rejected_mcp_call_ids=list(rejected))

    async def test_partial_approval_uses_saved_arguments_and_blocks_model(self):
        batch = await self.batch()
        tampered = json.loads(json.dumps(self.assistant))
        tampered["mcp_calls"][0]["arguments"]["content"] = "tampered"
        result = await AgentService.chat(self.request(batch, approved=["one"], messages=[tampered]), self.user)
        self.assertEqual(self.executed[0][1]["content"], "original")
        self.assertEqual([p["id"] for p in result["pending_mcp_calls"]], ["two"])
        self.assertEqual(result["approval_batch_id"], batch.id)
        self.assertTrue(result["replace_messages"])
        self.model.assert_not_awaited()
        final = await AgentService.chat(self.request(batch, rejected=["two"], messages=result["messages"]), self.user)
        self.assertEqual(final["pending_mcp_calls"], [])
        wire = self.model.await_args.args[0]
        self.assertEqual([m["mcp_call_id"] for m in wire if m["role"] == "tool"], ["one", "two"])
        self.assertEqual(len(self.executed), 1)

    async def test_all_approvals_execute_in_original_order(self):
        batch = await self.batch()
        result = await AgentService.chat(self.request(batch, approved=["two", "one"]), self.user)
        self.assertEqual([name for name, _ in self.executed], ["vfs_write_text", "vfs_mkdir"])
        self.assertEqual(result["finish_reason"], "completed")
        repeated = await AgentService.chat(self.request(batch, approved=["two", "one"]), self.user)
        self.assertEqual(repeated, result)
        self.assertEqual(len(self.executed), 2)
        self.model.assert_awaited_once()

    async def test_concurrent_batch_requests_do_not_reorder_operations(self):
        batch = await self.batch()
        started, release = asyncio.Event(), asyncio.Event()

        async def execute(name, args):
            self.executed.append((name, args))
            started.set()
            await release.wait()
            return tool_result_to_content({"written": True})

        async def execute_mcp(session, name, args):
            return await execute(name, args)

        with patch("domain.agent.service._execute_mcp_call", new=execute_mcp):
            first = asyncio.create_task(AgentService.chat(self.request(batch, approved=["one", "two"]), self.user))
            await asyncio.wait_for(started.wait(), timeout=3)
            second = await AgentService.chat(self.request(batch, approved=["two"]), self.user)
            self.assertEqual(second["finish_reason"], "operation_in_progress")
            self.assertEqual(len(self.executed), 1)
            release.set()
            await first
        self.assertEqual([name for name, _ in self.executed], ["vfs_write_text", "vfs_mkdir"])

    async def test_unknown_cross_user_conflicting_and_legacy_ids_rejected(self):
        batch = await self.batch()
        for req, user in [(self.request(batch, approved=["unknown"]), self.user),
                          (self.request(batch, approved=["one"], rejected=["one"]), self.user),
                          (self.request(batch, approved=["one"]), self.admin),
                          (AgentChatRequest(messages=[self.assistant], approved_mcp_call_ids=["one"]), self.user)]:
            with self.subTest(req=req):
                with self.assertRaises(HTTPException) as error:
                    await AgentService.chat(req, user)
                self.assertEqual(error.exception.status_code, 400)
        self.assertFalse(self.executed)

    async def test_expired_calls_require_regeneration(self):
        batch = await self.batch()
        await AgentApprovalBatch.filter(id=batch.id).update(expires_at=now() - timedelta(seconds=1))
        with self.assertRaisesRegex(HTTPException, "approval_expired"):
            await AgentService.chat(self.request(batch, approved=["one"]), self.user)
        self.assertEqual(await AgentApprovalCall.filter(batch_id=batch.id, status="expired").count(), 2)
        self.assertFalse(self.executed)

    async def test_concurrent_claim_and_cancelled_write_never_retry(self):
        batch = await self.batch()
        record = await AgentApprovalCall.get(batch_id=batch.id, call_id="one")
        started, release = asyncio.Event(), asyncio.Event()
        execute = AsyncMock()

        async def blocking(*args):
            started.set()
            await release.wait()
            return tool_result_to_content({"written": True})

        execute.side_effect = blocking
        first = asyncio.create_task(execute_call(record, execute))
        await started.wait()
        second = await execute_call(record, execute)
        self.assertEqual(second.status, "running")
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        third = await execute_call(record, execute)
        self.assertEqual(third.status, "running")
        execute.assert_awaited_once()

    async def test_running_operation_keeps_pending_and_never_calls_model(self):
        batch = await self.batch()
        await AgentApprovalCall.filter(batch_id=batch.id, call_id="one").update(status="running")
        result = await AgentService.chat(self.request(batch, approved=["one", "two"]), self.user)
        self.assertEqual(result["finish_reason"], "operation_in_progress")
        self.assertEqual(len(result["pending_mcp_calls"]), 2)
        self.model.assert_not_awaited()
        self.assertFalse(self.executed)

    async def test_http_and_sse_partial_approval_parity_and_400(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_active_user] = lambda: self.user
        batch = await self.batch()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            invalid = await client.post("/api/agent/chat/stream", json={"approved_mcp_call_ids": ["one"]})
            self.assertEqual(invalid.status_code, 400)
            response = await client.post("/api/agent/chat", json=self.request(batch, approved=["one"]).model_dump())
            self.assertEqual(response.status_code, 200, response.text)
            normal = response.json()["data"]
            response = await client.post("/api/agent/chat/stream", json=self.request(batch, approved=["one"]).model_dump())
            self.assertEqual(response.status_code, 200, response.text)
            events = [part for part in response.text.split("\n\n") if part.startswith("event: done")]
            streamed = json.loads(events[-1].split("data: ", 1)[1])
            self.assertEqual(streamed, normal)
            self.assertEqual(len(self.executed), 1)

    async def test_iteration_limit_is_visible_and_keeps_results(self):
        self.model.return_value = {"role": "assistant", "content": "", "mcp_calls": [{"id": "time", "name": "time", "arguments": {}}]}
        result = await AgentService.chat(AgentChatRequest(messages=[{"role": "user", "content": "loop"}]), self.user)
        self.assertEqual(result["finish_reason"], "iteration_limit")
        self.assertEqual(self.model.await_count, 8)
        self.assertEqual(len([m for m in result["messages"] if m["role"] == "tool"]), 8)

    async def test_agent_only_tools_execute_locally_without_approval(self):
        self.model.side_effect = [
            {"role": "assistant", "content": "", "mcp_calls": [
                {"id": "clock", "name": "time", "arguments": {}},
                {"id": "page", "name": "web_fetch", "arguments": {"url": "https://example.com"}},
                {"id": "invalid", "name": "web_fetch", "arguments": {"url": "file:///etc/passwd"}},
            ]},
            {"role": "assistant", "content": "done"},
        ]
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text="test page", request=req))
        with patch("domain.agent.tools.web_fetch.httpx.AsyncClient", lambda **kw: original_client(transport=transport, **kw)):
            result = await AgentService.chat(AgentChatRequest(messages=[{"role": "user", "content": "check time and page"}]), self.user)
        self.assertEqual(result["finish_reason"], "completed")
        self.assertEqual(result["pending_mcp_calls"], [])
        self.assertEqual(self.executed, [])
        outputs = {message["mcp_call_id"]: json.loads(message["content"])
                   for message in result["messages"] if message["role"] == "tool"}
        self.assertTrue(outputs["clock"]["ok"])
        self.assertIn("datetime", outputs["clock"]["data"])
        self.assertTrue(outputs["page"]["ok"])
        self.assertEqual(outputs["page"]["data"]["text"], "test page")
        self.assert_error(outputs["invalid"], "invalid_arguments")

    async def test_missing_model_and_unsupported_provider_are_explicit(self):
        self.patches[-1].stop()
        with patch("domain.agent.service.AIProviderService.get_default_model", AsyncMock(return_value=None)):
            result = await AgentService.chat(AgentChatRequest(), self.user)
            self.assertEqual(result["finish_reason"], "model_unavailable")
        with patch("domain.agent.service.AIProviderService.get_default_model", AsyncMock(return_value=SimpleNamespace(provider=SimpleNamespace(api_format="gemini")))):
            with self.assertRaises(MissingModelError):
                await _choose_chat_ability()


if __name__ == "__main__":
    unittest.main()
