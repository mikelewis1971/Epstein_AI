import requests
from bs4 import BeautifulSoup
from pathlib import Path
from tqdm import tqdm
import time
import hashlib

BASE_URL = "https://www.justice.gov"
PDF_FOLDER = Path("pdfs_doj")
PDF_FOLDER.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Epstein-Research-Pipeline/1.0"})

def get_pdf_links():
    """Basic crawler for DOJ Epstein pages"""
    pdf_links = []
    known_paths = [
        "/epstein",
        "/epstein/doj-disclosures",
        # Add more specific dataset pages as you discover them
    ]
    
    for path in known_paths:
        url = BASE_URL + path
        print(f"Scanning: {url}")
        try:
            resp = session.get(url, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.lower().endswith('.pdf'):
                    full_url = BASE_URL + href if href.startswith('/') else href
                    filename = full_url.split('/')[-1]
                    pdf_links.append((full_url, filename))
        except Exception as e:
            print(f"Error scanning {url}: {e}")
        time.sleep(1)
    
    # Deduplicate
    unique = {url: fname for url, fname in pdf_links}
    return list(unique.items())

def download_pdf(url, filename):
    filepath = PDF_FOLDER / filename
    if filepath.exists():
        print(f"✅ Already exists: {filename}")
        return True
    
    print(f"Downloading: {filename}")
    try:
        resp = session.get(url, stream=True, timeout=120)
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
    print("🔍 Collecting PDFs from official DOJ Epstein Library...")
    links = get_pdf_links()
    print(f"Found {len(links)} PDFs")
    
    for url, fname in tqdm(links):
        download_pdf(url, fname)
        time.sleep(0.8)  # Respectful rate limit

if __name__ == "__main__":
    main()
