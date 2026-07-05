
以下是針對指定範圍的純 Review（Review only，無任何修改）。 我已依 ponytail 原則（先完整 trace 真實端到端 flow、再指出最簡/現有問題）與 code-review-and-quality 五軸（Correctness、Readability、Architecture、Security、Performance）進行審查。所有說明以繁體中文呈現，引用關鍵檔案與路徑。

1. Dashboard 如何顯示系統統計（Experiments 與 Documents 數量）

資料流程（真實路徑）：

• 前端：src/components/rag/views/dashboard-view.tsx
  • 使用 useQuery<DashboardData>({ queryKey: ["dashboard"], queryFn: api.dashboard })
  • STAT_META 陣列定義：
    • experimentsTotal → s.experiments.total（顯示 "Experiments" 大數字 + ${completed} done · ${failed} failed）
    • documents → s.documents（顯示 "Documents" + "uploaded source files"）
  • 其他 stats（chunks, searches...）同樣來自同一個 payload。
  • 同時顯示 Recent Experiments（來自 recentExperiments，點擊會 setActiveExperiment + 切換 view）。

• Next.js Proxy：src/app/api/v1/dashboard/route.ts
  • 同時呼叫 backendHealth() + verifyNeo4jConnectivity()
  • 若 backend online：proxyToBackend(...) 到 GET /api/v1/dashboard，直接轉發 data.stats、recentExperiments、system
  • 否則 fallback 為全 0 的 stats + 預設 system block（v1.3 Jina 預設值）
  • 最後組裝 health（backend + neo4j 狀態）回傳給前端。

• FastAPI：backend/app/api/v1/dashboard.py
  • 單純 stats = db.dashboard_stats() + recent_experiments / recent_searches
  • 回傳 {"stats": ..., "recentExperiments": [..._exp_to_response...], "system": {embeddingModel, ...}}（system 來自 app.core.config + constants）

• Neo4j 真實紀錄來源：backend/app/db/neo4j_client.py 的 dashboard_stats()

MATCH (e:Experiment)
  WITH count(e) AS total, sum(CASE ... 'completed') AS completed, ...
  OPTIONAL MATCH (k:Knowledge)
  WITH ..., count(DISTINCT k.source_file) AS documents
  OPTIONAL MATCH (c:KnowledgeChunk) → chunks
  OPTIONAL MATCH (s:Experiment) WHERE kind='search' → searches
  ... memories, carts
  RETURN { experiments: {total, completed, failed}, documents, ... }
  • Experiments 數字 = 直接數 :Experiment 節點總數 + 狀態分類。
  • Documents 數字 = count(DISTINCT k.source_file) 來自所有 :Knowledge 節點（包含 Upload placeholder 與 ingest 後的 LongText/ChildChunk）。

這就是 Dashboard 兩個主要數字的完整來源：全部經由 Neo4j Cypher 聚合後，經 backend → proxy → TanStack Query 渲染。

2. Ingest 文件列表（Documents）與 Active Ingestion 如何顯示 Neo4j 紀錄

Documents 列表（左側卡片）：

• src/components/rag/views/ingest-view.tsx 的 DocumentsListCard
  • useQuery ["documents", {page:1, pageSize:50}] → api.documents.list
• Proxy：src/app/api/v1/documents/route.ts（極薄，僅 proxyToBackend）
• Backend：backend/app/api/v1/documents.py → list_documents() → db.list_documents()
• Neo4j 查詢（neo4j_client.py）：

MATCH (k:Knowledge)
  WITH k.source_file AS source_file, head(collect(k)) AS first, count(k) AS chunk_count
  ... collect(DISTINCT embedding_method) AS methods
  RETURN collect({ id: source_file, filename: source_file, sizeBytes: size(first.text),
                   representativeEmbeddingMethod: first.embedding_method, kinds: methods, ... }) AS items, ...
• UI 渲染：
  • 顯示 filename（即 source_file）
  • 額外 badge：representativeEmbeddingMethod、kinds、特別標 LongText :knowledge
  • 這些都是直接從 :Knowledge 節點的屬性投影出來。

Active Ingestion（右側 Live 面板）：

• IngestProgressPanel + chunkEvents
  • 來自 useQuery(["ingest-status", jobId]) → api.ingest.status（輪詢 /api/v1/ingest/{jobId}/status）
  • 此階段主要來自 Redis/ProgressTracker（backend/app/workers/progress.py + tasks.py），不是直接打 Neo4j。
  • 事件在 orchestrator.py 的 ingest_long_text / ingest_child_chunk 過程中產生：
    • chunking → embedding → persisting 階段
    • 每塊都帶 ChunkMetadata（chunkMethod, embeddingMethod, tokenCount, times, section, textPreview 等）
  • 完成時（status === "completed"）才 qc.invalidateQueries(["dashboard", "experiments", "documents"])，之後才從 Neo4j 讀取。
• 備註：在面板中已出現「LongText windows stored as :Knowledge」的文字提示，明確告訴使用者這些資料最終會變成 Neo4j 節點。

總結：Active 階段顯示的是「即將寫入 Neo4j 的紀錄快照」（來自記憶體/Redis stream）；完成後才真正由 Experiments / Dashboard 從 :Knowledge / :KnowledgeChunk / :Experiment 讀取。

3. Experiments View 如何顯示 Neo4j 紀錄

