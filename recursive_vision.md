New Recursive Workflow (High-Level)

Main AI (strong text model — e.g. Qwen2.5-7B or 14B) acts as the orchestrator / judge.
It instructs the Vision Model (Qwen2.5-VL) what to focus on.
Vision model transcribes the page.
Main AI reviews the result for accuracy, completeness, and consistency.
If quality is insufficient → it recursively asks the Vision model again with adjusted temperature / better instructions.
Once satisfied, the Main AI produces the final cleaned transcription.

This mimics a human supervisor + OCR specialist loop and usually delivers significantly higher quality.

Updated worker_recursive.py (Full Code)
Pythonimport fitz  # PyMuPDF
import base64
import json
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import time

# ====================== CONFIG ======================
TEXT_MODEL = "qwen2.5-7b-instruct"      # Your strong text model (Main AI / Judge)
VISION_MODEL = "qwen2.5-vl-7b-instruct" # Vision model

MAX_RETRIES = 3
QUALITY_THRESHOLD = 0.85  # Subjective score the judge gives itself (0-1)

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

def image_to_base64(pixmap):
    img_bytes = pixmap.tobytes("png")
    return base64.b64encode(img_bytes).decode('utf-8')

def judge_transcription(page_text: str, previous_attempts: list) -> dict:
    """Main AI evaluates quality and decides next action"""
    prompt = f"""You are an expert document analyst and quality controller.

Page content to evaluate:
{page_text}

Previous attempts (if any):
{chr(10).join([f"Attempt {i+1}: {att}" for i, att in enumerate(previous_attempts)])}

Evaluate the transcription on:
1. Completeness (all visible text captured?)
2. Accuracy (no hallucinations or misreads)
3. Clarity and structure
4. Handling of redactions/handwriting

Give a quality score 0.0-1.0 and decide:
- If score >= {QUALITY_THRESHOLD}: Return "FINAL" + improved clean version
- Else: Return "RETRY" + specific instructions for the vision model (what to focus on, what went wrong)
"""

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048
    )
    return json.loads(response.choices[0].message.content)  # Expect structured JSON output

def transcribe_with_vision(b64_image: str, instructions: str, temperature: float):
    """Vision model does the actual OCR"""
    prompt = f"""Transcribe this document page with extreme accuracy.
{instructions}

Rules:
- Capture every single word and number
- Preserve layout when important (tables, lists)
- Note redactions clearly as [REDACTED]
- Include any handwritten notes"""

    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
            ]
        }],
        temperature=temperature,
        max_tokens=4096
    )
    return response.choices[0].message.content.strip()

def process_page_recursive(pixmap, page_num: int, doc_name: str):
    b64 = image_to_base64(pixmap)
    attempts = []
    current_temp = 0.3
    
    for attempt in range(MAX_RETRIES):
        # Vision transcription
        vision_text = transcribe_with_vision(b64, 
            "Carefully read every part of this page." if attempt == 0 else attempts[-1].get("next_instructions", ""),
            current_temp)
        
        attempts.append({"text": vision_text, "temp": current_temp})
        
        # Main AI judges
        judgment = judge_transcription(vision_text, [a["text"] for a in attempts])
        
        if judgment.get("decision") == "FINAL" or attempt == MAX_RETRIES - 1:
            final_text = judgment.get("final_transcription", vision_text)
            break
        else:
            # Adjust strategy
            current_temp = judgment.get("suggested_temp", 0.6)
            # continue to next attempt
    
    return {
        "source": doc_name,
        "page": page_num + 1,
        "final_text": final_text,
        "quality_score": judgment.get("quality_score"),
        "attempts": len(attempts),
        "raw_attempts": attempts
    }

# ====================== MAIN ======================
def main():
    pdf_folder = Path("pdfs")
    output_file = Path("training_data_recursive.jsonl")
    
    for pdf_path in tqdm(list(pdf_folder.glob("*.pdf"))):
        print(f"\nProcessing: {pdf_path.name}")
        doc = fitz.open(pdf_path)
        
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(dpi=250)
            result = process_page_recursive(pix, i, pdf_path.name)
            
            with output_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            
            print(f"  Page {i+1}/{len(doc)} - Quality: {result['quality_score']} - Attempts: {result['attempts']}")
        
        time.sleep(1)  # Cooldown

if __name__ == "__main__":
    main()
Key Advantages of This Recursive Method

Much smarter error correction
Adaptive temperatures and instructions
Main AI has final authority on quality
Better handling of difficult pages (handwriting, poor scans, tables)
