"""Unit tests run offline: force the deterministic hash embeddings and skip the ONNX reranker."""

import os

os.environ["CAPSTONE_EMBEDDINGS"] = "hash"
os.environ["CAPSTONE_RERANK"] = "off"
