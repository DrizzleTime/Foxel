import unittest
import warnings

from qdrant_client import QdrantClient

from domain.ai.vector_providers.qdrant import QdrantProvider


class QdrantProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = QdrantProvider()
        self.provider.client = QdrantClient(":memory:")
        self.addCleanup(self.provider.client.close)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Payload indexes have no effect")
            self.provider.ensure_collection("files", vector=True, dim=4)

    def test_vector_search_preserves_payload_and_ranking(self):
        self.provider.upsert_vector(
            "files", {"path": "/match.txt", "embedding": [1.0, 0.0, 0.0, 0.0], "text": "match"}
        )
        self.provider.upsert_vector(
            "files", {"path": "/other.txt", "embedding": [0.0, 1.0, 0.0, 0.0], "text": "other"}
        )

        results = self.provider.search_vectors("files", [1.0, 0.0, 0.0, 0.0], top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]), 1)
        hit = results[0][0]
        self.assertEqual(hit["id"], self.provider._point_id("/match.txt"))
        self.assertAlmostEqual(hit["distance"], 1.0)
        self.assertEqual(hit["entity"]["path"], "/match.txt")
        self.assertEqual(hit["entity"]["text"], "match")

    def test_deleted_vector_is_absent_from_search(self):
        self.provider.upsert_vector(
            "files", {"path": "/deleted.txt", "embedding": [1.0, 0.0, 0.0, 0.0]}
        )
        self.provider.delete_vector("files", "/deleted.txt")

        self.assertEqual(
            self.provider.search_vectors("files", [1.0, 0.0, 0.0, 0.0], top_k=1), [[]]
        )
