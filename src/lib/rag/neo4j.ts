/**
 * Neo4j driver singleton (official JS driver). Used for:
 *   1. Optional direct read access from Next.js (e.g. Dashboard health, init verification).
 *   2. The /api/v1/neo4j/init + /api/v1/neo4j/health endpoints (run Cypher from
 *      neo4j-schema-v1.1.md + scripts/init_neo4j.py).
 *
 * The PRIMARY data path is via the FastAPI backend (backend-client.ts). This
 * driver is a secondary direct-access tool. In the sandbox (no Neo4j running),
 * connections fail gracefully — callers must handle the error.
 *
 * Mirrors db/neo4j_client.py from the FastAPI backend (same URI/user/password
 * env contract per infrastructure-environment-spec_v1.1.md §5).
 */

import neo4j, { type Driver, type Session } from "neo4j-driver";

const NEO4J_URI = process.env.NEO4J_URI || 
  (process.env.NODE_ENV === "production" ? "bolt://neo4j:7687" : "bolt://localhost:7687");
const NEO4J_USER = process.env.NEO4J_USER || "neo4j";
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD || "P@ssw0rd";

let _driver: Driver | null = null;
let _initError: string | null = null;

export function getNeo4jDriver(): Driver | null {
  if (_driver) return _driver;
  try {
    _driver = neo4j.driver(NEO4J_URI, neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD), {
      maxConnectionLifetime: 3 * 60 * 60 * 1000,
      maxConnectionPoolSize: 50,
      connectionAcquisitionTimeout: 10_000,
    });
    return _driver;
  } catch (err) {
    _initError = err instanceof Error ? err.message : String(err);
    return null;
  }
}

export function getNeo4jConfig() {
  return { uri: NEO4J_URI, user: NEO4J_USER, password: "***" };
}

export function getNeo4jInitError(): string | null {
  return _initError;
}

/** Verify connectivity. Returns true if Neo4j is reachable. */
export async function verifyNeo4jConnectivity(): Promise<{ ok: boolean; error?: string }> {
  const driver = getNeo4jDriver();
  if (!driver) return { ok: false, error: _initError || "driver init failed" };
  try {
    await driver.verifyConnectivity();
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/** Run a read query, return records as plain objects. */
export async function readQuery<T = Record<string, unknown>>(
  cypher: string,
  params: Record<string, unknown> = {},
): Promise<T[]> {
  const driver = getNeo4jDriver();
  if (!driver) throw new Error("Neo4j driver not initialized");
  const session: Session = driver.session({ defaultAccessMode: neo4j.session.READ });
  try {
    const result = await session.run(cypher, params);
    return result.records.map((r) => r.toObject() as T);
  } finally {
    await session.close();
  }
}

/** Run a write query. */
export async function writeQuery(
  cypher: string,
  params: Record<string, unknown> = {},
): Promise<void> {
  const driver = getNeo4jDriver();
  if (!driver) throw new Error("Neo4j driver not initialized");
  const session: Session = driver.session({ defaultAccessMode: neo4j.session.WRITE });
  try {
    await session.executeWrite(async (tx) => {
      await tx.run(cypher, params);
    });
  } finally {
    await session.close();
  }
}
