"""M3 policy index tests."""

from qdrant_client import QdrantClient

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
