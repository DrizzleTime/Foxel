import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from domain.audit.service import AuditService
from domain.auth import User, get_current_active_user
from domain.permission.service import PermissionContext, PermissionService
from domain.tasks import TaskService
from domain.virtual_fs.api import router
from domain.virtual_fs.service import VirtualFSService


def path_rule(path, *, read=True, write=True, delete=True):
    return SimpleNamespace(path_pattern=path, is_regex=False, priority=0,
                           can_read=read, can_write=write, can_delete=delete,
                           can_share=True)


@pytest.fixture
def batch_fs(monkeypatch):
    # Use the real HTTP endpoints, authorization and VFS transfer methods, with
    # an in-memory adapter so the tests need no database or worker threads.
    files = {'src/a.txt': 'source a', 'src/b.txt': 'source b',
             'dst/a.txt': 'protected', 'dst/b.txt': 'old b'}

    class Adapter:
        async def exists(self, root, rel):
            return rel in files

        async def stat_path(self, root, rel):
            return {'exists': rel in files, 'is_dir': False, 'path': rel}

        async def delete(self, root, rel):
            del files[rel]

        async def copy(self, root, src, dst, overwrite=False):
            files[dst] = files[src]

        async def move(self, root, src, dst):
            files[dst] = files.pop(src)

    adapter = Adapter()
    record = SimpleNamespace(id=1)

    async def resolve(path):
        assert path.startswith('/disk/')
        return adapter, record, '', path.removeprefix('/disk/')

    monkeypatch.setattr(VirtualFSService, 'resolve_adapter_and_rel', resolve)
    monkeypatch.setattr(AuditService, 'log', AsyncMock())
    monkeypatch.setattr(TaskService, 'trigger_tasks', AsyncMock())
    monkeypatch.setattr(PermissionService, '_cache', {})
    monkeypatch.setattr(PermissionService, '_context_cache', {})

    def authorize(*rules):
        PermissionService.clear_cache()
        context = PermissionContext(exists=True, is_admin=False,
            path_rules=PermissionService._sort_path_rules([path_rule('/disk'), *rules]))
        PermissionService._context_cache[123] = (context, PermissionService._now())

    authorize()

    async def user():
        return User(id=123, username='batch-test')

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = user

    def post(path, body):
        async def request():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url='http://test') as client:
                return await client.post(path, json=body)
        return asyncio.run(request())

    return files, authorize, post


@pytest.mark.parametrize('operation', ['copy', 'move'])
def test_batch_checks_each_final_destination(batch_fs, operation):
    files, authorize, post = batch_fs
    authorize(path_rule('/disk/dst/a.txt', write=False))
    single = post(f'/api/fs/{operation}?overwrite=true',
                  {'src': '/disk/src/a.txt', 'dst': '/disk/dst/a.txt'})
    assert single.status_code == 403

    response = post(f'/api/fs/batch/{operation}?overwrite=true',
                    {'srcs': ['/disk/src/a.txt', '/disk/src/b.txt'], 'dst': '/disk/dst'})
    assert response.status_code == 200
    result = response.json()['data']
    assert (result['succeeded'], result['failed']) == (1, 1)
    assert result['results'][0]['ok'] is False
    assert result['results'][1]['ok'] is True
    assert files['dst/a.txt'] == 'protected'
    assert files['src/a.txt'] == 'source a'
    assert files['dst/b.txt'] == 'source b'


@pytest.mark.parametrize('operation', ['delete', 'copy', 'move'])
def test_denied_source_does_not_abort_other_items(batch_fs, operation):
    files, authorize, post = batch_fs
    authorize(path_rule('/disk/src/a.txt', read=False, delete=False))
    sources = ['/disk/src/a.txt', '/disk/src/b.txt']
    body = {'paths': sources} if operation == 'delete' else {'srcs': sources, 'dst': '/disk/new'}
    response = post(f'/api/fs/batch/{operation}', body)
    assert response.status_code == 200
    result = response.json()['data']
    assert (result['succeeded'], result['failed']) == (1, 1)
    assert files['src/a.txt'] == 'source a'
    if operation == 'copy':
        assert files['src/b.txt'] == 'source b'
    else:
        assert 'src/b.txt' not in files


@pytest.mark.parametrize('operation', ['copy', 'move'])
def test_single_batch_source_uses_destination_directory(batch_fs, operation):
    files, _, post = batch_fs
    response = post(f'/api/fs/batch/{operation}',
                    {'srcs': ['/disk/src/a.txt'], 'dst': '/disk/new'})
    assert response.json()['data']['succeeded'] == 1
    assert files['new/a.txt'] == 'source a'
    assert 'new/a.txt/a.txt' not in files


@pytest.mark.parametrize('operation', ['copy', 'move'])
@pytest.mark.parametrize('destination', ['/disk/src', '/disk/src/a.txt'])
def test_self_transfer_cannot_delete_or_nest_the_source(batch_fs, operation, destination):
    files, _, post = batch_fs
    before = dict(files)
    response = post(f'/api/fs/batch/{operation}?overwrite=true',
                    {'srcs': ['/disk/src/a.txt'], 'dst': destination})
    assert response.json()['data']['failed'] == 1
    assert files == before


@pytest.mark.parametrize('operation', ['copy', 'move'])
def test_root_destination_and_queued_result(monkeypatch, operation):
    monkeypatch.setattr(PermissionService, 'require_path_permission', AsyncMock())
    primitive = AsyncMock(return_value={'queued': True, 'task_id': 'queued-123'})
    monkeypatch.setattr(VirtualFSService, operation, primitive)
    method = getattr(VirtualFSService, f'batch_{operation}')
    result = asyncio.run(method(['/disk/a.txt'], '/', user_id=123))
    primitive.assert_awaited_once_with('/disk/a.txt', '/a.txt', False)
    assert result['results'][0] == {'src': '/disk/a.txt', 'dst': '/a.txt',
                                   'ok': True, 'queued': True, 'task_id': 'queued-123'}


def test_service_rejects_oversized_batch_instead_of_truncating(monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(VirtualFSService, 'delete', delete)
    with pytest.raises(ValidationError):
        asyncio.run(VirtualFSService.batch_delete(
            [f'/disk/{index}.txt' for index in range(201)], user_id=123))
    delete.assert_not_awaited()
