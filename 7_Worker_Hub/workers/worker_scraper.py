import os
import re
import csv
import json
import time
import logging
import traceback
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import google.generativeai as genai

# ==========================================
# ENTERPRISE PATH & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
DELIVERABLES_FOLDER = os.path.join(DB_FOLDER, "Completed_Deliverables")

# Gemini API Configuration (To parse messy HTML into structured data)
GEMINI_API_KEY = "AIzaSyCtGJWf-tb0Y6YTF3y86YoE3y5lZUNljTs"

# ==========================================
# WORKER SPECIFIC LOGGING
# ==========================================
def setup_scraper_logger():
    logger = logging.getLogger("NM_Worker_Scraper")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [SCRAPER_WORKER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    log_file = os.path.join(DB_FOLDER, "worker_scraper_logs.txt")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_scraper_logger()

# ==========================================
# HYBRID SCRAPING & DATA STRUCTURING ENGINE
# ==========================================
class ScraperWorkerEngine:
    def __init__(self):
        self.deliverables_dir = DELIVERABLES_FOLDER
        if not os.path.exists(self.deliverables_dir):
            os.makedirs(self.deliverables_dir)
            
        self.is_api_ready = self.initialize_api()

    def initialize_api(self):
        """Gemini API ফর অ্যাডভান্সড ডেটা ক্লিনিং"""
        if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
            logger.warning("Gemini API Key missing. Fallback to basic HTML extraction.")
            return False
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            return True
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")
            return False

    def extract_target_urls(self, text):
        """ক্লায়েন্টের ডেসক্রিপশন থেকে টার্গেট ওয়েবসাইটের লিংক খুঁজে বের করা"""
        urls = re.findall(r'(https?://[^\s]+)', text)
        return list(set(urls))

    def identify_required_format(self, text):
        """ক্লায়েন্ট ডেটা কোন ফরম্যাটে চাইছে (CSV, JSON, Text) তা নির্ধারণ করা"""
        text_lower = text.lower()
        if "csv" in text_lower or "excel" in text_lower or "spreadsheet" in text_lower:
            return "csv"
        elif "json" in text_lower or "api format" in text_lower:
            return "json"
        else:
            return "txt" # Default

    def basic_static_scrape(self, url):
        """নরমাল ওয়েবসাইট থেকে Requests দিয়ে দ্রুত ডেটা টানা"""
        logger.info(f"Attempting static scrape for: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0'}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "lxml")
                # অপ্রয়োজনীয় ট্যাগ মুছে ফেলা (RAM বাঁচানোর জন্য)
                for tag in soup(["script", "style", "nav", "footer", "svg"]):
                    tag.extract()
                return soup.get_text(separator=' ', strip=True)[:15000] # মেমরি লিমিট
            else:
                logger.warning(f"Static scrape failed with status code: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Static scrape error: {e}")
            return None

    def dynamic_browser_scrape(self, url):
        """জাভাস্ক্রিপ্ট রেন্ডার করা বা সিকিউর সাইটের জন্য Playwright হেডলেস ব্রাউজার"""
        logger.info(f"Switching to Dynamic Browser Engine for: {url}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0")
                
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(3) # JS লোড হওয়ার জন্য ওয়েট করা
                
                # ডামি স্ক্রোল
                page.mouse.wheel(0, 1000)
                time.sleep(2)
                
                content = page.content()
                browser.close()
                
                soup = BeautifulSoup(content, "lxml")
                for tag in soup(["script", "style", "noscript"]):
                    tag.extract()
                return soup.get_text(separator=' ', strip=True)[:15000]
        except PlaywrightTimeoutError:
            logger.error("Playwright Timeout. Site is too slow or protected.")
            return None
        except Exception as e:
            logger.error(f"Dynamic scrape failed: {e}")
            return None

    def ai_data_structuring(self, raw_text, task_description):
        """Gemini AI ব্যবহার করে অগোছালো টেক্সটকে সুন্দর JSON এ সাজানো"""
        if not self.is_api_ready:
            return {"raw_data": raw_text[:1000] + "...(AI unavailable)"}

        prompt = f"""
You are an expert Data Engineer. I will provide you with raw, messy text scraped from a website, and the client's instructions.
Your job is to extract the relevant data and format it STRICTLY as a JSON array of objects.

CLIENT INSTRUCTION: {task_description}

RAW SCRAPED TEXT (Truncated):
{raw_text[:10000]}

OUTPUT FORMAT:
Return ONLY valid JSON. No markdown, no explanations. 
Example: [{{"name": "Item 1", "price": "$10"}}, {{"name": "Item 2", "price": "$20"}}]
"""
        try:
            response = self.model.generate_content(prompt)
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            structured_data = json.loads(json_text)
            return structured_data
        except Exception as e:
            logger.error(f"AI Structuring failed: {e}")
            return [{"raw_extracted_text": raw_text[:1000]}] # Fallback

    def save_to_format(self, job_id, data, format_type):
        """ডেটাবেস বা ফাইলে সেভ করা (SSD স্পেস বাঁচিয়ে)"""
        safe_name = f"scraped_data_{job_id.split('/')[-1] if '/' in job_id else job_id}"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == '_')
        
        try:
            if format_type == "csv" and isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                file_path = os.path.join(self.deliverables_dir, f"{safe_name}.csv")
                keys = data[0].keys()
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    dict_writer = csv.DictWriter(f, fieldnames=keys)
                    dict_writer.writeheader()
                    dict_writer.writerows(data)
                    
            elif format_type == "json":
                file_path = os.path.join(self.deliverables_dir, f"{safe_name}.json")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                    
            else: # Default txt
                file_path = os.path.join(self.deliverables_dir, f"{safe_name}.txt")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(str(data))
                    
            logger.info(f"Data successfully formatted and saved to: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save formatted data: {e}")
            return None

# ==========================================
# STANDARD WORKER ENTRY POINT (CALLED BY FILE 7)
# ==========================================
def execute_task(task_data):
    """Main Hub (File 7) এই ফাংশনটিকে কল করবে।"""
    logger.info(f"--- Scraper Worker received task: {task_data.get('title')} ---")
    
    engine = ScraperWorkerEngine()
    
    task_desc = task_data.get('task_description', '')
    job_id = task_data.get('job_id', str(time.time()))
    
    # ১. ইউআরএল বের করা
    target_urls = engine.extract_target_urls(task_desc)
    
    if not target_urls:
        return {
            "status": "failed",
            "error": "No target URLs found in the task description to scrape.",
            "retry_allowed": False
        }

    target_url = target_urls[0] # প্রথম ইউআরএল টার্গেট করব
    output_format = engine.identify_required_format(task_desc)
    
    # ২. ডেটা স্ক্র্যাপিং (প্রথমে স্ট্যাটিক, ফেইল করলে ডায়নামিক)
    raw_text = engine.basic_static_scrape(target_url)
    
    if not raw_text or len(raw_text) < 100: # যদি স্ট্যাটিক কাজ না করে
        raw_text = engine.dynamic_browser_scrape(target_url)
        
    if not raw_text:
        return {
            "status": "failed",
            "error": f"Failed to extract any content from {target_url}. Site might be strictly blocked.",
            "retry_allowed": True
        }

    # ৩. এআই দিয়ে ডেটা ক্লিন ও স্ট্রাকচার করা
    logger.info("Raw data extracted. Sending to AI for JSON structuring...")
    structured_data = engine.ai_data_structuring(raw_text, task_desc)
    
    # ৪. ক্লায়েন্টের পছন্দের ফরম্যাটে সেভ করা
    deliverable_path = engine.save_to_format(job_id, structured_data, output_format)
    
    if deliverable_path:
        # সফল হলে ডেটা হাবকে পাঠিয়ে দেওয়া
        return {
            "status": "success",
            "data": {
                "deliverable_path": deliverable_path,
                "format_used": output_format,
                "records_extracted": len(structured_data) if isinstance(structured_data, list) else 1,
                "message": f"Successfully scraped {target_url} and saved as {output_format.upper()}."
            },
            "retry_allowed": False
        }
    else:
        return {
            "status": "failed",
            "error": "Data scraped but failed to write to SSD.",
            "retry_allowed": True
        }

# ==========================================
# LOCAL TESTING BLOCK
# ==========================================
if __name__ == "__main__":
    print("Running diagnostic test for worker_scraper.py...")
    dummy_task = {
        "job_id": "scrape_test_99",
        "title": "Scrape remote python jobs",
        "task_description": "Go to https://remoteok.com/remote-python-jobs and extract the job titles and companies. Save it as a CSV file."
    }
    
    result = execute_task(dummy_task)
    print(json.dumps(result, indent=4))