# Detailed Neo4j Schema & Index Scripts (v1)

**Version**: 1.0 (Aligned with approved Backend Design Scope v1)

## 1. Node Labels & Properties

### :Knowledge (Parent Document Level)
```cypher
(:Knowledge {
  id: string (UUID),
  source_file: string,
  total_tokens: integer,
  embedding_method: string,           // "LongText"
  created_at: datetime,
  experiment_id: string,
  vector: list<float>                 // dimension depends on model (e.g. 1024 for BGE-M3)
})
```

### :KnowledgeChunk (Child Level)
```cypher
(:KnowledgeChunk {
  id: string (UUID),
  parent_doc_id: string,
  chunk_index: integer,
  text: string,
  token_count: integer,
  chunk_method: string,               // "Recursive" | "Semantic" | "Structure-Aware"
  chunking_time_ms: float,
  embedding_time_ms: float,
  embedding_method: string,           // "ChildChunk"
  vector: list<float>
})
```

### :UserQuery
```cypher
(:UserQuery {
  id: string (UUID),
  text: string,
  total_tokens: integer,
  embedding_method: string,           // "LongText"
  created_at: datetime,
  experiment_id: string,
  vector: list<float>
})
```

### :UserQueryChunk
```cypher
(:UserQueryChunk {
  id: string (UUID),
  parent_query_id: string,
  chunk_index: integer,
  text: string,
  token_count: integer,
  chunk_method: string,
  embedding_time_ms: float,
  vector: list<float>
})
```

### :Memory
```cypher
(:Memory {
  id: string (UUID),
  user_query_id: string,
  timestamp: datetime,
  success_score: float | null,
  notes: string | null
})
```

### :MemoryCart
```cypher
(:MemoryCart {
  id: string (UUID),
  name: string,
  description: string | null,
  created_at: datetime,
  researcher_id: string | null          // for future multi-user
})
```

### :Experiment
```cypher
(:Experiment {
  id: string (UUID),
  description: string,
  embedding_approach: string,
  chunk_method: string,
  total_chunks: integer,
  avg_tokens_per_chunk: float,
  total_time_ms: float,
  source_file: string,
  created_at: datetime,
  status: string
})
```

## 2. Relationships

```cypher
// Parent-Child hierarchy
(:Knowledge)-[:HAS_CHUNK]->(:KnowledgeChunk)
(:UserQuery)-[:HAS_CHUNK]->(:UserQueryChunk)

// Retrieval memory links
(:UserQuery)-[:TRIGGERED]->(:Memory)-[:RETRIEVED]->(:KnowledgeChunk)

// Curation
(:MemoryCart)-[:CONTAINS]->(:Memory)
```

## 3. Constraints & Indexes (Creation Script)

```cypher
// Constraints (uniqueness)
CREATE CONSTRAINT knowledge_id IF NOT EXISTS FOR (k:Knowledge) REQUIRE k.id IS UNIQUE;
CREATE CONSTRAINT knowledgechunk_id IF NOT EXISTS FOR (c:KnowledgeChunk) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT userquery_id IF NOT EXISTS FOR (q:UserQuery) REQUIRE q.id IS UNIQUE;
CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT memorycart_id IF NOT EXISTS FOR (c:MemoryCart) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT experiment_id IF NOT EXISTS FOR (e:Experiment) REQUIRE e.id IS UNIQUE;

// Vector Indexes (HNSW, cosine)
CREATE VECTOR INDEX knowledge_vector IF NOT EXISTS
FOR (k:Knowledge) ON (k.vector)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,           // Adjust per model (BGE-M3 = 1024)
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_vector IF NOT EXISTS
FOR (c:KnowledgeChunk) ON (c.vector)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};

// Full-text index for BM25 (optional but recommended for v1)
CREATE FULLTEXT INDEX knowledge_text IF NOT EXISTS FOR (k:Knowledge) ON EACH [k.source_file];
CREATE FULLTEXT INDEX knowledgechunk_text IF NOT EXISTS FOR (c:KnowledgeChunk) ON EACH [c.text];
```

**Note**: Vector dimensions should be configurable via `core/config.py` based on the chosen embedding model.

## 4. Recommended Query Patterns (for reference)

- Get all chunks for an experiment with metadata
- Parent-level vector search + child expansion
- Memory cart retrieval with full context

These will be implemented in `db/neo4j_client.py`.