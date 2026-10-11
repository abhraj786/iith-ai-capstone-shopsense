"""Build the local M3 Qdrant policy index."""

from capstone.rag.policy_index import PolicyIndex


def main() -> None:
    index = PolicyIndex.local()
    count = index.build(recreate=True)
    print(f"Indexed {count} policy chunks into {index.collection_name}")


if __name__ == "__main__":
    main()
