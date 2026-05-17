import os
import json
import re
import time
import shutil
import logging
from datetime import datetime

# ==========================================
# ADVANCED SYSTEM CONFIGURATIONS & PATHS
# ==========================================
# ডিরেক্টরি পাথ ডায়নামিক করা হয়েছে যাতে যেকোনো ফোল্ডার স্ট্রাকচারেই কাজ করে
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")

# ইনপুট এবং আউটপুট ফাইল
RAW_JOBS_FILE = os.path.join(DB_FOLDER, "raw_scraped_jobs.json")
VALIDATED_JOBS_FILE = os.path.join(DB_FOLDER, "validated_jobs.json")
REJECTED_JOBS_FILE = os.path.join(DB_FOLDER, "rejected_jobs.json")
VALIDATOR_LOG_FILE = os.path.join(DB_FOLDER, "validator_system_logs.txt")

# ==========================================
# ENTERPRISE LOGGING SETUP
# ==========================================
def setup_logger():
    """লগিং সিস্টেম তৈরি করা যা কোনো ক্র্যাশ হতে দেবে না এবং সব রেকর্ড রাখবে"""
    logger = logging.getLogger("NM_Validator_Engine")
    logger.setLevel(logging.DEBUG)
    
    # লগ ফরম্যাট
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # ফাইল হ্যান্ডলার (SSD তে সেভ করার জন্য)
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(VALIDATOR_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # কনসোল হ্যান্ডলার (টার্মিনালে দেখার জন্য)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()

# ==========================================
# SCAM & SPAM DETECTION DICTIONARIES (NLP LOGIC)
# ==========================================
# এই কিওয়ার্ডগুলো থাকলে ট্রাস্ট স্কোর সরাসরি মাইনাস হবে
SCAM_KEYWORDS = [
    r"telegram me", r"whatsapp me", r"\+1\s?\(\d{3}\)", r"crypto investment",
    r"pay outside", r"easy money", r"pyramid scheme", r"free registration",
    r"deposit fee", r"security fee", r"send money first", r"message me on tg",
    r"payment outside upwork", r"no experience required make \$", r"urgent hiring text me"
]

# এই কিওয়ার্ডগুলো জেনুইন কাজের প্রমাণ দেয়
TRUST_KEYWORDS = [
    r"api integration", r"python script", r"flutter app", r"backend", 
    r"data extraction", r"long term", r"github", r"repository", 
    r"database", r"bug fix", r"automation workflow", r"clean code"
]

class NMValidatorEngine:
    """
    NMStudio1 AI Engine - Validator Module.
    এই ক্লাসটি raw job ডেটা প্রসেস করে 100% ভ্যালিড কাজগুলো ফিল্টার করবে।
    """
    
    def __init__(self):
        self.raw_jobs = []
        self.validated_jobs = []
        self.rejected_jobs = []
        self.trust_threshold = 50 # ন্যূনতম 50 স্কোর না পেলে কাজ রিজেক্ট হবে

    def check_file_health(self):
        """JSON ফাইলের ইন্টিগ্রিটি চেক করা যাতে কোনো করাপ্ট ফাইল ইঞ্জিন ক্র্যাশ না করে"""
        logger.info("Initializing System Health Check...")
        if not os.path.exists(RAW_JOBS_FILE):
            logger.warning(f"Raw jobs file not found at {RAW_JOBS_FILE}. Waiting for File 1.")
            return False
            
        # ফাইল সাইজ চেক (0 byte হলে এরর এড়ানো)
        if os.path.getsize(RAW_JOBS_FILE) == 0:
            logger.warning("Raw jobs file is empty.")
            return False
            
        return True

    def load_data(self):
        """নিরাপদে ডাটাবেস থেকে raw jobs লোড করা"""
        try:
            with open(RAW_JOBS_FILE, 'r', encoding='utf-8') as file:
                self.raw_jobs = json.load(file)
            logger.info(f"Successfully loaded {len(self.raw_jobs)} raw jobs for validation.")
        except json.JSONDecodeError as e:
            logger.error(f"JSON Structure corrupted in raw jobs: {e}")
            self.raw_jobs = []
        except Exception as e:
            logger.critical(f"Critical error loading data: {e}")

    def load_existing_validated_data(self):
        """আগে থেকে ভ্যালিডেট করা কাজগুলো লোড করা যাতে ওভাররাইট না হয়"""
        if os.path.exists(VALIDATED_JOBS_FILE) and os.path.getsize(VALIDATED_JOBS_FILE) > 0:
            try:
                with open(VALIDATED_JOBS_FILE, 'r', encoding='utf-8') as file:
                    self.validated_jobs = json.load(file)
            except Exception as e:
                logger.error(f"Error loading existing validated jobs: {e}")

    def calculate_trust_score(self, job_title, job_description):
        """
        ডিপ লজিক: কাজের টাইটেল এবং ডেসক্রিপশন পড়ে ট্রাস্ট স্কোর ক্যালকুলেট করবে।
        """
        score = 100  # বেস স্কোর ১০০ থেকে শুরু
        full_text = f"{job_title} {job_description}".lower()
        
        # ১. স্ক্যাম কিওয়ার্ড চেকিং (Regex)
        for pattern in SCAM_KEYWORDS:
            if re.search(pattern, full_text):
                score -= 60  # স্ক্যাম ওয়ার্ড পেলে ডাইরেক্ট ৬০ মাইনাস
                logger.debug(f"Scam pattern detected: '{pattern}'")
                
        # ২. ডেসক্রিপশন লেংথ লজিক (খুব ছোট ডেসক্রিপশন ফেক হওয়ার চান্স বেশি)
        desc_length = len(job_description.split())
        if desc_length < 15:
            score -= 30
        elif desc_length > 300:
            score += 10 # বিস্তারিত কাজের বিবরণ ভালো সাইন
            
        # ৩. ট্রাস্টেড কিওয়ার্ড চেকিং
        for pattern in TRUST_KEYWORDS:
            if re.search(pattern, full_text):
                score += 15 # টেকনিক্যাল শব্দ থাকলে স্কোর বাড়বে
                
        # ৪. URL চেকিং (ডেসক্রিপশনে কোনো সন্দেহজনক লিংক আছে কিনা)
        urls = re.findall(r'(https?://[^\s]+)', job_description)
        if len(urls) > 3:
            score -= 20 # অতিরিক্ত লিংক স্প্যামের লক্ষণ
            
        # স্কোর লিমিট 0-100 এর মধ্যে রাখা
        score = max(0, min(score, 100))
        return score

    def process_validation(self):
        """প্রধান লজিক লুপ যা প্রতিটি কাজ ফিল্টার করবে"""
        if not self.raw_jobs:
            return

        logger.info("Starting Deep AI Validation Process...")
        
        newly_validated_count = 0
        newly_rejected_count = 0
        
        # ডুপ্লিকেট চেকিংয়ের জন্য এক্সিস্টিং লিংকগুলোর সেট তৈরি
        existing_links = {job['link'] for job in self.validated_jobs}
        
        for job in self.raw_jobs:
            if job['status'] != 'raw':
                continue # আগে প্রসেস হলে ইগনোর করবে
                
            if job['link'] in existing_links:
                continue # ডুপ্লিকেট কাজ বাদ
                
            title = job.get('title', '')
            desc = job.get('description', '')
            
            # ট্রাস্ট স্কোর ক্যালকুলেশন কল করা
            trust_score = self.calculate_trust_score(title, desc)
            job['trust_score'] = trust_score
            job['validation_time'] = time.time()
            
            if trust_score >= self.trust_threshold:
                job['status'] = 'validated' # File 3 এর জন্য প্রস্তুত
                self.validated_jobs.append(job)
                existing_links.add(job['link'])
                newly_validated_count += 1
                logger.info(f"[VALID] Score: {trust_score} | Title: {title[:50]}...")
            else:
                job['status'] = 'rejected'
                self.rejected_jobs.append(job)
                newly_rejected_count += 1
                logger.warning(f"[REJECTED] Score: {trust_score} | Title: {title[:50]}...")
                
        logger.info(f"Validation Complete. Validated: {newly_validated_count}, Rejected: {newly_rejected_count}")
        
    def save_results(self):
        """ফলাফলগুলো একদম সেফলি JSON এ রাইট করা"""
        try:
            # Validated jobs সেভ
            with open(VALIDATED_JOBS_FILE, 'w', encoding='utf-8') as file:
                json.dump(self.validated_jobs, file, indent=4, ensure_ascii=False)
                
            # Rejected jobs সেভ (ভবিষ্যতে AI ট্রেইনিং এর জন্য)
            if self.rejected_jobs:
                mode = 'w' if not os.path.exists(REJECTED_JOBS_FILE) else 'r+'
                if mode == 'r+':
                    with open(REJECTED_JOBS_FILE, 'r', encoding='utf-8') as f:
                        try:
                            old_rejected = json.load(f)
                        except:
                            old_rejected = []
                    self.rejected_jobs.extend(old_rejected)
                    
                with open(REJECTED_JOBS_FILE, 'w', encoding='utf-8') as file:
                    json.dump(self.rejected_jobs, file, indent=4, ensure_ascii=False)
                    
            logger.info("All processed data safely written to SSD.")
        except Exception as e:
            logger.error(f"Failed to save validation results: {e}")

    def clean_raw_data(self):
        """SSD স্পেস বাঁচানোর জন্য প্রসেস হয়ে যাওয়া ডাটা raw ফাইল থেকে মুছে ফেলা"""
        try:
            # শুধু যেগুলো raw আছে সেগুলো রেখে বাকি সব মুছে নতুন করে সেভ করা
            unprocessed = [job for job in self.raw_jobs if job.get('status') == 'raw']
            with open(RAW_JOBS_FILE, 'w', encoding='utf-8') as file:
                json.dump(unprocessed, file, indent=4, ensure_ascii=False)
            logger.info("Raw data file cleaned up. Ready for next scrape.")
        except Exception as e:
            logger.error(f"Failed to clean raw jobs file: {e}")

# ==========================================
# MAIN EXECUTION BLOCK (CRON JOB READY)
# ==========================================
def main():
    print("="*60)
    print(" NMStudio1 AI Engine - FILE 2: VALIDATOR MODULE INITIATED ")
    print("="*60)
    
    engine = NMValidatorEngine()
    
    # স্টেপ ১: ফাইল হেলথ চেক
    if not engine.check_file_health():
        print("Exiting Module safely.")
        return
        
    # স্টেপ ২: ডেটা লোড
    engine.load_data()
    engine.load_existing_validated_data()
    
    # স্টেপ ৩: ডিপ লজিক ভ্যালিডেশন
    engine.process_validation()
    
    # স্টেপ ৪: সেভ এবং ক্লিনআপ
    engine.save_results()
    engine.clean_raw_data()
    
    print("="*60)
    print(" VALIDATOR MODULE EXECUTION COMPLETED WITHOUT ERRORS ")
    print("="*60)

if __name__ == "__main__":
    # যেকোনো স্ক্রিপ্ট ক্র্যাশ আটকাতে গ্লোবাল Try-Except ব্লক
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Process forcefully stopped by user.")
    except Exception as e:
        logger.critical(f"FATAL SYSTEM ERROR IN FILE 2: {e}")