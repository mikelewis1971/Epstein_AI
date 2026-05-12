# Epstein_AI
Turn the Epstien files into an AI by converting the documents to a RAG or training data


**Here's the refactored, no-bullshit, LM Studio-centric guide.** Everything is built around LM Studio's local OpenAI-compatible server for maximum simplicity and compatibility with your Qwen workflow.

### 1. Install and Set Up LM Studio (Exact Steps)
1. Go to [lmstudio.ai](https://lmstudio.ai/) and download the latest version for your OS (Windows, macOS, or Linux).
2. Install and open LM Studio.
3. **Download the Vision Model** (required for OCR/transcription):
   - Go to the **Discover** / search tab.
   - Search for: `Qwen2.5-VL-7B-Instruct` (recommended) or the smaller `Qwen2.5-VL-3B` / `2B` variants if VRAM is limited.
   - Download a GGUF quantized version (e.g., Q4_K_M or Q5_K_M for good speed/quality balance). LM Studio will show available quants.
   - Load the model in the chat interface first and test it with a sample document image to confirm vision works ("Transcribe this page").

4. **Start the Local Server** (this is what your Python scripts will talk to):
   - Click the **Developer** tab (bottom-left or sidebar).
   - Toggle **Developer Mode** if needed.
   - In the Developer/Local Server section, turn on the server (Status: Running).
   - Default endpoint: `http://localhost:1234/v1`
   - You can also use the CLI: `lms server start` in a terminal.

**Test the server** (optional but recommended):
```bash
curl http://localhost:1234/v1/models
```

### 2. Python Environment Setup
```bash
# Create a clean environment
python -m venv epstein_pipeline
source epstein_pipeline/bin/activate    # Windows: epstein_pipeline\Scripts\activate

pip install openai pymupdf pillow requests tqdm sqlite3  # PyMuPDF = fitz
```

### 3. Core Worker Script (LM Studio + Multi-Pass OCR)
This script uses your local LM Studio server for all vision calls. Save as `worker.py`.

```python
import fitz  # PyMuPDF
import base64
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import time

# Point to LM Studio
client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"  # dummy key, LM Studio ignores it
)

MODEL_NAME = "qwen2.5-vl-7b-instruct"  # exact name as loaded in LM Studio

def image_to_base64(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

def process_page(page_pixmap, page_num, doc_name):
    img_bytes = page_pixmap.tobytes("png")
    b64 = image_to_base64(img_bytes)
    
    transcripts = []
    temperatures = [0.2, 0.5, 0.7]
    
    for temp in temperatures:
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Accurately transcribe ALL text from this document page. Include layout, handwriting, redactions, and any notes. Be precise and complete."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }],
                temperature=temp,
                max_tokens=4096
            )
            transcripts.append(response.choices[0].message.content.strip())
            time.sleep(0.5)  # gentle rate limit
        except Exception as e:
            print(f"Error on temp {temp}: {e}")
            transcripts.append("")
    
    # Consensus / synthesis pass (send image + all 3 transcripts)
    consensus_prompt = f"""You are an expert document transcriber.
Here are 3 independent transcriptions of the same page.
Compare them carefully, resolve differences, correct errors, and produce ONE final high-quality transcription.

Transcripts:
1. {transcripts[0]}
2. {transcripts[1]}
3. {transcripts[2]}
"""
    
    final_resp = client.chat.completions.create(
        model=MODEL_NAME,  # or switch to a strong text-only Qwen if you prefer
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": consensus_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        temperature=0.3
    )
    
    final_text = final_resp.choices[0].message.content.strip()
    
    return {
        "source": doc_name,
        "page": page_num + 1,
        "text": final_text,
        "transcripts_raw": transcripts  # for debugging
    }

def main():
    pdf_folder = Path("pdfs")
    output_file = Path("training_data.jsonl")
    
    for pdf_path in tqdm(list(pdf_folder.glob("*.pdf"))):
        doc_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        # TODO: check against central DB to skip duplicates
        
        doc = fitz.open(pdf_path)
        results = []
        
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(dpi=250)  # 200-300 DPI good for docs
            page_data = process_page(pix, i, pdf_path.name)
            results.append(page_data)
        
        # Append to JSONL
        with output_file.open("a", encoding="utf-8") as f:
            for res in results:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
        
        print(f"Processed {pdf_path.name} — {len(doc)} pages")

if __name__ == "__main__":
    main()
```

**Tips for this script**:
- Run it while LM Studio server is active and the VL model is loaded.
- For weaker hardware, drop to Qwen2.5-VL 3B/2B and lower DPI.
- Add SQLite or a simple file for processed hashes to make it resumable and safe for multiple workers.

### 4. Coordinator / Distributed Setup (High-Level)
- Host a simple FastAPI app on your server (`mikes_server.com`) that maintains a list of available PDFs (from CourtListener RECAP links) with SHA hashes.
- Workers poll `/claim_job` → get a PDF URL → download → process → POST results to `/submit`.
- First submit wins; others get a new job.
- Use GitHub/Hugging Face to merge `training_data.jsonl` files from contributors.

### 5. Fine-Tuning Path (After Data Collection)
- Use the resulting `training_data.jsonl` for continued pre-training or SFT on a text Qwen model (e.g., Qwen2.5-7B or 1.5B-3B).
- Best tool: **Unsloth** (very fast on consumer GPUs) or Hugging Face TRL.
- Export back to GGUF → load into LM Studio as your "Epstein-specialized" model.

### Next Actions for You
1. Install LM Studio → download & test Qwen2.5-VL-7B.
2. Run the script above on 5-10 sample PDFs first.
3. Share any errors you hit (VRAM, model name, etc.).

Want me to generate the full coordinator FastAPI code, deduplication DB script, or a polished HTML user guide next? Just say the word. This setup is solid, local-first, and scales with many hands.
