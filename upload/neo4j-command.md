1. Dashboard 頁面（系統統計 + Recent）

A. 統計數字（experiments, documents, chunks, searches, memories, carts）
位置：src/components/rag/views/dashboard-view.tsx
後端：dashboard_stats()

// Dashboard 統計數字（目前使用的版本）
MATCH (e:Experiment)
WHERE coalesce(e.kind, 'ingest') <> 'search'
WITH
    count(e) AS total,
    sum(CASE WHEN coalesce(e.status, '') = 'completed' THEN 1 ELSE 0 END) AS completed,
    sum(CASE WHEN coalesce(e.status, '') = 'failed' THEN 1 ELSE 0 END) AS failed

OPTIONAL MATCH (k:Knowledge)
WITH total, completed, failed, count(DISTINCT k.source_file) AS documents

OPTIONAL MATCH (c:KnowledgeChunk)
WITH total, completed, failed, documents, count(c) AS chunks

OPTIONAL MATCH (s:Experiment)
WHERE coalesce(s.kind, '') = 'search'
WITH total, completed, failed, documents, chunks, count(s) AS searches

OPTIONAL MATCH (m:Memory)
WITH total, completed, failed, documents, chunks, searches, count(m) AS memories

OPTIONAL MATCH (mc:MemoryCart)
WITH total, completed, failed, documents, chunks, searches, memories, count(mc) AS carts

RETURN {
    experiments: { total: total, completed: completed, failed: failed },
    documents: documents,
    chunks: chunks,
    searches: searches,
    memories: memories,
    carts: carts
} AS stats

Neo4j Browser 使用：

// 直接執行上面這段即可

B. Recent Experiments

MATCH (e:Experiment)
RETURN e
ORDER BY coalesce(e.created_at, datetime('1900-01-01')) DESC
LIMIT $limit

C. Recent Searches（kind = 'search' 的 Experiment）

MATCH (e:Experiment)
WHERE coalesce(e.kind, '') = 'search'
RETURN e
ORDER BY coalesce(e.created_at, datetime('1900-01-01')) DESC
LIMIT $limit

───

2. Ingest 頁面（Documents 清單）

位置：src/components/rag/views/ingest-view.tsx → DocumentsListCard
後端：list_documents()

// 目前已修正的版本
MATCH (k:Knowledge)
WITH k.source_file AS source_file,
     head(collect(k)) AS first,
     count(k) AS chunk_count,
     collect(DISTINCT k.embedding_method) AS methods
RETURN collect({
  id: source_file,
  filename: source_file,
  contentType: 'text/markdown',
  sizeBytes: size(first.text),
  totalChunks: chunk_count,
  createdAt: first.created_at,
  representativeEmbeddingMethod: first.embedding_method,
  kinds: methods
}) AS items, count(DISTINCT source_file) AS total

後端額外處理：
• Client-side 排序（依 createdAt DESC）
• Client-side 分頁（[skip : skip + page_size]）

建議測試參數：

:params {page: 1, pageSize: 20}

───

3. Experiments 頁面（最主要展示區）

A. Experiments 清單
位置：experiments-view.tsx（列表模式）
後端：list_experiments()

// 無 kind 過濾（全部）
MATCH (e:Experiment)
WITH e ORDER BY coalesce(e.created_at, datetime('1900-01-01')) DESC
RETURN collect(e) AS items, count(e) AS total

// 有 kind 過濾（ingest 或 search）
MATCH (e:Experiment)
WHERE coalesce(e.kind, '') = $kind
WITH e ORDER BY coalesce(e.created_at, datetime('1900-01-01')) DESC
RETURN collect(e) AS items, count(e) AS total

後端額外處理：Client-side 分頁。

B. 單一 Experiment 詳細資料

MATCH (e:Experiment {id: $id})
RETURN e

C. Chunks（Chunk Browser + Inspector）
位置：Experiments 詳細頁 → ChunkBrowser
後端：list_chunks_for_experiment()

MATCH (e:Experiment {id: $id})
OPTIONAL MATCH (k:Knowledge {experiment_id: $id})
OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
RETURN
  collect(DISTINCT k) AS parents,
  collect(c) AS children

後端重要處理（你一定要知道）：
• 把 parent :Knowledge 標記 node_type: "knowledge"
• 把 child :KnowledgeChunk 標記 node_type: "knowledge_chunk"
• 先排 parents，再排 children（依 chunk_index）

D. Source Document（顯示原始上傳 + 完整 ingested 文件）
位置：Experiments 詳細頁的 Source Document 區塊
後端：get_experiment_document()

這個方法會呼叫下面兩個：

1. 原始上傳的 :Knowledge（Upload placeholder）

MATCH (k:Knowledge {source_file: $source_file, embedding_method: 'Upload'})
WHERE k.text IS NOT NULL
RETURN k
ORDER BY coalesce(k.created_at, datetime('1900-01-01')) DESC
LIMIT 1

2. Ingest 後的完整文件（LongText parent）
   → 實際上是重複呼叫 list_chunks_for_experiment，然後取第一個 node_type = 'knowledge' 的。

───

快速測試建議（Neo4j Browser）

// 1. 先設定常用參數
:params {
  id: "你的 experiment id",
  source_file: "你的檔案名稱.md",
  kind: "ingest",
  limit: 5,
  page: 1,
  pageSize: 20
}

// 2. 測試主要查詢
// Dashboard 統計
// Experiments 清單
// Documents 清單
// Chunks
// ...

───