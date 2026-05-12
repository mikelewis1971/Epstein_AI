**✅ Updated Project: Now Using Official DOJ Epstein Library**  
**Source: https://www.justice.gov/epstein**

This is the best and most authoritative source. The Department of Justice has released millions of pages under the Epstein Files Transparency Act, with properly redacted PDFs organized into data sets and court records.

---

### Updated Download Strategy for `1_download_docs.py`

Here's a new, clean downloader focused on the official DOJ site.

```python
import requests
from bs4 import BeautifulSoup
import hashlib
from pathlib import Path
from tqdm import tqdm
import time
import re

BASE_URL = "https://www.justice.gov"
PDF_FOLDER = Path("pdfs_doj")
PDF_FOLDER.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Epstein-Research-Pipeline/1.0"})

def get_all_pdf_links():
    """Crawl main disclosure pages and collect PDF links"""
    pdf_links = []
    start_pages = [
        "/epstein/doj-disclosures",
        "/epstein/doj-disclosures/data-set-12-files",  # example data set
        # Add more data set pages as needed
    ]
    
    for page in start_pages:
        url = BASE_URL + page
        print(f"Scanning: {url}")
        resp = session.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.lower().endswith('.pdf'):
                full_url = BASE_URL + href if href.startswith('/') else href
                filename = full_url.split('/')[-1]
                pdf_links.append((full_url, filename))
        
        time.sleep(1)  # Be respectful
    
    # Remove duplicates
    unique = {}
    for url, fname in pdf_links:
        unique[url] = fname
    return list(unique.items())

def download_pdf(url, filename):
    filepath = PDF_FOLDER / filename
    if filepath.exists():
        print(f"✅ Already downloaded: {filename}")
        return True
    
    print(f"Downloading: {filename}")
    try:
        resp = session.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✅ Downloaded: {filename}")
        return True
    except Exception as e:
        print(f"❌ Failed {filename}: {e}")
        return False

def main():
    print("🔍 Collecting PDF links from official DOJ Epstein Library...")
    links = get_all_pdf_links()
    print(f"Found {len(links)} unique PDFs")
    
    for url, filename in tqdm(links):
        download_pdf(url, filename)
        time.sleep(0.5)  # Rate limiting - be respectful to DOJ servers

if __name__ == "__main__":
    main()
```

**Note**: The DOJ site has many data sets. You can manually add more start pages (e.g. `/epstein/doj-disclosures/data-set-1-files`, etc.) or improve the crawler to follow pagination.

---

### Updated FastAPI Coordinator (Key Changes)

In `main.py`, update the seed function and job creation to use DOJ sources:

```python
# Inside main.py - replace the old seed-epstein with this:

@app.post("/seed-doj-epstein")
def seed_doj_epstein_jobs(db: Session = Depends(get_db)):
    # You can run the downloader first, then seed from local files, OR seed direct URLs
    samples = [
        {
            "doc_id": "EFTA02730265",
            "source_url": "https://www.justice.gov/epstein/files/DataSet%2012/EFTA02730265.pdf",
            "filename": "EFTA02730265.pdf",
            "sha256": ""  # Will be computed on first download
        },
        # The downloader script can also push new jobs to the coordinator via API
    ]
    
    added = 0
    for s in samples:
        try:
            create_job(JobCreate(**s), db)
            added += 1
        except:
            pass
    return {"added": added, "message": "DOJ Epstein Library jobs seeded"}
```

---


Just tell me what to generate next.
