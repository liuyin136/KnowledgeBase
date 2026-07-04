/**
 * Store — thin data-access layer over Prisma (replaces db/neo4j_client.py).
 * Provides typed CRUD + vector search helpers for all graph nodes:
 *   Knowledge, KnowledgeChunk, UserQuery, UserQueryChunk, Memory, MemoryCart,
 *   Experiment, SearchRun, Document, Job.
 *
 * Vector storage: SQLite has no native vector type; vectors are JSON-encoded
 * number[] on each node. In-memory cosine (./vectors.ts) is used for retrieval
 * (v1 research-scale corpus — adequate for the experimentation platform).
 */

import { db } from "@/lib/db";
import { cosine } from "./vectors";

const parseVec = (s: string | null | undefined): number[] =>
  s ? (JSON.parse(s) as number[]) : [];

const stringifyVec = (v: number[]): string => JSON.stringify(v);

// ─── Experiment ─────────────────────────────────────────────────────────────

export async function createExperiment(opts: {
  description: string;
  embeddingApproach: string;
  chunkMethod: string;
  sourceFile?: string;
  kind?: "ingest" | "search";
}): Promise<string> {
  const exp = await db.experiment.create({
    data: {
      description: opts.description,
      embeddingApproach: opts.embeddingApproach,
      chunkMethod: opts.chunkMethod,
      sourceFile: opts.sourceFile ?? null,
      status: "pending",
    },
  });
  return exp.id;
}

export async function updateExperimentStatus(
  id: string,
  status: "pending" | "running" | "completed" | "failed",
  extra?: {
    totalChunks?: number;
    avgTokensPerChunk?: number;
    totalTimeMs?: number;
    errorCode?: string;
    errorMessage?: string;
  },
): Promise<void> {
  await db.experiment.update({ where: { id }, data: { status, ...extra } });
}

export async function getExperiment(id: string) {
  return db.experiment.findUnique({ where: { id } });
}

export async function listExperiments(opts: {
  page: number;
  pageSize: number;
  kind?: "ingest" | "search";
}) {
  const where = opts.kind
    ? opts.kind === "ingest"
      ? { embeddingApproach: { in: ["LongText", "ChildChunk"] } }
      : { embeddingApproach: "Query" }
    : {};
  const [items, total] = await Promise.all([
    db.experiment.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (opts.page - 1) * opts.pageSize,
      take: opts.pageSize,
    }),
    db.experiment.count({ where }),
  ]);
  return { items, total };
}

// ─── Knowledge (parent) ─────────────────────────────────────────────────────

export async function createKnowledge(opts: {
  experimentId: string;
  sourceFile: string;
  text: string;
  totalTokens: number;
  vector: number[];
  embeddingTimeMs: number;
}): Promise<string> {
  const k = await db.knowledge.create({
    data: {
      experimentId: opts.experimentId,
      sourceFile: opts.sourceFile,
      text: opts.text,
      totalTokens: opts.totalTokens,
      embeddingMethod: "LongText",
      vector: stringifyVec(opts.vector),
      embeddingTimeMs: opts.embeddingTimeMs,
    },
  });
  return k.id;
}

export async function getKnowledge(id: string) {
  const k = await db.knowledge.findUnique({ where: { id } });
  if (!k) return null;
  return { ...k, vector: parseVec(k.vector) };
}

export async function listKnowledgeForExperiment(experimentId: string) {
  const items = await db.knowledge.findMany({ where: { experimentId } });
  return items.map((k) => ({ ...k, vector: parseVec(k.vector) }));
}

// ─── KnowledgeChunk (child) ─────────────────────────────────────────────────

export async function createChunk(opts: {
  experimentId: string;
  parentId: string;
  chunkIndex: number;
  text: string;
  tokenCount: number;
  chunkMethod: string;
  chunkingTimeMs: number;
  embeddingMethod: string;
  embeddingTimeMs: number;
  vector: number[];
  charStart?: number;
  charEnd?: number;
  section?: string;
}): Promise<string> {
  const c = await db.knowledgeChunk.create({
    data: {
      experimentId: opts.experimentId,
      parentId: opts.parentId,
      chunkIndex: opts.chunkIndex,
      text: opts.text,
      tokenCount: opts.tokenCount,
      chunkMethod: opts.chunkMethod,
      chunkingTimeMs: opts.chunkingTimeMs,
      embeddingMethod: opts.embeddingMethod,
      embeddingTimeMs: opts.embeddingTimeMs,
      vector: stringifyVec(opts.vector),
      charStart: opts.charStart ?? null,
      charEnd: opts.charEnd ?? null,
      section: opts.section ?? null,
    },
  });
  return c.id;
}

