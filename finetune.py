# 3_finetune.py
import json
from pathlib import Path
from datasets import Dataset
from unsloth import FastLanguageModel
import torch
from tqdm import tqdm

# ====================== CONFIG ======================
MODEL_NAME = "unsloth/Qwen2.5-7B-Instruct"   # Change to 1.5B, 3B, 14B etc. as needed
MAX_SEQ_LENGTH = 8192
DTYPE = None  # Auto detection
LOAD_IN_4BIT = True

OUTPUT_DIR = "epstein_finetuned_model"
DATASET_PATH = Path("training_data.jsonl")

# ====================== DATA PREPARATION ======================
def load_and_format_data():
    """Convert raw transcriptions into proper SFT format"""
    data = []
    
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Loading & formatting data"):
            if not line.strip():
                continue
            item = json.loads(line)
            
            text = item.get("text", "").strip()
            if len(text) < 50:  # Skip very short / bad pages
                continue
                
            # High-quality instruction format for Epstein domain
            conversation = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Epstein AI, an expert research assistant specialized in the official U.S. Department of Justice Epstein Files. You provide accurate, well-structured, and properly cited information based on primary source documents."
                    },
                    {
                        "role": "user",
                        "content": f"""Transcribe and clean the following page from an official DOJ Epstein document.

Source: {item.get('source', 'Unknown')}
Page: {item.get('page', '?')}

Document content:"""
                    },
                    {
                        "role": "assistant",
                        "content": text
                    }
                ]
            }
            data.append(conversation)
    
    print(f"Prepared {len(data)} training examples")
    return Dataset.from_list(data)

# ====================== LOAD MODEL ======================
print("Loading model...")
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=DTYPE,
    load_in_4bit=LOAD_IN_4BIT,
    trust_remote_code=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=32,                    # LoRA rank
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
    use_rslora=True,
    loftq_config=None,
)

# ====================== TRAINING ======================
dataset = load_and_format_data()

trainer = model.trainer(
    train_dataset=dataset,
    dataset_text_field=None,           # We use chat format
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=4,
    packing=False,                     # Better for document data
    args={
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 8,
        "warmup_steps": 10,
        "max_steps": 400,              # Adjust based on your dataset size
        "learning_rate": 2e-4,
        "fp16": not torch.cuda.is_bf16_supported(),
        "bf16": torch.cuda.is_bf16_supported(),
        "logging_steps": 10,
        "optim": "adamw_8bit",
        "weight_decay": 0.01,
        "lr_scheduler_type": "linear",
        "seed": 3407,
        "output_dir": OUTPUT_DIR,
        "report_to": "none",           # Change to "wandb" if you want logging
    },
    tokenizer=tokenizer,
)

print("Starting fine-tuning...")
trainer_stats = trainer.train()

# ====================== SAVE MODEL ======================
print("Saving model...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

# Export to GGUF for LM Studio (recommended)
print("Exporting GGUF (for LM Studio)...")
model.save_pretrained_merged(
    OUTPUT_DIR + "_gguf",
    tokenizer,
    save_method="merged_16bit",   # or "merged_4bit" for smaller size
)

print(f"\n✅ Fine-tuning complete!")
print(f"Model saved to: {OUTPUT_DIR}")
print(f"GGUF version ready for LM Studio in: {OUTPUT_DIR}_gguf")
