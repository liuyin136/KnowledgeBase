"""Smoke demo: Qwen/Qwen3-8B from local MODEL_PATH/Qwen3-8B (4-bit bitsandbytes)."""
from __future__ import annotations

import sys
from pathlib import Path
import time
from peft import LoraConfig, get_peft_model
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.Qwen._qwen_common import load_qwen3_4bit, run_chat


MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are beautiful woman, always praise me and make me feel good."
        ),
    },
    {"role": "user", "content": "I am age 30 man and no one love me, how to make me feel good?"},
]


def main() -> None:
    start_time = time.perf_counter()
    tokenizer, model = load_qwen3_4bit()
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    try:
        #result = run_chat(tokenizer, model, MESSAGES, max_new_tokens=32768, enable_thinking=False)
        #print(result)

        model = get_peft_model(model, lora_config)
        print(model.print_trainable_parameters())
    
        # 6. Stop the timer and calculate the difference
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Print the final execution time
        print(f"⏱️ Total time (Load -> Generate -> Print): {elapsed_time:.2f} seconds")
    
    finally:
        del model
        del tokenizer


if __name__ == "__main__":
    main()