export async function listChunksForExperiment(experimentId: string) {
  return db.knowledgeChunk.findMany({
    where: { experimentId },
    orderBy: { chunkIndex: "asc" },
  });
}

export async function listChunksForParent(parentId: string) {
  return db.knowledgeChunk.findMany({
    where: { parentId },
    orderBy: { chunkIndex: "asc" },
  });
}

export async function getChunkWithParent(chunkId: string) {
  const chunk = await db.knowledgeChunk.findUnique({
    where: { id: chunkId },
    include: { parent: true },
  });
  if (!chunk) return null;
  return { ...chunk, vector: parseVec(chunk.vector) };
}

// ─── Vector search (parent-level) ───────────────────────────────────────────

export async function vectorSearchParents(opts: {
  experimentId?: string;
  queryVector: number[];
  topK: number;
}): Promise<{ id: string; parentId: string; score: number; chunkIndex: number; text: string; tokenCount: number; chunkMethod: string; embeddingMethod: string; section: string | null; chunkingTimeMs: number; embeddingTimeMs: number; experimentId: string; parentSourceFile: string; parentText: string }[]> {
  // For ChildChunk experiments, search at child level (each child has its own vector).
  // For LongText experiments, the only "chunk" is the parent itself (1:1).
  // We search across ALL chunks of the experiment (child-level retrieval) which
  // covers both cases — LongText produces a single chunk whose parent text == chunk text.
  const where = opts.experimentId ? { experimentId: opts.experimentId } : {};
  const chunks = await db.knowledgeChunk.findMany({
    where,
    include: { parent: true },
  });
  const scored = chunks.map((c) => {
    const v = parseVec(c.vector);
    return {
      id: c.id,
      parentId: c.parentId,
      score: cosine(opts.queryVector, v),
      chunkIndex: c.chunkIndex,
      text: c.text,
      tokenCount: c.tokenCount,
      chunkMethod: c.chunkMethod,
      embeddingMethod: c.embeddingMethod,
      section: c.section,
      chunkingTimeMs: c.chunkingTimeMs,
      embeddingTimeMs: c.embeddingTimeMs,
      experimentId: c.experimentId,
      parentSourceFile: c.parent.sourceFile,
      parentText: c.parent.text,
      charStart: c.charStart,
      charEnd: c.charEnd,
    };
  });
  return scored.sort((a, b) => b.score - a.score).slice(0, opts.topK);
}

// ─── UserQuery ──────────────────────────────────────────────────────────────

export async function createUserQuery(opts: {
  experimentId?: string | null;
  text: string;
  totalTokens: number;
  vector: number[];
  embeddingTimeMs: number;
}): Promise<string> {
  const q = await db.userQuery.create({
    data: {
      experimentId: opts.experimentId ?? null,
      text: opts.text,
      totalTokens: opts.totalTokens,
      embeddingMethod: "LongText",
      vector: stringifyVec(opts.vector),
      embeddingTimeMs: opts.embeddingTimeMs,
    },
  });
  return q.id;
}

// ─── Memory + MemoryCart ────────────────────────────────────────────────────

export async function createMemory(opts: {
  userQueryId: string;
  experimentId?: string | null;
  chunkId?: string | null;
  queryText: string;
  chunkText?: string | null;
  vectorScore?: number | null;
  bm25Score?: number | null;
  fusedScore?: number | null;
  rerankerScore?: number | null;
  score?: number | null;
  notes?: string | null;
}): Promise<string> {
  const m = await db.memory.create({
    data: {
      userQueryId: opts.userQueryId,
      experimentId: opts.experimentId ?? null,
      chunkId: opts.chunkId ?? null,
      queryText: opts.queryText,
      chunkText: opts.chunkText ?? null,
      vectorScore: opts.vectorScore ?? null,
      bm25Score: opts.bm25Score ?? null,
      fusedScore: opts.fusedScore ?? null,
      rerankerScore: opts.rerankerScore ?? null,
      score: opts.score ?? null,
      notes: opts.notes ?? null,
    },
  });
  return m.id;
}

export async function listMemories(opts: { experimentId?: string; page: number; pageSize: number }) {
  const where = opts.experimentId ? { experimentId: opts.experimentId } : {};
  const [items, total] = await Promise.all([
    db.memory.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (opts.page - 1) * opts.pageSize,
      take: opts.pageSize,
    }),
    db.memory.count({ where }),
  ]);
  // Denormalize `selected` flag based on cart membership.
  const carts = await db.memoryCart.findMany({ include: { memories: { select: { id: true } } } });
  const inCart = new Set<string>();
  for (const c of carts) for (const m of c.memories) inCart.add(m.id);
  return {
    items: items.map((m) => ({ ...m, selected: inCart.has(m.id) })),
    total,
  };
}

