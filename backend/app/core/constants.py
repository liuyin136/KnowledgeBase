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

GRANDCHILD_RERANK_TOKEN_LIMIT = 8192
SEARCH_CACHE_VERSION = "v16"
