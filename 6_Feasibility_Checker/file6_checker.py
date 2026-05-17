import os
import json
import time
import re
import logging
import traceback
from datetime import datetime

# ==========================================
# ENTERPRISE PATH CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")

# Input & Output Data Files
PARSED_TASKS_FILE = os.path.join(DB_FOLDER, "parsed_tasks.json")
HUB_QUEUE_FILE = os.path.join(DB_FOLDER, "hub_queue.json") # File 7 এর জন্য
REJECTED_TASKS_FILE = os.path.join(DB_FOLDER, "rejected_jobs.json")
CHECKER_LOG_FILE = os.path.join(DB_FOLDER, "feasibility_checker_logs.txt")

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_checker_logger():
    """Fail-proof Logging System"""
    logger = logging.getLogger("NM_Feasibility_Checker")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [FEASIBILITY] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(CHECKER_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_checker_logger()

# ==========================================
# ADVANCED AI CAPABILITY MATRIX (THE BRAIN)
# ==========================================
class CapabilityMatrix:
    """
    এই ক্লাসটি ডিফাইন করে আমাদের এআই কোন কাজগুলো করতে পারবে এবং কোনগুলো পারবে না।
    """
    
    # যে কাজগুলো AI সরাসরি করতে পারে না (Physical, Audio/Video, Complex Visuals)
    IMPOSSIBLE_KEYWORDS = [
        r"\bvideo editing\b", r"\blogo design\b", r"\bphotoshop\b", r"\billustrator\b",
        r"\bui/ux\b", r"\bfigma\b", r"\bcanva\b", r"\bvoice over\b", r"\baudacity\b",
        r"\bpremiere pro\b", r"\bafter effects\b", r"\bcall clients\b", r"\bphone call\b",
        r"\bphysical delivery\b", r"\b3d modeling\b", r"\bblender\b", r"\bautocad\b",
        r"\bzoom meeting\b", r"\bscreen share\b", r"\bgraphic design\b", r"\bphoto editing\b"
    ]

    # যে কাজগুলোর জন্য আমাদের স্পেসিফিক ওয়ার্কার (File 7) রেডি আছে
    ROUTING_RULES = {
        "worker_python": {
            "keywords": [r"\bpython\b", r"\bscript\b", r"\bautomation\b", r"\bbot\b", r"\bflutter\b", r"\bdart\b", r"\bapi integration\b"],
            "base_score": 30
        },
        "worker_scraper": {
            "keywords": [r"\bweb scraping\b", r"\bdata extraction\b", r"\bbeautifulsoup\b", r"\bselenium\b", r"\bcrawling\b", r"\bdata entry\b", r"\bexcel\b"],
            "base_score": 30
        },
        "worker_writer": {
            "keywords": [r"\barticle\b", r"\bblog post\b", r"\brewrite\b", r"\bsummarize\b", r"\bcontent writing\b", r"\bseo writing\b"],
            "base_score": 25
        }
    }

# ==========================================
# FEASIBILITY & ROUTING ENGINE
# ==========================================
class NMFeasibilityEngine:
    def __init__(self):
        self.parsed_tasks = []
        self.approved_for_hub = []
        self.rejected_tasks = []
        self.approval_threshold = 60 # নূন্যতম 60% কনফিডেন্স পেলে কাজ এক্সেপ্ট হবে

    def system_health_check(self):
        """ডাটাবেসের ইন্টিগ্রিটি চেক করা"""
        logger.info("Initiating Feasibility Diagnostic Check...")
        if not os.path.exists(PARSED_TASKS_FILE):
            logger.warning(f"File 5 Output not found at {PARSED_TASKS_FILE}. Halting execution.")
            return False
        if os.path.getsize(PARSED_TASKS_FILE) == 0:
            logger.warning("Parsed tasks file is empty. No tasks to evaluate.")
            return False
        return True

    def load_parsed_data(self):
        """File 5 এর ডাটা নিরাপদে লোড করা"""
        try:
            with open(PARSED_TASKS_FILE, 'r', encoding='utf-8') as f:
                self.parsed_tasks = json.load(f)
            logger.info(f"Loaded {len(self.parsed_tasks)} parsed tasks for deep feasibility check.")
        except Exception as e:
            logger.critical(f"Data corruption detected in Parsed Tasks: {e}")
            self.parsed_tasks = []

        # আগের পেন্ডিং হাব ডাটা লোড করা
        if os.path.exists(HUB_QUEUE_FILE):
            try:
                with open(HUB_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    self.approved_for_hub = json.load(f)
            except:
                self.approved_for_hub = []

    def evaluate_task(self, task):
        """
        ডিপ লজিক: একটি কাজের ডেসক্রিপশন পড়ে কনফিডেন্স স্কোর বের করা 
        এবং সঠিক ওয়ার্কার (Python/Scraper/Writer) সিলেক্ট করা।
        """
        full_text = f"{task.get('title', '')} {task.get('task_description', '')} {' '.join(task.get('required_skills', []))}".lower()
        
        evaluation_result = {
            "is_feasible": False,
            "confidence_score": 0,
            "assigned_worker": None,
            "rejection_reason": None
        }

        # লজিক ১: ইম্পসিবল টাস্ক চেকিং (Hard Rejection)
        for pattern in CapabilityMatrix.IMPOSSIBLE_KEYWORDS:
            if re.search(pattern, full_text):
                evaluation_result["rejection_reason"] = f"Requires human-only/visual task ({pattern.strip(r'\\b')})"
                logger.warning(f"[HARD REJECT] {task.get('title')} -> Reason: {evaluation_result['rejection_reason']}")
                return evaluation_result

        # লজিক ২: স্কিল ও ওয়ার্কার ম্যাচিং এবং স্কোরিং
        best_worker = None
        highest_score = 0
        
        for worker_name, rules in CapabilityMatrix.ROUTING_RULES.items():
            current_score = 0
            for pattern in rules["keywords"]:
                if re.search(pattern, full_text):
                    current_score += rules["base_score"]
            
            if current_score > highest_score:
                highest_score = current_score
                best_worker = worker_name

        # লজিক ৩: ডেসক্রিপশন কোয়ালিটি স্কোর (খুব ছোট ডেসক্রিপশন মানে কাজ ক্লিয়ার না)
        word_count = len(full_text.split())
        if 20 < word_count < 500:
            highest_score += 20 # পারফেক্ট লেংথ
        elif word_count <= 20:
            highest_score -= 10 # অতিরিক্ত ছোট, রিস্কি
            
        evaluation_result["confidence_score"] = min(100, highest_score)

        # ফাইনাল ডিসিশন মেকিং
        if evaluation_result["confidence_score"] >= self.approval_threshold and best_worker:
            evaluation_result["is_feasible"] = True
            evaluation_result["assigned_worker"] = best_worker
            logger.info(f"[APPROVED] {task.get('title')[:30]} | Score: {evaluation_result['confidence_score']}% | Assigned: {best_worker}")
        else:
            evaluation_result["rejection_reason"] = f"Low confidence score ({evaluation_result['confidence_score']}%) or no matching worker."
            logger.info(f"[REJECTED] {task.get('title')[:30]} | Reason: {evaluation_result['rejection_reason']}")

        return evaluation_result

    def process_feasibility(self):
        """সবগুলো কাজের ওপর লজিক ইঞ্জিন রান করা"""
        if not self.parsed_tasks:
            return

        logger.info("Initializing Neural Match & Routing Engine...")
        newly_approved = 0
        newly_rejected = 0
        
        for task in self.parsed_tasks:
            # কাজ যদি আগে থেকেই এক্সেপ্টেড থাকে
            if any(t.get('job_id') == task.get('job_id') for t in self.approved_for_hub):
                continue

            evaluation = self.evaluate_task(task)
            
            if evaluation["is_feasible"]:
                # টাস্কের সাথে ওয়ার্কারের নাম এবং স্কোর যুক্ত করে হাবে পাঠানো
                task["feasibility_score"] = evaluation["confidence_score"]
                task["assigned_worker"] = evaluation["assigned_worker"]
                task["status"] = "ready_for_execution"
                self.approved_for_hub.append(task)
                newly_approved += 1
            else:
                task["rejection_reason"] = evaluation["rejection_reason"]
                task["status"] = "rejected_by_ai"
                self.rejected_tasks.append(task)
                newly_rejected += 1

        logger.info(f"Engine Cycle Complete. Approved: {newly_approved} | Rejected: {newly_rejected}")

    def save_and_cleanup(self):
        """ডাটাবেস সিকিউরলি আপডেট করা এবং SSD স্পেস ফ্রি করা"""
        # ১. Approved Tasks সেভ করা (File 7 এর জন্য)
        if self.approved_for_hub:
            try:
                with open(HUB_QUEUE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.approved_for_hub, f, indent=4, ensure_ascii=False)
                logger.info("Approved tasks routed to File 7 (Worker Hub) successfully.")
            except Exception as e:
                logger.error(f"Failed to save HUB_QUEUE: {e}")

        # ২. Rejected Tasks সেভ করা (ভবিষ্যতে AI ট্রেইনিং এর জন্য কাজে লাগবে)
        if self.rejected_tasks:
            try:
                mode = 'r+' if os.path.exists(REJECTED_TASKS_FILE) else 'w'
                if mode == 'r+':
                    with open(REJECTED_TASKS_FILE, 'r', encoding='utf-8') as f:
                        try:
                            existing_rejected = json.load(f)
                        except:
                            existing_rejected = []
                    self.rejected_tasks.extend(existing_rejected)
                    
                with open(REJECTED_TASKS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.rejected_tasks, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save REJECTED_TASKS: {e}")

        # ৩. SSD Clean-up: Parsed tasks ফাইল ফাঁকা করে দেওয়া কারণ ডেটা প্রসেস হয়ে গেছে
        try:
            with open(PARSED_TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f) # Empty Array
            logger.info("Storage Optimized: Cleaned parsed_tasks.json")
        except Exception as e:
            logger.error(f"Failed to clean parsed tasks file: {e}")

# ==========================================
# MAIN EXECUTION THREAD
# ==========================================
def main():
    print("\n" + "="*75)
    print(" NMStudio1 AI Engine - FILE 6: FEASIBILITY CHECKER MODULE INITIATED ")
    print("="*75)
    
    checker = NMFeasibilityEngine()
    
    if not checker.system_health_check():
        print("System halted safely. Awaiting data from File 5 (Task Reader).")
        return
        
    # Execution Pipeline
    checker.load_parsed_data()
    checker.process_feasibility()
    checker.save_and_cleanup()
    
    print("="*75)
    print(" FEASIBILITY MODULE EXECUTED (DATA SAFELY ROUTED TO FILE 7) ")
    print("="*75 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Module execution interrupted by system administrator.")
    except Exception as e:
        logger.critical(f"FATAL SYSTEM ERROR IN FILE 6: {traceback.format_exc()}")