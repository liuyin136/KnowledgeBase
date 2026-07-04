#!/usr/bin/env python3
"""
test_chunking_jina_late_v2.py
================================================================================
只執行這一個檔案，就能完成整個進階 Token-level + Mean Pooling 流程。

流程（嚴格按照要求）：
1. 從 RAW_FILE_PATH 讀取原始 .md
2. 呼叫 split_and_clean_v2.py 的 clean_text() 得到 cleaned_text
3. 在 cleaned_text 上使用 Jina v5 取得 last_hidden_state + offset_mapping
4. 在 cleaned_text 上使用 RecursiveCharacterTextSplitter(return_start_index=True) 拆 chunk
5. 根據每個 chunk 的字元範圍，從 offset_mapping 選出對應 token → mean pooling
6. Query 使用 SentenceTransformer + task="retrieval" + prompt_name="query"
7. 計算 similarity → 輸出 Top-K（含 similarity、span、內容預覽）
================================================================================
"""

import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Any

from transformers import AutoTokenizer, AutoModel


# ======================== 從 v2 library 匯入 ========================
from split_and_clean_v2 import clean_text, split_into_chunks


# ======================== 使用者設定 ========================
RAW_FILE_PATH = "./01_Climate_Change_and_Energy_Transition.md"   # ←←← 請改成你的原始 .md 檔案

QUERY = "Overview of climate change impacts on coastal cities"

MODEL_NAME = "jinaai/jina-embeddings-v5-text-small"
TOP_K = 10
MAX_LENGTH = 8192
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# ========================================================


def get_token_level_embeddings(text: str, tokenizer, model):
    """對 cleaned_text 做一次 forward，取得 token embeddings 與 offset mapping"""
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_LENGTH,
        return_offsets_mapping=True,
        padding=False
    ).to(DEVICE)

    offset_mapping = inputs.pop("offset_mapping")[0].cpu().to(torch.float32).numpy()

    with torch.no_grad():
        outputs = model(**inputs)

    token_embeddings = outputs.last_hidden_state[0].cpu().to(torch.float32).numpy()
    return token_embeddings, offset_mapping



def mean_pool_chunk(
    token_embeddings: np.ndarray,
    offset_mapping: np.ndarray,
    start_char: int,
    end_char: int
) -> np.ndarray:
    """根據 chunk 的字元範圍，選出對應的 token 並做 mean pooling"""
    mask = (
        (offset_mapping[:, 0] < end_char) &
        (offset_mapping[:, 1] > start_char)
    )
    if not np.any(mask):
        return np.zeros(token_embeddings.shape[1], dtype=np.float32)
    return np.mean(token_embeddings[mask], axis=0)


