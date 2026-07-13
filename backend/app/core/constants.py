NEO4J_MAX_RETRIES = 2
ALLOWED_COARSE_DIMS_V1 = (256, 512)
DEFAULT_COARSE_DIM = 256
EMBEDDING_FULL_DIM = 1024
CHUNK_TOKEN_MAX = 29500
OVERLAP_TOKENS = 2950
STRIDE_TOKENS = 26550
METRICS_LIST_KEY = "metrics:pipeline"
METRICS_LIST_MAX = 10_000

COARSE_INDEX_NAMES = {
    256: "knowledgechunk_vector_coarse_256",
    512: "knowledgechunk_vector_coarse_512",
}

CHILD_COARSE_INDEX_NAMES = {
    256: "knowledgechunk_sen_vector_coarse_256",
    512: "knowledgechunk_sen_vector_coarse_512",
}

# Phase 1.62 — 4-tier vector indexes
FAMILY_COARSE_INDEX_NAMES = {
    256: "knowledgechunk_family_vector_coarse_256",
    512: "knowledgechunk_family_vector_coarse_512",
}

PARENT_COARSE_INDEX_NAMES = {
    256: "knowledgechunk_parent_vector_coarse_256",
    512: "knowledgechunk_parent_vector_coarse_512",
}

GRANDCHILD_COARSE_INDEX_NAMES = {
    256: "knowledgechunk_grand_vector_coarse_256",
    512: "knowledgechunk_grand_vector_coarse_512",
}

# Cascade recall K (W1–W5)
TIER_RECALL_K = {
    "family": 128,
    "parent": 64,
    "child": 32,
    "grandchild": 16,
    "rerank": 8,
}

# Hierarchical vector-tier weights (W1 highest → W5 lowest); sum ≈ 1.0
TIER_WEIGHTS = {
    "family": 0.35,
    "parent": 0.25,
    "child": 0.20,
    "grandchild": 0.12,
    "rerank": 0.08,
}

GRANDCHILD_RERANK_TOKEN_LIMIT = 8192
SEARCH_CACHE_VERSION = "v162"
