"""Build the configured M3/M4 Qdrant policy index."""

from capstone.rag.policy_index import PolicyIndex


def main() -> None:
    index = PolicyIndex.from_settings()
    count = index.build(recreate=True)
    print(f"Indexed {count} policy chunks into {index.collection_name} ({index.storage_label} Qdrant)")


if __name__ == "__main__":
    main()
