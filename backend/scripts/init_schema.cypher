// Hybrid Search v1.51 — Phase 1 schema (pre-phase DDL)
// Run via init_neo4j.py after connectivity check

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

CREATE CONSTRAINT memory_key_unique IF NOT EXISTS
FOR (m:Memory) REQUIRE m.memory_key IS UNIQUE;
