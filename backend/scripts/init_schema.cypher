// Hybrid Search v1.62 — 4-tier hierarchical schema
// Run via init_neo4j.py after connectivity check

// Legacy flat chunks (kept for purge/compat during migration)
CREATE VECTOR INDEX knowledgechunk_vector_coarse_256 IF NOT EXISTS
FOR (c:KnowledgeChunk) ON (c.vector_coarse_256)
OPTIONS {indexConfig: {
  `vector.dimensions`: 256,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_vector_coarse_512 IF NOT EXISTS
FOR (c:KnowledgeChunk) ON (c.vector_coarse_512)
OPTIONS {indexConfig: {
  `vector.dimensions`: 512,
  `vector.similarity_function`: 'cosine'
}};

CREATE FULLTEXT INDEX knowledgechunk_text IF NOT EXISTS
FOR (c:KnowledgeChunk) ON EACH [c.content];

// Family tier
CREATE VECTOR INDEX knowledgechunk_family_vector_coarse_256 IF NOT EXISTS
FOR (c:Knowledgechunk_family) ON (c.vector_coarse_256)
OPTIONS {indexConfig: {
  `vector.dimensions`: 256,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_family_vector_coarse_512 IF NOT EXISTS
FOR (c:Knowledgechunk_family) ON (c.vector_coarse_512)
OPTIONS {indexConfig: {
  `vector.dimensions`: 512,
  `vector.similarity_function`: 'cosine'
}};

CREATE FULLTEXT INDEX knowledgechunk_family_text IF NOT EXISTS
FOR (c:Knowledgechunk_family) ON EACH [c.content];

// Parent tier (:Knowledgechunk)
CREATE VECTOR INDEX knowledgechunk_parent_vector_coarse_256 IF NOT EXISTS
FOR (c:Knowledgechunk) ON (c.vector_coarse_256)
OPTIONS {indexConfig: {
  `vector.dimensions`: 256,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_parent_vector_coarse_512 IF NOT EXISTS
FOR (c:Knowledgechunk) ON (c.vector_coarse_512)
OPTIONS {indexConfig: {
  `vector.dimensions`: 512,
  `vector.similarity_function`: 'cosine'
}};

CREATE FULLTEXT INDEX knowledgechunk_parent_text IF NOT EXISTS
FOR (c:Knowledgechunk) ON EACH [c.content];

// Child tier (:Knowledgechunk_sen)
CREATE VECTOR INDEX knowledgechunk_sen_vector_coarse_256 IF NOT EXISTS
FOR (c:Knowledgechunk_sen) ON (c.vector_coarse_256)
OPTIONS {indexConfig: {
  `vector.dimensions`: 256,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_sen_vector_coarse_512 IF NOT EXISTS
FOR (c:Knowledgechunk_sen) ON (c.vector_coarse_512)
OPTIONS {indexConfig: {
  `vector.dimensions`: 512,
  `vector.similarity_function`: 'cosine'
}};

CREATE FULLTEXT INDEX knowledgechunk_sen_text IF NOT EXISTS
FOR (c:Knowledgechunk_sen) ON EACH [c.content];

// Grandchild tier
CREATE VECTOR INDEX knowledgechunk_grand_vector_coarse_256 IF NOT EXISTS
FOR (c:Knowledgechunk_grand) ON (c.vector_coarse_256)
OPTIONS {indexConfig: {
  `vector.dimensions`: 256,
  `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX knowledgechunk_grand_vector_coarse_512 IF NOT EXISTS
FOR (c:Knowledgechunk_grand) ON (c.vector_coarse_512)
OPTIONS {indexConfig: {
  `vector.dimensions`: 512,
  `vector.similarity_function`: 'cosine'
}};

CREATE FULLTEXT INDEX knowledgechunk_grand_text IF NOT EXISTS
FOR (c:Knowledgechunk_grand) ON EACH [c.content];

CREATE CONSTRAINT memory_key_unique IF NOT EXISTS
FOR (m:Memory) REQUIRE m.memory_key IS UNIQUE;

// Phase 2 — GraphRAG memory subgraph (scoped by memory_key)
CREATE CONSTRAINT entity_batch_key IF NOT EXISTS
FOR (e:Entity) REQUIRE (e.memory_key, e.entity_id) IS NODE KEY;

CREATE CONSTRAINT claim_batch_key IF NOT EXISTS
FOR (c:Claim) REQUIRE (c.memory_key, c.claim_id) IS NODE KEY;

CREATE CONSTRAINT community_batch_key IF NOT EXISTS
FOR (c:Community) REQUIRE (c.memory_key, c.community_id) IS NODE KEY;

CREATE CONSTRAINT community_summary_batch_key IF NOT EXISTS
FOR (s:CommunitySummary) REQUIRE (s.memory_key, s.summary_id) IS NODE KEY;

CREATE FULLTEXT INDEX community_summary_text IF NOT EXISTS
FOR (s:CommunitySummary) ON EACH [s.text];