• src/components/rag/views/experiments-view.tsx
  • List 模式：api.experiments.list → 顯示 Experiment 列表（含 status、embeddingApproach、chunkMethod、totalChunks、sourceFile）
  • Detail 模式：
    • api.experiments.get(id) → Experiment 基本資料
    • api.experiments.chunks(id) → Chunk Browser
    • api.experiments.document(id) → Source Document（特別強調顯示原始與 ingested）
  • UI 明確區分：
    • nodeType === 'knowledge' → "Full :Knowledge text (document)" + FULL DOC 標籤
    • 其餘為 :KnowledgeChunk
    • SourceDocumentSection / OriginalDocumentSection 會優先拿 doc?.ingested?.text 或 original?.text

後端對應：
• backend/app/api/v1/experiments.py：
  • _exp_to_response 把 snake_case Experiment dict 轉 camelCase
  • get_experiment_chunks → db.list_chunks_for_experiment(experiment_id)
  • get_experiment_document → 呼叫 get_original_knowledge + list_chunks_for_experiment 挑第一個 knowledge

• Neo4j 關鍵查詢（neo4j_client.py）：

-- list_chunks_for_experiment
  MATCH (e:Experiment {id: $id})
  OPTIONAL MATCH (k:Knowledge {experiment_id: $id})
  OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
  RETURN collect(DISTINCT k) AS parents, collect(c) AS children
  -- 之後 client 端排序、標 node_type = 'knowledge' / 'knowledge_chunk'

  -- get_experiment_document 另外抓 embedding_method='Upload' 的原始 placeholder

• create_experiment 與實際寫入發生在 orchestrator.py（create_experiment + 多個 create_knowledge + 後續更新 Experiment 狀態）。

因此 Experiments View 是最直接展示 Neo4j 圖形紀錄的地方：一個 Experiment 節點 + 它關聯的 Knowledge（parent）與 KnowledgeChunk（children）。

Code-Review-and-Quality 五軸 Review 發現（重點）

Correctness（正確性）
• Dashboard stats documents 與 Ingest 文件列表都來自 Knowledge 的 source_file，語意一致（好）。
• 重大問題：neo4j_client.py list_documents() 的 Cypher 在第二個 WITH 直接寫 k.source_file 與 k.embedding_method，但第一個 WITH 已將變數綁定到 source_file / first，k 已不在 scope。這段查詢幾乎一定出錯或回傳空結果。這是 Ingest 文件列表的根本來源，屬 Critical。
• list_chunks_for_experiment 與 get_experiment_document 邏輯重複（parents 挑第一個），容易在 LongText vs ChildChunk 邊界出錯。
• 上傳 placeholder 用 embedding_method='Upload' + vector=null 的設計正確（不會污染索引）。

Readability & Simplicity
• 大量 _exp_to_response、 _chunk_to_response、 _knowledge_to_document 重複 coercion 邏輯，散落在多處。
• UI 內大量 (c as any).nodeType || c.node_type 型別斷言，顯示 schema 與回傳不夠嚴謹。
• dashboard_stats 用一連串 OPTIONAL MATCH 累加計數，可讀性差（雖然對小資料沒差）。

Architecture
• 資料擁有者清楚：所有 RAG 狀態（Experiment / Knowledge / KnowledgeChunk）都只存在 Neo4j，Redis 只負責即時 job 進度。proxy 層很薄，正確。
• 但 list_documents 在 client 端做全量 collect 後再 slice 排序（非資料庫分頁），與 backend list_experiments 的 server-side skip 設計不一致。
• 沒有單一的「Neo4j record projection」工具函式，導致重複。

Security
• 無明顯注入（Cypher 都有參數化）。
• 文件上傳只接受 .md，驗證存在。
• 刪除文件會 cascade（neo4j_client.delete_document）。

Performance
• dashboard_stats 與 list_documents 都做全表 MATCH + collect，對大量文件/實驗會變慢（目前用 OPTIONAL MATCH 多次掃描）。
• Ingest 完成後一次 invalidates 多個 queryKey，正確但可能造成不必要重載。
• list_documents 內 sorted(items, ...) 在 Python 端做，資料量大時浪費記憶體。

Ponytail 視角（Review only）

• 最懶（也最正確）的路徑已經存在：所有顯示 Neo4j record 的 UI 都經由 backend/neo4j_client 的單一查詢，前端幾乎不直接碰 driver（只有 health 用）。這點做得好，不需要再發明新抽象。
• 但 list_documents Cypher 這類「看起來在做，但其實壞掉」的程式碼，是典型的「第二個 bug 來源」。
• 重複的 coercion 函式 + 任何 as any 都是可以刪減的 boilerplate。
• dashboard_stats 可以用單一 Cypher + 更明確的 WITH 聚合一次完成（更少掃描）。
• 目前設計「Upload placeholder 與 ingest 後 Knowledge 分開存」是正確且必要的（避免 double-count），不需要再簡化。

總結觀察（不需行動）： Dashboard stats（experiments/documents）與 Experiments 的主畫面真正來自 Neo4j 的 :Experiment + :Knowledge + :KnowledgeChunk；Ingest 的文件列表也是；Active Ingestion 則是「預覽即將落地的 Neo4j 紀錄」。

以上 trace 完整覆蓋從 UI → proxy → FastAPI → neo4j_client Cypher 的所有呼叫點。Review 完畢。