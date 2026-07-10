from llama_cpp import Llama
import sys
import os
from contextlib import contextmanager

@contextmanager
def redirect_all_output_to_file(file_path):
    """強力的重定向工具，同時捕捉 Python 與底層 C++ 的 stdout 和 stderr"""
    # 開啟目標檔案
    log_file = open(file_path, "w", encoding="utf-8")
    
    # 備份原本的標準輸出與錯誤（Python 層面與系統 FD 層面）
    old_stdout_fd = os.dup(1)
    old_stderr_fd = os.dup(2)
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        # 1. 重定向 Python 層面的輸出
        sys.stdout = log_file
        sys.stderr = log_file
        
        # 2. 重定向系統底層（C++）的輸出描述符到檔案
        os.dup2(log_file.fileno(), 1)
        os.dup2(log_file.fileno(), 2)
        
        yield
    finally:
        # 刷新緩衝區
        sys.stdout.flush()
        sys.stderr.flush()
        
        # 復原系統底層描述符
        os.dup2(old_stdout_fd, 1)
        os.dup2(old_stderr_fd, 2)
        
        # 關閉備份的 FD
        os.close(old_stdout_fd)
        os.close(old_stderr_fd)
        
        # 復原 Python 層面
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        # 關閉檔案
        log_file.close()

# ==================== 開始測試 ====================
print("開始測試模型載入...")

# 使用剛才定義的上下文管理器來包裹測試邏輯
with redirect_all_output_to_file("scripts/temp.txt"):
    try:
        # 這裡所有的 Python print、llama.cpp 的底層 GGML 日誌都會進到 temp.txt
        llm = Llama(
            model_path="/app/models/liquid/LFM2.5-350M-BF16.gguf",   # ← 請改成實際 GGUF 模型完整路徑
            n_gpu_layers=-1,
            flash_attn=1,
            n_ctx=1024,
            n_batch=512,
            verbose=True
        )
        
        print("\n=== 模型載入成功 ===")
        print(f"Context length (n_ctx): {llm.n_ctx}")
        print(f"Model path: {llm.model_path}")
        
    except Exception as e:
        print(f"載入錯誤: {str(e)}")

print("測試完成！詳細 verbose log 已儲存到 ./temp.txt")
print("請執行: cat ./temp.txt")