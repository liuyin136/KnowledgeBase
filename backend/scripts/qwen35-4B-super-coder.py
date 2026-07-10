import sys

from download_models2 import expected_model_path, verify_model
from llama_cpp import Llama


try:
    model_path = expected_model_path()
    verify_model(model_path)
except (FileNotFoundError, ValueError) as exc:
    print(f"Model not available: {exc}", file=sys.stderr)
    sys.exit(1)

# 2. load the model by using GPU
print("Loading the model by using GPU...")
llm = Llama(
    model_path=str(model_path),
    n_gpu_layers=-1, #
    n_ctx=32768,      
    verbose=False    
)

# 3. Extract the code from file i defined, store as "context", file_path is constant.
file_path = "/app/scripts/read-only/init_neo4j.py"
with open(file_path, "r") as file:
    content = file.read()

tokens = llm.tokenize(content.encode("utf-8"), add_bos=True)
token_count_input = len(tokens)

# 4. Define the conversation content and generate the response
messages = [
    {"role": "system", "content": "You are a coding assistant. Read the content to generate definitation comments."},
    {"role": "user", "content": f'{content}'}
]

print("Generating response...\n")
response = llm.create_chat_completion(
    messages=messages,
    temperature=0.6,    # recommended temperature value by the author
    top_p=0.95,         # recommended top-p value by the author
    #max_tokens=1024     # limit the maximum output length
)

# 5. Print the result
result = response['choices'][0]['message']['content']
print(result)
tokens = llm.tokenize(result.encode("utf-8"), add_bos=True)
token_count = len(tokens)
print(f"This input has {token_count_input} tokens.")
print(f"This response has {token_count} tokens.")
