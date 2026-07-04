/**
 * POST /api/v1/neo4j/init — initialize Neo4j schema (constraints + vector
 * indexes + fulltext indexes) per neo4j-schema-v1.1.md. Idempotent (IF NOT EXISTS).
 *
 * This is the JS-side mirror of backend/scripts/init_neo4j.py. Either can run
 * the initiation; the Python script is the canonical one for Docker setup.
 */
import { NextResponse } from "next/server";
import { writeQuery, readQuery, verifyNeo4jConnectivity } from "@/lib/rag/neo4j";
import { withErrors } from "@/lib/rag/api-helpers";
import { EMBEDDING_DIM } from "@/lib/rag/constants";

// All Cypher from neo4j-schema-v1.1.md §3 (constraints + vector + fulltext).
const CONSTRAINTS = [
  "CREATE CONSTRAINT knowledge_id IF NOT EXISTS FOR (k:Knowledge) REQUIRE k.id IS UNIQUE",
  "CREATE CONSTRAINT knowledgechunk_id IF NOT EXISTS FOR (c:KnowledgeChunk) REQUIRE c.id IS UNIQUE",
  "CREATE CONSTRAINT userquery_id IF NOT EXISTS FOR (q:UserQuery) REQUIRE q.id IS UNIQUE",
  "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
  "CREATE CONSTRAINT memorycart_id IF NOT EXISTS FOR (c:MemoryCart) REQUIRE c.id IS UNIQUE",
  "CREATE CONSTRAINT experiment_id IF NOT EXISTS FOR (e:Experiment) REQUIRE e.id IS UNIQUE",
];

const VECTOR_INDEXES = [
  `CREATE VECTOR INDEX knowledge_vector IF NOT EXISTS
   FOR (k:Knowledge) ON (k.vector)
   OPTIONS {indexConfig: {
     \`vector.dimensions\`: ${EMBEDDING_DIM},
     \`vector.similarity_function\`: 'cosine'
   }}`,
  `CREATE VECTOR INDEX knowledgechunk_vector IF NOT EXISTS
   FOR (c:KnowledgeChunk) ON (c.vector)
   OPTIONS {indexConfig: {
     \`vector.dimensions\`: ${EMBEDDING_DIM},
     \`vector.similarity_function\`: 'cosine'
   }}`,
];

const FULLTEXT_INDEXES = [
  "CREATE FULLTEXT INDEX knowledge_text IF NOT EXISTS FOR (k:Knowledge) ON EACH [k.source_file, k.text]",
  "CREATE FULLTEXT INDEX knowledgechunk_text IF NOT EXISTS FOR (c:KnowledgeChunk) ON EACH [c.text]",
];

export async function POST() {
  return withErrors(async (): Promise<NextResponse> => {
    const conn = await verifyNeo4jConnectivity();
    if (!conn.ok) {
      return NextResponse.json(
        {
          error: {
            code: "NEO4J_UNAVAILABLE",
            message: `Cannot connect to Neo4j: ${conn.error}. Start Neo4j (docker compose up neo4j) and set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD.`,
          },
        },
        { status: 503 },
      );
    }
    const applied: string[] = [];
    const errors: { step: string; error: string }[] = [];
    for (const cypher of CONSTRAINTS) {
      try {
        await writeQuery(cypher);
        applied.push(cypher.slice(0, 60) + "…");
      } catch (e) {
        errors.push({ step: "constraint", error: e instanceof Error ? e.message : String(e) });
      }
    }
    for (const cypher of VECTOR_INDEXES) {
      try {
        await writeQuery(cypher);
        applied.push("vector index: " + cypher.match(/INDEX (\w+)/)?.[1]);
      } catch (e) {
        errors.push({ step: "vector_index", error: e instanceof Error ? e.message : String(e) });
      }
    }
    for (const cypher of FULLTEXT_INDEXES) {
      try {
        await writeQuery(cypher);
        applied.push("fulltext: " + cypher.match(/INDEX (\w+)/)?.[1]);
      } catch (e) {
        errors.push({ step: "fulltext", error: e instanceof Error ? e.message : String(e) });
      }
    }
    // Verify indexes exist
    const indexes = await readQuery<{ name: string; type: string }>(
      "SHOW INDEXES YIELD name, type RETURN name, type",
    );
    return NextResponse.json({
      applied,
      errors,
      embeddingDim: EMBEDDING_DIM,
      indexes: indexes.map((i) => ({ name: i.name, type: i.type })),
    });
  });
}
