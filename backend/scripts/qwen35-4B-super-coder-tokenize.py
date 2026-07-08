import sys

from download_models2 import expected_model_path, verify_model
from llama_cpp import Llama

try:
    model_path = expected_model_path()
    verify_model(model_path)
except (FileNotFoundError, ValueError) as exc:
    print(f"Model not available: {exc}", file=sys.stderr)
    sys.exit(1)

# Load vocab only (no full model weights) for lightweight token counting
print("Loading tokenizer from GGUF...")
llm = Llama(
    model_path=str(model_path),
    vocab_only=True,
    n_gpu_layers=0,
    verbose=False,
)

file_path = "/app/scripts/read-only/init_neo4j.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# add_bos=True adds the beginning-of-sequence token
tokens = llm.tokenize(content.encode("utf-8"), add_bos=True)
token_count = len(tokens)

print(f"File: {file_path}")
print(f"Token count: {token_count}")