def main():
    print("=" * 115)
    print("Jina v5 Token-level Embedding + Mean Pooling per Chunk (v2 最終版)")
    print("=" * 115)

    # 1. 讀取 RAW 檔案
    raw_path = Path(RAW_FILE_PATH)
    if not raw_path.exists():
        print(f"❌ 找不到檔案：{RAW_FILE_PATH}")
        print("請修改最上方的 RAW_FILE_PATH 為正確的原始 .md 路徑")
        return

    print(f"\n📖 讀取原始檔案：{raw_path.name}")
    raw_content = raw_path.read_text(encoding="utf-8")

    # 2. 清理文字
    print("\n🧹 使用 clean_text() 進行清理...")
    cleaned_text = clean_text(raw_content, aggressive=False)
    print(f"   清理後字數: {len(cleaned_text):,}")

    # 3. 載入 Jina v5 模型
    print(f"\n[載入] {MODEL_NAME} ...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True).to(DEVICE)
    model.eval()

    # 4. 取得 token-level embeddings + offset_mapping
    print("\n[Token Embedding] 取得 last_hidden_state + offset_mapping ...")
    token_embeddings, offset_mapping = get_token_level_embeddings(
        cleaned_text, tokenizer, model
    )
    print(f"   Token 數量: {len(token_embeddings):,}")

    # 5. 拆分 chunks（在 cleaned_text 上）
    print("\n🔪 使用 RecursiveCharacterTextSplitter 拆分 cleaned_text ...")
    chunks = split_into_chunks(cleaned_text)
    print(f"   共 {len(chunks)} 個 chunks")

    # 6. 每個 chunk 做 mean pooling
    print("\n[Mean Pooling] 根據 chunk span 計算 mean pooling ...")
    pooled_list = []
    for chunk in chunks:
        pooled = mean_pool_chunk(
            token_embeddings,
            offset_mapping,
            chunk["start_char"],
            chunk["end_char"]
        )
        pooled_list.append(pooled)
    chunk_embeddings = np.stack(pooled_list)

    # 7. Query embedding
    print("\n[Query] 使用 task='retrieval' + prompt_name='query' ...")
    query_emb = model.encode(
        texts=[QUERY],
        task="retrieval",
        prompt_name="query",
    )

    query_vec = query_emb.cpu().to(torch.float32).numpy()

    # 8. 計算 similarity 並排序
    print("\n[Similarity] 計算 Top-K ...")
    sims = []
    for i in range(len(chunks)):
        a = query_vec
        b = chunk_embeddings[i]

        # 確保都是 1D numpy array，避免 0-d array 轉 float 錯誤
        if isinstance(a, torch.Tensor):
            a = a.cpu().numpy()
        if isinstance(b, torch.Tensor):
            b = b.cpu().numpy()

        a = np.asarray(a, dtype=np.float64).ravel()
        b = np.asarray(b, dtype=np.float64).ravel()

        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        sim = float(dot / norm) if norm > 0 else 0.0

        sims.append((i, sim))
        sims.sort(key=lambda x: x[1], reverse=True)
        top_k = sims[:TOP_K]

    # 9. 輸出結果
    print("\n" + "=" * 115)
    print(f"Top-{TOP_K} 最相關 Chunks")
    print("=" * 115)

    for rank, (idx, score) in enumerate(top_k, 1):
        ch = chunks[idx]
        preview = ch["content"][:300].replace("\n", " ").strip()
        if len(ch["content"]) > 300:
            preview += " ..."

        print(f"\n【Rank {rank}】 Similarity: {score:.6f}")
        print(f"Chunk #{idx} | Span: [{ch['start_char']}:{ch['end_char']}]")
        print(f"Metadata: {ch.get('metadata', {})}")
        print(f"長度: {len(ch['content']):,} 字元")
        print(f"預覽:\n{preview}")
        print("-" * 100)

        # 以下是獨立呼叫的寫法（推薦這樣做）
   
    file_name = Path(RAW_FILE_PATH).name

    # 假設你已經執行過 main() 並產生了 chunks 和 chunk_embeddings
    # 如果想一次完成，可以把下面這行放在 main() 函數的最後面
    save_chunks_to_neo4j(chunks, chunk_embeddings, file_name)

    print("\n✅ 全部流程完成！")


# ======================== 寫入 Neo4j 的部分 ========================
from neo4j_chunk_db import Neo4jChunkDB   # ← 假設你把之前設計的 class 放在這個檔案
import numpy as np

def save_chunks_to_neo4j(
    chunks: list, 
    chunk_embeddings: np.ndarray, 
    file_name: str,
    replace_existing: bool = True   # ← 新增參數，預設為 True（建議保持）
):
    """
    將 chunk + embedding 寫入 Neo4j
    - replace_existing=True 時，會先刪除該 file_name 的所有舊 Chunk，再寫入新資料
    """
    print("\n[寫入 Neo4j] 準備資料並寫入資料庫...")

    # 1. 初始化資料庫連線
    db = Neo4jChunkDB()

    # 2. 建立 Vector Index（第一次執行時需要，之後可註解）
    db.create_vector_index()

    # 3. 如果需要，先刪除舊資料（更新檔案時使用）
    if replace_existing:
        deleted_count = db.delete_chunks_by_file(file_name)
        if deleted_count > 0:
            print(f"🗑️ 已刪除舊資料：{deleted_count} 筆 (file_name: {file_name})")
        else:
            print(f"ℹ️ 該檔案目前沒有舊資料，直接新增")

    # 4. 準備批次寫入資料
    chunk_records = []
    for i, chunk in enumerate(chunks):
        record = {
            "file_name": file_name,
            "chunk_index": i,
            "span_start": chunk["start_char"],
            "span_end": chunk["end_char"],
            "text": chunk["content"],
            "length": len(chunk["content"]),
            "embedding": chunk_embeddings[i].tolist(),   # 轉成 Python list
            "page": chunk.get("metadata", {}).get("page"),
            "section": chunk.get("metadata", {}).get("section"),
        }
        chunk_records.append(record)

    # 5. 批次寫入
    created_count = db.add_chunks_batch(chunk_records)
    print(f"✅ 成功寫入 {created_count} 個新 Chunk 到 Neo4j")

    db.close()
    return created_count

# ======================== 在 main() 最後呼叫 ========================
if __name__ == "__main__":
    main()

    # === 新增：寫入資料庫 ===
    # 注意：要先執行上面的 main() 產生 chunks 和 chunk_embeddings
    # 所以建議把 main() 改成回傳值，或直接在 main() 裡面呼叫下面這行


