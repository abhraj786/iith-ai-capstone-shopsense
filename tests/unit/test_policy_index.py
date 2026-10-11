"""M3 policy index tests."""

from qdrant_client import QdrantClient

import capstone.rag.policy_index as policy_index_module
from capstone.rag.policy_index import PolicyIndex
from capstone.settings import PROJECT_ROOT


def test_policy_index_builds_qdrant_collection_and_retrieves_refund_policy():
    index = PolicyIndex(
        QdrantClient(":memory:"),
        PROJECT_ROOT / "data" / "shopsense",
    )
    count = index.build()
    hits = index.search("automated assistant refund above 2000 rupees legal escalation", limit=3)

    assert count > 10
    assert hits
    assert any("refund" in hit.title.lower() or "escalation" in hit.title.lower() for hit in hits)
    assert all(hit.document_slug and hit.text for hit in hits)


def test_policy_index_from_settings_uses_cloud_when_available(monkeypatch):
    class FakeQdrantClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_collections(self):
            return []

    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("QDRANT_API_KEY", "secret")
    monkeypatch.setattr(policy_index_module, "QdrantClient", FakeQdrantClient)

    index = PolicyIndex.from_settings()

    assert index.storage_label == "cloud"
    assert index.client.kwargs["url"] == "https://qdrant.example"


def test_policy_index_from_settings_falls_back_to_local_when_cloud_unavailable(monkeypatch, tmp_path):
    class FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def get_collections(self):
            raise TimeoutError("network unavailable")

    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("QDRANT_API_KEY", "secret")
    monkeypatch.setattr(policy_index_module, "QdrantClient", FakeQdrantClient)

    index = PolicyIndex.from_settings(index_dir=tmp_path)

    assert index.storage_label == "local"
    assert index.client.kwargs["path"] == str(tmp_path)
