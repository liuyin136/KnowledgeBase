# Run: docker compose exec api-worker python /app/scripts/LiquidAI/lfm25-8b-a1b.py
import sys
from pathlib import Path
import json
import re


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.LiquidAI._liquid_common import load_liquid, run_chat

MODEL_KEY = "liquid-8b"

def pre_filter_chunks(chunks, scores, threshold=0.5):
    """
    實作 B: 利用 Hybrid Search 的分數過濾低品質 Chunk
    """
    filtered = []
    for i, (chunk, score) in enumerate(zip(chunks, scores)):
        if score >= threshold:
            filtered.append(f"[Chunk {i+1}]\n{chunk}")
    return "\n\n".join(filtered)

def main() -> None:
    llm = load_liquid(MODEL_KEY)

    
    # ... (此處省略上文定義好的 graph_schema) ...
    graph_schema = {
    "type": "object",
    "properties": {
        "split_result": {
        "type": "string",
        "description": "Comma-separated tokens from the input sentence"
        }
    },
    "required": ["split_result"]
    }

    chunk_category = "MSSQL"
    sample_query = "當你在跑 DeepSeek-R1 這類模型時"
    
    # 模擬 Hybrid Search 返回的結果與分數
    raw_chunks = [
        "Microsoft introduced a new approach to Graph RAG.",
        "The weather in Seattle is usually rainy.", # 雜訊，分數極低
        "Neo4j integrates natively with LangChain for Graph RAG."
    ]
    search_scores = [0.85, 0.12, 0.78]

    # 1. 執行實作 B：過濾雜訊
    relevant_context = pre_filter_chunks(raw_chunks, search_scores, threshold=0.5)

    # 2. 執行實作 A：Query-Guided Prompt
    system_prompt = f"""
Split the input sentence into individual words or meaningful tokens separated by commas.
Output only the comma-separated list, nothing else.
"""
#2. Supplementing with common domain entities is allowed ({search_scores} > 0.5 must be annotated)

    user_prompt = f"""
{sample_query}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    print("Generating Query-Guided Graph JSON...\n")
    
    # 執行提取 (假設 run_chat 支援 response_format)
    result = run_chat(llm, messages, max_tokens=2048)
    clean_json_str = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL).strip()
    print(clean_json_str)
    #print(result)
    del llm

if __name__ == "__main__":
    main()