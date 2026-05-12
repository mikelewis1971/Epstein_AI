import fitz  # PyMuPDF
import base64
import json
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import time

# ====================== CONFIG ======================
TEXT_MODEL = "qwen2.5-7b-instruct"      # Main Orchestrator / Judge
VISION_MODEL = "qwen2.5-vl-7b-instruct" # Vision Model

MAX_RETRIES = 3
client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

def image_to_base64(pixmap):
    return base64.b64encode(pixmap.tobytes("png")).decode('utf-8')

def judge_transcription(page_text: str, attempts: list) -> dict:
    prompt = f"""You are an expert legal document transcriber and quality controller.

Current transcription:
{page_text}

Previous attempts: {len(attempts)}

Evaluate completeness, accuracy, and clarity. Return valid JSON only:
{{
  "quality_score": 0.0-1.0,
  "decision": "FINAL" or "RETRY",
  "next_instructions": "specific guidance for next vision pass",
  "final_transcription": "clean version if FINAL"
}}"""

    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2048
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except:
        return {"quality_score": 0.6, "decision": "FINAL", "final_transcription": page_text}

def transcribe_vision(b64: str, instructions: str, temp: float):
    prompt = f"Transcribe this official DOJ document page with maximum accuracy. {instructions}"
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        temperature=temp,
        max_tokens=4096
    )
    return resp.choices[0].message.content.strip()

def process_page(pixmap, page_num: int, doc_name: str):
    b64 = image_to_base64(pixmap)
    attempts = []
    temp = 0.3

    for attempt in range(MAX_RETRIES):
        vision_text = transcribe_vision(b64, "Read every word carefully.", temp)
        attempts.append(vision_text)
        
        judgment = judge_transcription(vision_text, attempts)
        
        if judgment.get("decision") == "FINAL" or attempt == MAX_RETRIES - 1:
            final_text = judgment.get("final_transcription", vision_text)
            break
        else:
            temp = 0.7 if temp < 0.5 else 0.4  # adaptive temp

    result = {
        "source": doc_name,
        "page": page_num + 1,
        "text": final_text,
        "quality_score": judgment.get("quality_score"),
        "attempts": len(attempts)
    }
    
    return result

def main():
    pdf_folder = Path("pdfs_doj")
    output_file = Path("training_data.jsonl")
    
    for pdf_path in tqdm(list(pdf_folder.glob("*.pdf"))):
        print(f"\n→ Processing {pdf_path.name}")
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(dpi=250)
            result = process_page(pix, i, pdf_path.name)
            
            with output_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            
            print(f"   Page {i+1:3d} | Quality: {result['quality_score']:.2f} | Attempts: {result['attempts']}")

if __name__ == "__main__":
    main()
