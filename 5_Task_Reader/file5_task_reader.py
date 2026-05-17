import os
import json
import time
import re
import logging
import traceback
from bs4 import BeautifulSoup

# ==========================================
# ENTERPRISE PATH CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
HTML_DUMP_FOLDER = os.path.join(DB_FOLDER, "Page_Dumps")

# Data Storage Files
ACTIVE_JOBS_FILE = os.path.join(DB_FOLDER, "active_jobs.json")
PARSED_TASKS_FILE = os.path.join(DB_FOLDER, "parsed_tasks.json")
READER_LOG_FILE = os.path.join(DB_FOLDER, "task_reader_logs.txt")

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_reader_logger():
    logger = logging.getLogger("NM_Task_Reader")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [TASK_READER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(READER_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_reader_logger()

# ==========================================
# NLP REGEX EXTRACTION ENGINE
# ==========================================
class RequirementExtractor:
    """
    খুবই অ্যাডভান্সড Regex ইঞ্জিন যা আনস্ট্রাকচারড HTML টেক্সট থেকে
    বাজেট, ডেডলাইন এবং টেকনিক্যাল স্কিল নিখুঁতভাবে এক্সট্রাক্ট করবে।
    """
    
    # স্কিল ডিকশনারি (এই স্কিলগুলো আমাদের সিস্টেম করতে পারবে)
    TARGET_SKILLS = [
        "python", "flutter", "dart", "api", "web scraping", "automation", 
        "data entry", "json", "beautifulsoup", "selenium", "playwright",
        "bot", "script", "backend", "javascript", "html", "css", "crawling"
    ]

    @staticmethod
    def extract_budget(text):
        """টেক্সট থেকে ডলার বা অন্য কারেন্সির বাজেট বের করা"""
        budget_patterns = [
            r'\$[\d,]+(?:\.\d{2})?\s?(?:to|-)?\s?\$?[\d,]+(?:\.\d{2})?', # $500 or $500-$1000
            r'(?:usd|eur)\s?[\d,]+', # USD 500
            r'\$[\d,]+\s?/\s?hr', # $50/hr
            r'budget:?\s?\$[\d,]+', # Budget: $100
            r'₹[\d,]+' # ₹5000 (Indian Rupees)
        ]
        
        found_budgets = []
        for pattern in budget_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_budgets.extend(matches)
            
        return list(set(found_budgets)) if found_budgets else ["Not explicitly mentioned"]

    @staticmethod
    def extract_skills(text):
        """ডেসক্রিপশন থেকে রিকোয়ার্ড স্কিল খুঁজে বের করা"""
        found_skills = set()
        text_lower = text.lower()
        
        # Word boundary দিয়ে স্কিল খোঁজা যাতে ফেক ম্যাচ না হয়
        for skill in RequirementExtractor.TARGET_SKILLS:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.add(skill)
                
        return list(found_skills)

    @staticmethod
    def extract_deadlines(text):
        """কাজের কোনো ডেডলাইন দেওয়া আছে কিনা তা চেক করা"""
        deadline_patterns = [
            r'\b(?:urgent|asap|immediately)\b',
            r'\b(?:within|in)\s\d+\s(?:days|hours|weeks)\b',
            r'\bdeadline:?\s.*?(?=\n|\.)'
        ]
        
        deadlines = []
        for pattern in deadline_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            deadlines.extend(matches)
            
        return list(set(deadlines)) if deadlines else ["Flexible/Not specified"]

# ==========================================
# OFFLINE DOM PARSER ENGINE
# ==========================================
class HTMLParserEngine:
    """অফলাইনে HTML পড়ে শুধু কাজের ইনফরমেশন বের করার লজিক"""
    
    @staticmethod
    def clean_html(html_content):
        """স্ক্রিপ্ট, স্টাইল এবং অপ্রয়োজনীয় ট্যাগ মুছে ফেলে র‍্যাম বাঁচানো"""
        soup = BeautifulSoup(html_content, "lxml")
        
        # অপ্রয়োজনীয় এলিমেন্ট রিমুভ করা
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()
            
        # শুধু মূল টেক্সট এক্সট্রাক্ট করা (অতিরিক্ত স্পেস রিমুভ করে)
        text = soup.get_text(separator=' ')
        cleaned_text = re.sub(r'\s+', ' ', text).strip()
        return cleaned_text, soup

    @staticmethod
    def parse_job_details(html_content):
        """ক্লিন করা টেক্সট থেকে ডাটা এক্সট্রাক্ট করে স্ট্রাকচারড ডিকশনারি বানানো"""
        cleaned_text, soup = HTMLParserEngine.clean_html(html_content)
        
        # Extractor মডিউলের মাধ্যমে ডেটা প্রসেস করা
        budget = RequirementExtractor.extract_budget(cleaned_text)
        skills = RequirementExtractor.extract_skills(cleaned_text)
        deadline = RequirementExtractor.extract_deadlines(cleaned_text)
        
        # ডেসক্রিপশন লিমিট করা (অতিরিক্ত বড় হলে 5000 ক্যারেক্টার পর্যন্ত রাখবে)
        safe_description = cleaned_text[:5000] if len(cleaned_text) > 5000 else cleaned_text
        
        return {
            "extracted_budget": budget,
            "required_skills": skills,
            "deadlines": deadline,
            "full_description": safe_description,
            "word_count": len(cleaned_text.split())
        }

# ==========================================
# MAIN TASK READER CORE
# ==========================================
class NMTaskReaderEngine:
    def __init__(self):
        self.active_jobs = []
        self.parsed_tasks = []

    def system_health_check(self):
        """SSD ফোল্ডার এবং ফাইল স্ট্রাকচার চেক করা"""
        logger.info("Running System Health Check for File 5...")
        if not os.path.exists(ACTIVE_JOBS_FILE) or os.path.getsize(ACTIVE_JOBS_FILE) == 0:
            logger.warning("No active jobs found from File 3. Awaiting data.")
            return False
        if not os.path.exists(HTML_DUMP_FOLDER):
            logger.warning("HTML Dump folder is missing. No data to parse.")
            return False
        return True

    def load_data(self):
        """File 3 থেকে আসা জবগুলো লোড করা"""
        try:
            with open(ACTIVE_JOBS_FILE, 'r', encoding='utf-8') as f:
                self.active_jobs = json.load(f)
            logger.info(f"Successfully loaded {len(self.active_jobs)} active jobs for reading.")
        except Exception as e:
            logger.critical(f"Failed to load active jobs: {e}")
            self.active_jobs = []

        # এক্সিস্টিং পার্স করা কাজ লোড করা (ওভাররাইট এড়ানোর জন্য)
        if os.path.exists(PARSED_TASKS_FILE) and os.path.getsize(PARSED_TASKS_FILE) > 0:
            try:
                with open(PARSED_TASKS_FILE, 'r', encoding='utf-8') as f:
                    self.parsed_tasks = json.load(f)
            except:
                self.parsed_tasks = []

    def process_html_dumps(self):
        """লোকাল ড্রাইভের HTML পড়ে ডাটা এক্সট্রাক্ট করা"""
        if not self.active_jobs:
            return

        logger.info("Initializing Offline Deep DOM Reading Protocol...")
        successful_parses = 0
        jobs_to_keep_active = [] # যেগুলোর কাজ শেষ হয়নি

        for job in self.active_jobs:
            dump_path = job.get('html_dump_path')
            
            # ডাটা ভ্যালিডেশন
            if not dump_path or not os.path.exists(dump_path):
                logger.error(f"Missing HTML dump for job: {job.get('title')}")
                jobs_to_keep_active.append(job)
                continue
                
            try:
                # লোকাল SSD থেকে HTML রিড করা
                logger.debug(f"Reading dumped file: {os.path.basename(dump_path)}")
                with open(dump_path, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()
                    
                # Parser Engine দিয়ে ডাটা স্ট্রাকচার করা
                parsed_data = HTMLParserEngine.parse_job_details(html_content)
                
                # File 6 (Feasibility) এর জন্য ফাইনাল পে-লোড তৈরি
                task_payload = {
                    "job_id": job.get('link'),
                    "title": job.get('title'),
                    "source_url": job.get('link'),
                    "extracted_budget": parsed_data["extracted_budget"],
                    "required_skills": parsed_data["required_skills"],
                    "deadlines": parsed_data["deadlines"],
                    "task_description": parsed_data["full_description"],
                    "status": "ready_for_feasibility_check",
                    "timestamp": time.time()
                }
                
                # ডুপ্লিকেট চেকিং
                if not any(t['job_id'] == task_payload['job_id'] for t in self.parsed_tasks):
                    self.parsed_tasks.append(task_payload)
                    successful_parses += 1
                    logger.info(f"[PARSED SUCCESS] {job.get('title')[:30]}... | Skills: {len(parsed_data['required_skills'])}")
                
                # SSD ক্লিনআপ (240GB লিমিট বাঁচানোর জন্য HTML ডিলিট)
                os.remove(dump_path)
                logger.debug(f"Deleted local HTML dump to conserve SSD space: {os.path.basename(dump_path)}")
                
            except Exception as e:
                logger.error(f"Error parsing job {job.get('title')}: {e}")
                jobs_to_keep_active.append(job) # এরর হলে রেখে দেবে পরের বার ট্রাই করতে

        self.active_jobs = jobs_to_keep_active
        logger.info(f"Parsing complete. Successfully structured {successful_parses} tasks.")

    def save_and_cleanup(self):
        """সব ডাটাবেস সেফলি সেভ এবং আপডেট করা"""
        # File 6 এর জন্য ডাটা সেভ
        try:
            with open(PARSED_TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.parsed_tasks, f, indent=4)
            logger.info("All parsed tasks safely routed to File 6 queue.")
        except Exception as e:
            logger.error(f"Failed to save parsed tasks: {e}")

        # Active Jobs আপডেট (যেগুলো প্রসেস হয়ে গেছে সেগুলো বাদ দিয়ে)
        try:
            with open(ACTIVE_JOBS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.active_jobs, f, indent=4)
            logger.info("Active jobs database state updated.")
        except Exception as e:
            logger.error(f"Failed to update active jobs file: {e}")

# ==========================================
# EXECUTION TRIGGER (CRON-READY)
# ==========================================
def main():
    print("\n" + "="*70)
    print(" NMStudio1 AI Engine - FILE 5: TASK READER MODULE INITIATED ")
    print("="*70)
    
    reader = NMTaskReaderEngine()
    
    if not reader.system_health_check():
        print("System safely halting. Awaiting HTML dump data from File 3.")
        return
        
    reader.load_data()
    reader.process_html_dumps()
    reader.save_and_cleanup()
    
    print("="*70)
    print(" TASK READER EXECUTION COMPLETED (MEMORY SAFELY CLEANED) ")
    print("="*70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Execution interrupted manually.")
    except Exception as e:
        logger.critical(f"FATAL SYSTEM FAILURE IN FILE 5: {traceback.format_exc()}")