import os
import json
import time
import requests
from bs4 import BeautifulSoup

# ==========================================
# CONFIGURATIONS & PATHS
# ==========================================
# মেইন ডিরেক্টরি থেকে Database_Logs ফোল্ডারের পাথ সেট করা হচ্ছে
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
RAW_JOBS_FILE = os.path.join(DB_FOLDER, "raw_scraped_jobs.json")
ERROR_LOG_FILE = os.path.join(DB_FOLDER, "error_logs.txt")

# যেসব সোর্স থেকে কাজ খোঁজা হবে (উদাহরণস্বরূপ RSS ফিড)
TARGET_SOURCES = [
    {
        "name": "Freelance_Python_RSS",
        "url": "https://cragslist.org/search/cpg?format=rss", # ডামি URL, এখানে আসল Upwork/Reddit RSS বসবে
        "type": "rss"
    },
    {
        "name": "Remote_Data_Entry_Jobs",
        "url": "https://remoteok.com/api", # RemoteOK API
        "type": "json"
    }
]

# ==========================================
# DIRECTORY & LOGGING SETUP
# ==========================================
def setup_directories():
    """Database_Logs ফোল্ডার না থাকলে তৈরি করবে।"""
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        print(f"[INFO] Created directory: {DB_FOLDER}")

def log_error(error_msg):
    """যেকোনো এরর হলে তা error_logs.txt ফাইলে প্লেইন টেক্সট হিসেবে সেভ করবে।"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [File1_Scraper] {error_msg}\n")

# ==========================================
# SCRAPING LOGIC
# ==========================================
def fetch_jobs_from_rss(source_name, url):
    """RSS ফিড থেকে কাজের ডেটা এক্সট্রাক্ট করবে BeautifulSoup ব্যবহার করে।"""
    jobs = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml') # XML/RSS পার্স করার জন্য
            items = soup.find_all('item')
            
            for item in items:
                job = {
                    "source": source_name,
                    "title": item.title.text if item.title else "No Title",
                    "link": item.link.text if item.link else "No Link",
                    "description": item.description.text if item.description else "No Description",
                    "timestamp": time.time(),
                    "status": "raw" # এই স্ট্যাটাস দেখেই Validator ফাইল বুঝবে একে চেক করতে হবে
                }
                jobs.append(job)
            print(f"[SUCCESS] Scraped {len(jobs)} jobs from {source_name}")
        else:
            log_error(f"Failed to fetch {url}. Status Code: {response.status_code}")
            
    except Exception as e:
        log_error(f"Error scraping {source_name}: {str(e)}")
        
    return jobs

def fetch_jobs_from_api(source_name, url):
    """JSON API থেকে সরাসরি কাজের ডেটা এক্সট্রাক্ট করবে।"""
    jobs = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # RemoteOK API structure check
            for item in data[1:]: # প্রথম আইটেম লিগ্যাল নোটিশ থাকে সাধারণত
                job = {
                    "source": source_name,
                    "title": item.get("position", "No Title"),
                    "link": item.get("url", "No Link"),
                    "description": item.get("description", "No Description"),
                    "timestamp": time.time(),
                    "status": "raw"
                }
                jobs.append(job)
            print(f"[SUCCESS] Scraped {len(jobs)} jobs from {source_name}")
        else:
            log_error(f"Failed to fetch {url}. Status Code: {response.status_code}")
            
    except Exception as e:
        log_error(f"Error fetching API {source_name}: {str(e)}")
        
    return jobs

# ==========================================
# DATA STORAGE (JSON)
# ==========================================
def save_scraped_data(new_jobs):
    """নতুন পাওয়া কাজগুলো raw_scraped_jobs.json ফাইলে সেভ করবে।"""
    if not new_jobs:
        print("[INFO] No new jobs to save.")
        return

    existing_jobs = []
    if os.path.exists(RAW_JOBS_FILE):
        try:
            with open(RAW_JOBS_FILE, "r", encoding="utf-8") as f:
                existing_jobs = json.load(f)
        except json.JSONDecodeError:
            log_error("JSON decode error in raw_scraped_jobs.json. Starting fresh.")

    # ডুপ্লিকেট চেকিং লজিক (একই লিংক আগে থাকলে সেভ করবে না)
    existing_links = {job['link'] for job in existing_jobs}
    added_count = 0
    
    for job in new_jobs:
        if job['link'] not in existing_links:
            existing_jobs.append(job)
            added_count += 1

    # ডেটা সেভ করা
    with open(RAW_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_jobs, f, indent=4, ensure_ascii=False)
        
    print(f"[SAVED] {added_count} new unique jobs added to {RAW_JOBS_FILE}.")

# ==========================================
# MAIN EXECUTION PROCESS
# ==========================================
def main():
    print("--- NM_AutoWorker_AI: File 1 (Explorer) Started ---")
    setup_directories()
    
    all_extracted_jobs = []
    
    for source in TARGET_SOURCES:
        print(f"[ACTION] Scanning target: {source['name']}...")
        if source['type'] == 'rss':
            jobs = fetch_jobs_from_rss(source['name'], source['url'])
            all_extracted_jobs.extend(jobs)
        elif source['type'] == 'json':
            jobs = fetch_jobs_from_api(source['name'], source['url'])
            all_extracted_jobs.extend(jobs)
            
        time.sleep(2) # সার্ভারে চাপ কমানোর জন্য ডিলে
        
    save_scraped_data(all_extracted_jobs)
    print("--- File 1 Execution Completed. Waiting for File 2 (Validator) ---\n")

if __name__ == "__main__":
    main()