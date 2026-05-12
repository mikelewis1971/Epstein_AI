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