export async function createMemoryCart(opts: { name: string; description?: string }): Promise<string> {
  const c = await db.memoryCart.create({
    data: { name: opts.name, description: opts.description ?? null },
  });
  return c.id;
}

export async function listMemoryCarts() {
  const carts = await db.memoryCart.findMany({
    orderBy: { updatedAt: "desc" },
    include: { _count: { select: { memories: true } } },
  });
  return carts.map((c) => ({
    id: c.id,
    name: c.name,
    description: c.description,
    memoryCount: c._count.memories,
    createdAt: c.createdAt.toISOString(),
    updatedAt: c.updatedAt.toISOString(),
  }));
}

export async function getMemoryCart(id: string) {
  const cart = await db.memoryCart.findUnique({
    where: { id },
    include: { memories: true },
  });
  if (!cart) return null;
  return {
    id: cart.id,
    name: cart.name,
    description: cart.description,
    memories: cart.memories.map((m) => ({ ...m, selected: true })),
    createdAt: cart.createdAt.toISOString(),
    updatedAt: cart.updatedAt.toISOString(),
  };
}

export async function setCartMemorySelection(cartId: string, memoryIds: string[]): Promise<void> {
  // Replace all associations.
  await db.$transaction([
    db.memoryCart.update({ where: { id: cartId }, data: { memories: { set: [] } } }),
    db.memoryCart.update({
      where: { id: cartId },
      data: { memories: { connect: memoryIds.map((id) => ({ id })) } },
    }),
  ]);
}

export async function addMemoriesToCart(cartId: string, memoryIds: string[]): Promise<void> {
  await db.memoryCart.update({
    where: { id: cartId },
    data: { memories: { connect: memoryIds.map((id) => ({ id })) } },
  });
}

// ─── SearchRun history ──────────────────────────────────────────────────────

export async function createSearchRun(opts: {
  experimentId?: string | null;
  rawQuery: string;
  config: {
    hybridAlpha: number;
    useBm25: boolean;
    useReranker: boolean;
    topKVector: number;
    topNRerank: number;
    parentContextLevels: number;
    autoTuneWeights: boolean;
  };
  bestAlpha?: number | null;
  resultCount: number;
  topScore?: number | null;
  searchTimeMs: number;
}): Promise<string> {
  const sr = await db.searchRun.create({
    data: {
      experimentId: opts.experimentId ?? null,
      rawQuery: opts.rawQuery,
      hybridAlpha: opts.config.hybridAlpha,
      useBm25: opts.config.useBm25,
      useReranker: opts.config.useReranker,
      topKVector: opts.config.topKVector,
      topNRerank: opts.config.topNRerank,
      parentContextLevels: opts.config.parentContextLevels,
      autoTuneWeights: opts.config.autoTuneWeights,
      bestAlpha: opts.bestAlpha ?? null,
      resultCount: opts.resultCount,
      topScore: opts.topScore ?? null,
      searchTimeMs: opts.searchTimeMs,
    },
  });
  return sr.id;
}

export async function listSearchRuns(opts: { page: number; pageSize: number; experimentId?: string }) {
  const where = opts.experimentId ? { experimentId: opts.experimentId } : {};
  const [items, total] = await Promise.all([
    db.searchRun.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip: (opts.page - 1) * opts.pageSize,
      take: opts.pageSize,
    }),
    db.searchRun.count({ where }),
  ]);
  return { items, total };
}

// ─── Documents ──────────────────────────────────────────────────────────────

export async function createDocument(opts: {
  filename: string;
  contentType: string;
  size: number;
  text: string;
}): Promise<string> {
  const d = await db.document.create({
    data: {
      filename: opts.filename,
      contentType: opts.contentType,
      size: opts.size,
      text: opts.text,
    },
  });
  return d.id;
}

export async function listDocuments(opts: { page: number; pageSize: number }) {
  const [items, total] = await Promise.all([
    db.document.findMany({
      orderBy: { createdAt: "desc" },
      skip: (opts.page - 1) * opts.pageSize,
      take: opts.pageSize,
      select: {
        id: true,
        filename: true,
        contentType: true,
        size: true,
        createdAt: true,
      },
    }),
    db.document.count(),
  ]);
  return { items, total };
}

export async function getDocument(id: string) {
  return db.document.findUnique({ where: { id } });
}

export async function deleteDocument(id: string): Promise<void> {
  await db.document.delete({ where: { id } });
}
