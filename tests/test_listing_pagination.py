import unittest

from api.response import cursor_page, dir_listing, listing_pagination, page


class ListingPaginationTests(unittest.TestCase):
    def test_paged_result_keeps_totals(self):
        result = page([{"name": "a"}], total=120, page=2, page_size=50)
        items, pagination = listing_pagination(result, page_num=2, page_size=50)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            pagination,
            {
                "mode": "paged",
                "page_size": 50,
                "total": 120,
                "page": 2,
                "pages": 3,
            },
        )

    def test_cursor_result_keeps_cursors(self):
        result = cursor_page(
            [{"name": "tg"}],
            page_size=50,
            cursor="10",
            next_cursor="20",
        )
        items, pagination = listing_pagination(result, page_num=2, page_size=50, cursor="10")
        self.assertEqual(items, [{"name": "tg"}])
        self.assertEqual(
            pagination,
            {
                "mode": "cursor",
                "page_size": 50,
                "cursor": "10",
                "next_cursor": "20",
                "has_next": True,
            },
        )
        self.assertNotIn("total", pagination)
        self.assertNotIn("page", pagination)

    def test_missing_total_does_not_fake_page_count(self):
        items, pagination = listing_pagination(
            {"items": [{"name": "a"}] * 50, "page_size": 50},
            page_num=1,
            page_size=50,
        )
        self.assertEqual(len(items), 50)
        self.assertEqual(pagination["mode"], "paged")
        self.assertEqual(pagination["total"], 0)
        self.assertEqual(pagination["pages"], 0)

    def test_dir_listing_wraps_path_and_entries(self):
        result = page([{"name": "a"}], total=1, page=1, page_size=50)
        payload = dir_listing(result, path="/share/docs", page_num=1, page_size=50)
        self.assertEqual(payload["path"], "/share/docs")
        self.assertEqual(payload["entries"], [{"name": "a"}])
        self.assertEqual(payload["pagination"]["mode"], "paged")
        self.assertEqual(payload["pagination"]["total"], 1)

    def test_non_dict_result_is_empty_paged(self):
        items, pagination = listing_pagination(None, page_num=3, page_size=20)
        self.assertEqual(items, [])
        self.assertEqual(pagination["mode"], "paged")
        self.assertEqual(pagination["total"], 0)
        self.assertEqual(pagination["page"], 3)
        self.assertEqual(pagination["page_size"], 20)


if __name__ == "__main__":
    unittest.main()
