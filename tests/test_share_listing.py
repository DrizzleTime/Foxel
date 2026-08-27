import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.response import cursor_page, page
from domain.share.service import ShareService


class ShareSingleFileListingTests(unittest.TestCase):
    def test_first_page_returns_file(self):
        stat = {"name": "notes.md", "is_dir": False, "size": 12}
        result = ShareService._single_file_listing(stat, 1, 50)
        self.assertEqual(result["items"], [stat])
        self.assertEqual(result["pagination"]["mode"], "paged")
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["pagination"]["page"], 1)
        self.assertEqual(result["pagination"]["pages"], 1)

    def test_later_page_is_empty(self):
        stat = {"name": "notes.md", "is_dir": False}
        result = ShareService._single_file_listing(stat, 2, 50)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["pagination"]["page"], 2)
        self.assertEqual(result["pagination"]["pages"], 1)


class ShareDirectoryListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_directory_maps_offset_pagination(self):
        share = SimpleNamespace(paths=["/photos"])
        listing = page([{"name": "a.jpg"}, {"name": "b.jpg"}], total=90, page=2, page_size=20)
        with patch.object(ShareService, "_list_shared_virtual_dir", new_callable=AsyncMock) as listed:
            with patch("domain.share.service.VirtualFSService.stat_file", new_callable=AsyncMock) as stat_file:
                stat_file.return_value = {"is_dir": True, "name": "photos"}
                listed.return_value = {"items": listing["items"], "pagination": {"mode": "paged", "total": 90}}
                result = await ShareService.get_shared_item_details(
                    share, "/", page_num=2, page_size=20
                )
        listed.assert_awaited_once_with("/photos", 2, 20, None)
        self.assertEqual(result["pagination"]["total"], 90)

    async def test_directory_passes_cursor_to_vfs(self):
        share = SimpleNamespace(paths=["/tg"])
        vfs_result = cursor_page(
            [{"name": "1_clip.mp4"}],
            page_size=50,
            cursor="10",
            next_cursor="20",
        )
        with patch("domain.share.service.VirtualFSService.stat_file", new_callable=AsyncMock) as stat_file:
            with patch(
                "domain.share.service.VirtualFSService.list_virtual_dir",
                new_callable=AsyncMock,
            ) as list_dir:
                stat_file.return_value = {"is_dir": True, "name": "tg"}
                list_dir.return_value = vfs_result
                result = await ShareService.get_shared_item_details(
                    share, "/", page_num=1, page_size=50, cursor="10"
                )
        list_dir.assert_awaited_once_with("/tg", 1, 50, cursor="10")
        self.assertEqual(result["items"], [{"name": "1_clip.mp4"}])
        self.assertEqual(result["pagination"]["mode"], "cursor")
        self.assertEqual(result["pagination"]["next_cursor"], "20")
        self.assertTrue(result["pagination"]["has_next"])
        self.assertNotIn("total", result["pagination"])

    async def test_missing_directory_http_404_is_normalized(self):
        share = SimpleNamespace(paths=["/photos"])
        with patch(
            "domain.share.service.VirtualFSService.list_virtual_dir",
            new_callable=AsyncMock,
        ) as list_dir:
            list_dir.side_effect = HTTPException(status_code=404, detail="Path not found")
            with self.assertRaises(HTTPException) as ctx:
                await ShareService.get_shared_item_details(share, "/missing")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "目录未找到")

    async def test_empty_share_is_404(self):
        share = SimpleNamespace(paths=[])
        with self.assertRaises(HTTPException) as ctx:
            await ShareService.get_shared_item_details(share)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
