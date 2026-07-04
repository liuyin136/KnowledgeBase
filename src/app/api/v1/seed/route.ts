/**
 * POST /api/v1/seed — seed sample documents for researcher experimentation.
 * Idempotent: checks filename first.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors } from "@/lib/rag/api-helpers";
import { db } from "@/lib/db";

const SAMPLE_DOCS: { filename: string; contentType: string; text: string }[] = [
  {
    filename: "rag-overview.md",
    contentType: "text/markdown",
    text: `# Retrieval-Augmented Generation: An Overview

## Introduction
Retrieval-Augmented Generation (RAG) combines a retriever with a generative language model. The retriever fetches relevant passages from a knowledge base, and the generator conditions on those passages to produce an answer. RAG reduces hallucination by grounding the model in retrieved evidence.

## Core Components
A RAG system has three core components: an embedding model that converts text into dense vectors, a vector store that supports similarity search, and a generator that produces the final answer. The quality of retrieval depends heavily on how documents are chunked and embedded.

## Chunking Strategies
Chunking breaks long documents into smaller units. The recursive character splitter divides text by structural separators. The semantic splitter groups adjacent sentences with high lexical overlap. The structure-aware splitter respects markdown headings and sections.

## Parent-Child Hierarchy
A parent-child hierarchy stores both the full document (parent) and its chunks (children). Retrieval can match at the child level for precision and expand to the parent for context. This is the foundation for meaningful retrieval experimentation.

## Hybrid Search
Hybrid search combines dense vector retrieval with sparse lexical retrieval such as BM25. Reciprocal Rank Fusion (RRF) merges the two ranked lists. The alpha parameter controls the weight given to the vector score; beta = 1 - alpha controls BM25. An adaptive sweep tests every alpha from 0.1 to 0.9 and picks the best.

## Embedding Approaches
LongText embedding encodes the whole document as a single vector. ChildChunk embedding encodes each chunk separately. Comparing these two approaches under identical retrieval conditions is a primary goal of this platform.
`,
  },
  {
    filename: "hybrid-search-deep-dive.md",
    contentType: "text/markdown",
    text: `# Hybrid Search Deep Dive

## BM25 Scoring
Okapi BM25 scores documents against a query using term frequency, inverse document frequency, and document length normalization. The formula balances relevance against document verbosity. BM25 is strong at matching exact keywords that dense embeddings may miss.

## Reciprocal Rank Fusion
Reciprocal Rank Fusion combines multiple ranked lists without needing score calibration. For each document, sum one over (k plus its rank) across all lists, with k typically set to 60. RRF is robust when the two retrieval systems produce scores on different scales.

## Adaptive Weight Tuning
Instead of fixing alpha at a heuristic value, an adaptive sweep evaluates every candidate alpha from 0.1 to 0.9. For each alpha, the system fuses vector and BM25 scores and records the top similarity. The alpha producing the highest top similarity is selected for the final ranking.

## Reranking
A cross-encoder reranker takes a query and a candidate passage as joint input and outputs a relevance score. Reranking the top N candidates after hybrid fusion improves precision. The tradeoff is latency, since each candidate requires a separate model call.

## Max-Pooling Children
When using a parent-child hierarchy, multiple children may belong to the same parent. Max-pooling takes the highest child score as the parent score, so a parent is retrieved if any of its children matches well.
`,
  },
  {
    filename: "embedding-models.md",
    contentType: "text/markdown",
    text: `# Embedding Models for RAG

## BGE-M3
BGE-m3 is a multilingual embedding model producing 1024-dimensional vectors. It supports long context windows and performs well across languages. On a GTX 3070 Ti with 8 GB VRAM, BGE-M3 fits comfortably under load.

## Float Precision
When running on GPU, embedding models may output bfloat16 tensors. To convert to a numpy array, always cast to float32 on CPU first: tensor.cpu().to(torch.float32).numpy(). This avoids dtype errors in downstream cosine similarity computation.

## Local-First Embedding
In environments without a GPU runtime, a deterministic feature-hashing embedding into 1024 dimensions can serve as a local-first substitute. It mixes word unigrams, word bigrams, and character trigrams with TF weighting and L2 normalization. The interface matches BGE-M3 so the system can swap backends without changing the orchestrator.

## Cosine Similarity
Cosine similarity measures the angle between two vectors, independent of their magnitude. It is the standard metric for dense retrieval. After L2 normalization, cosine similarity reduces to a simple dot product.
`,
  },
  {
    filename: "experiment-design.md",
    contentType: "text/markdown",
    text: `# Designing RAG Experiments

## Controlled Comparison
A controlled experiment varies one factor at a time while holding the rest constant. To compare LongText against ChildChunk embedding, keep the chunking method, the search config, and the document corpus identical. Only the embedding approach differs.

## Observability
Every experiment must record per-chunk metadata: token count, chunking time, embedding time, char range, and section path. The experiment summary records total chunks, average tokens, and total time. This metadata is what makes the platform a learning tool.

## The Memory Cart
The Memory Cart lets a researcher curate retrieval results. After a search, the researcher selects the most relevant passages and saves them to a cart. Over time, the cart becomes a curated dataset for evaluating future retrieval changes.

## Scope Guardrails for v1
Version one supports standard paths only. Late chunking and agentic chunking are deferred. Structured chat, GraphRAG, and multi-user features are out of scope. Keeping the scope tight is what makes v1 shippable and observable.
`,
  },
];

export async function POST(_req: NextRequest) {
  return withErrors(async () => {
    const created: string[] = [];
    const skipped: string[] = [];
    for (const d of SAMPLE_DOCS) {
      const existing = await db.document.findFirst({ where: { filename: d.filename } });
      if (existing) {
        skipped.push(d.filename);
        continue;
      }
      const doc = await db.document.create({
        data: {
          filename: d.filename,
          contentType: d.contentType,
          size: new Blob([d.text]).size,
          text: d.text,
        },
      });
      created.push(doc.id);
    }
    return NextResponse.json({ created: created.length, skipped, createdIds: created });
  });
}
