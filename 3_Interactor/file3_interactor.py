import os
import json
import time
import random
import logging
import traceback
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==========================================
# ENTERPRISE PATH CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")

# Input / Output Files
VALIDATED_JOBS_FILE = os.path.join(DB_FOLDER, "validated_jobs.json")
ACTIVE_JOBS_FILE = os.path.join(DB_FOLDER, "active_jobs.json")
ERROR_LOG_FILE = os.path.join(DB_FOLDER, "error_logs.txt")
HTML_DUMP_FOLDER = os.path.join(DB_FOLDER, "Page_Dumps") # File 5 এর জন্য
PENDING_ACTION_FILE = os.path.join(DB_FOLDER, "pending_human_action.json") # File 4 এর জন্য

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_interactor_logger():
    logger = logging.getLogger("NM_Interactor_Engine")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [INTERACTOR] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    if not os.path.exists(HTML_DUMP_FOLDER):
        os.makedirs(HTML_DUMP_FOLDER)
        
    file_handler = logging.FileHandler(os.path.join(DB_FOLDER, "interactor_system_logs.txt"), encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_interactor_logger()

# ==========================================
# BOT STEALTH & HUMAN SIMULATION MODULE
# ==========================================
class StealthSimulator:
    """ওয়েবসাইটের সিকিউরিটি (Cloudflare, Datadome) বাইপাস করার জন্য হিউম্যান লজিক"""
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]

    @staticmethod
    def get_random_user_agent():
        return random.choice(StealthSimulator.USER_AGENTS)

    @staticmethod
    def human_delay(min_sec=1.5, max_sec=4.5):
        """মানুষের মতো র‍্যান্ডম ডিলে"""
        time.sleep(random.uniform(min_sec, max_sec))

    @staticmethod
    def type_like_human(page, selector, text):
        """মানুষের মতো স্পিড কমিয়ে টাইপ করা"""
        logger.info(f"Typing into {selector} like a human...")
        page.click(selector)
        StealthSimulator.human_delay(0.5, 1.5)
        for char in text:
            page.keyboard.press(char)
            time.sleep(random.uniform(0.05, 0.25)) # প্রতি কী-বোর্ডের বাটনে র‍্যান্ডম স্পিড
        StealthSimulator.human_delay(0.5, 1.0)

    @staticmethod
    def scroll_like_human(page):
        """পেজ লোড হওয়ার পর ডামি স্ক্রোল করা যাতে বট মনে না হয়"""
        logger.debug("Simulating human page scrolling...")
        scroll_steps = random.randint(3, 6)
        for _ in range(scroll_steps):
            scroll_amount = random.randint(200, 700)
            page.mouse.wheel(0, scroll_amount)
            StealthSimulator.human_delay(0.5, 2.0)
        # আবার একটু ওপরে ওঠা
        page.mouse.wheel(0, -random.randint(100, 400))
        StealthSimulator.human_delay(1.0, 2.0)

# ==========================================
# CAPTCHA & BLOCK DETECTION ENGINE
# ==========================================
class SecurityDetector:
    """লগইন ব্লক বা ক্যাপচা পেজ ডিটেক্ট করার এন্টারপ্রাইজ লজিক"""
    
    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "#cf-turnstile",            # Cloudflare Turnstile
        "#challenge-form",          # Cloudflare old challenge
        "div.g-recaptcha",
        "div.h-captcha",
        "[id*='px-captcha']"        # PerimeterX
    ]
    
    LOGIN_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "form[action*='login']",
        "a[href*='login']",
        "button:has-text('Sign In')",
        "button:has-text('Log In')"
    ]

    @staticmethod
    def check_for_captcha(page):
        """পেজে ক্যাপচা আছে কিনা চেক করবে"""
        for selector in SecurityDetector.CAPTCHA_SELECTORS:
            try:
                if page.locator(selector).count() > 0:
                    logger.warning(f"SECURITY ALERT: Captcha detected via selector -> {selector}")
                    return True
            except Exception as e:
                pass
        
        # টেক্সট ভিত্তিক ক্লাউডফ্লেয়ার চেকিং
        content = page.content().lower()
        if "checking your browser before accessing" in content or "please stand by, while we are checking your browser" in content:
            logger.warning("SECURITY ALERT: Cloudflare browser check detected.")
            return True
            
        return False

    @staticmethod
    def check_for_login_wall(page):
        """জব দেখতে লগইন লাগবে কিনা তা চেক করা"""
        for selector in SecurityDetector.LOGIN_SELECTORS:
            try:
                if page.locator(selector).count() > 0:
                    logger.info("ACTION REQUIRED: Login wall detected.")
                    return True
            except:
                pass
        return False

# ==========================================
# MAIN INTERACTOR CORE
# ==========================================
class NMInteractorEngine:
    def __init__(self):
        self.jobs_to_process = []
        self.active_jobs = []
        self.pending_human_actions = []

    def system_health_check(self):
        """ডাটাবেসের ইন্টিগ্রিটি চেক করা"""
        logger.info("Running File 3 Health Check...")
        if not os.path.exists(VALIDATED_JOBS_FILE):
            logger.warning("No validated jobs file found. Exiting.")
            return False
        if os.path.getsize(VALIDATED_JOBS_FILE) == 0:
            logger.warning("Validated jobs file is empty. Nothing to process.")
            return False
        return True

    def load_data(self):
        """File 2 থেকে ভ্যালিড কাজগুলো মেমরিতে লোড করা"""
        try:
            with open(VALIDATED_JOBS_FILE, 'r', encoding='utf-8') as f:
                self.jobs_to_process = json.load(f)
            logger.info(f"Loaded {len(self.jobs_to_process)} jobs for interaction.")
        except Exception as e:
            logger.critical(f"Failed to load validated jobs: {e}")
            self.jobs_to_process = []

        # আগের পেন্ডিং অ্যাকশন লোড করা (যাতে ডুপ্লিকেট নোটিফিকেশন না যায়)
        if os.path.exists(PENDING_ACTION_FILE) and os.path.getsize(PENDING_ACTION_FILE) > 0:
            try:
                with open(PENDING_ACTION_FILE, 'r', encoding='utf-8') as f:
                    self.pending_human_actions = json.load(f)
            except:
                self.pending_human_actions = []

    def trigger_file4_notifier(self, job, reason, page_url):
        """যখনই সিস্টেম আটকে যাবে, File 4 এর জন্য ডাটা ডাম্প করবে"""
        logger.error(f"HALTING AUTOMATION FOR JOB: {job.get('title')}. REASON: {reason}")
        
        action_payload = {
            "job_id": job.get("link"),
            "title": job.get("title"),
            "url": page_url,
            "reason": reason,
            "timestamp": time.time(),
            "status": "waiting_for_user"
        }
        
        # ডুপ্লিকেট চেক
        exists = any(a['job_id'] == action_payload['job_id'] for a in self.pending_human_actions)
        if not exists:
            self.pending_human_actions.append(action_payload)
            try:
                with open(PENDING_ACTION_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.pending_human_actions, f, indent=4)
                logger.info("Signal sent to File 4 (Notifier). Awaiting manual Flutter App intervention.")
            except Exception as e:
                logger.error(f"Failed to save pending action: {e}")

    def save_page_for_file5(self, job_id, html_content):
        """File 5 (Task Reader) এর জন্য পেজের পুরো HTML সেভ করা"""
        # সেফ ফাইল নেম তৈরি
        safe_name = "".join([c for c in job_id if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        safe_name = safe_name[:50].replace(" ", "_")
        file_path = os.path.join(HTML_DUMP_FOLDER, f"dump_{safe_name}.html")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Successfully dumped HTML context for File 5 -> {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to dump HTML for File 5: {e}")
            return None

    def execute_browser_session(self):
        """Playwright ব্যবহার করে হেডলেস ব্রাউজার কন্ট্রোল করা"""
        if not self.jobs_to_process:
            return

        logger.info("Initializing Stealth Browser Session...")
        
        try:
            with sync_playwright() as p:
                # ব্রাউজার লঞ্চ করা (হেডলেস মোডে, তবে অ্যান্টি-বট বাইপাসের আর্গুমেন্ট সহ)
                browser = p.chromium.launch(
                    headless=True, # স্ক্রিনে না দেখিয়ে ব্যাকগ্রাউন্ডে চলবে
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-infobars',
                        '--no-sandbox',
                        '--disable-setuid-sandbox'
                    ]
                )
                
                for job in self.jobs_to_process:
                    # যদি কাজ অলরেডি পেন্ডিং থাকে, স্কিপ করবে
                    if any(a['job_id'] == job.get('link') for a in self.pending_human_actions):
                        logger.info(f"Skipping {job.get('title')}, already waiting for manual action.")
                        continue

                    job_url = job.get('link')
                    logger.info(f"Navigating to Target: {job_url}")
                    
                    # নতুন ইনকগনিটো কন্টেক্সট (যাতে ক্যাশ ক্লিয়ার থাকে)
                    context = browser.new_context(
                        user_agent=StealthSimulator.get_random_user_agent(),
                        viewport={"width": random.randint(1366, 1920), "height": random.randint(768, 1080)}
                    )
                    
                    page = context.new_page()
                    
                    # ন্যাভিগেশন লজিক
                    try:
                        # Timeout বাড়িয়ে দেওয়া হয়েছে যাতে ভারী সাইট লোড হতে পারে
                        page.goto(job_url, timeout=60000, wait_until="domcontentloaded")
                        StealthSimulator.human_delay(2.0, 4.0)
                        
                        # ডামি স্ক্রোল
                        StealthSimulator.scroll_like_human(page)
                        
                        # সিকিউরিটি এবং ক্যাপচা চেকিং
                        if SecurityDetector.check_for_captcha(page):
                            self.trigger_file4_notifier(job, "CAPTCHA_BLOCKED", page.url)
                            context.close()
                            continue
                            
                        # লগইন চেকিং
                        if SecurityDetector.check_for_login_wall(page):
                            self.trigger_file4_notifier(job, "LOGIN_REQUIRED", page.url)
                            context.close()
                            continue
                            
                        # সব বাধা পার হলে File 5 এর জন্য ডাটা এক্সট্রাক্ট করা
                        logger.info(f"Target clear. Extracting DOM data for {job.get('title')}")
                        html_content = page.content()
                        dump_path = self.save_page_for_file5(job.get('title'), html_content)
                        
                        if dump_path:
                            job['status'] = 'ready_for_reader'
                            job['html_dump_path'] = dump_path
                            self.active_jobs.append(job)
                            
                    except PlaywrightTimeoutError:
                        logger.error(f"Timeout occurred while trying to load: {job_url}")
                    except Exception as e:
                        logger.error(f"Unexpected error during navigation to {job_url}: {e}")
                        
                    finally:
                        context.close()
                        StealthSimulator.human_delay(1.0, 3.0) # দুটি জবের মাঝে ডিলে

                browser.close()
                logger.info("Browser session closed safely.")
                
        except Exception as e:
            logger.critical(f"FATAL BROWSER ENGINE CRASH: {traceback.format_exc()}")

    def update_database(self):
        """SSD ডাটাবেস আপডেট করা"""
        # Active Jobs আপডেট
        if self.active_jobs:
            try:
                # এক্সিস্টিং ডাটার সাথে মার্জ করা
                existing_active = []
                if os.path.exists(ACTIVE_JOBS_FILE):
                    with open(ACTIVE_JOBS_FILE, 'r', encoding='utf-8') as f:
                        existing_active = json.load(f)
                
                existing_active.extend(self.active_jobs)
                
                with open(ACTIVE_JOBS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(existing_active, f, indent=4)
                logger.info("Active jobs successfully passed to File 5 queue.")
            except Exception as e:
                logger.error(f"Failed to update active jobs database: {e}")

        # ভ্যালিডেটেড লিস্ট ক্লিন করা (যেহেতু প্রসেস হয়ে গেছে)
        try:
            processed_links = [j.get('link') for j in self.active_jobs] + [p.get('job_id') for p in self.pending_human_actions]
            remaining_jobs = [j for j in self.jobs_to_process if j.get('link') not in processed_links]
            
            with open(VALIDATED_JOBS_FILE, 'w', encoding='utf-8') as f:
                json.dump(remaining_jobs, f, indent=4)
            logger.info("Cleaned up processed jobs from validated list.")
        except Exception as e:
            logger.error(f"Failed to clean validated jobs: {e}")

# ==========================================
# INITIALIZATION BLOCK
# ==========================================
def main():
    print("\n" + "="*70)
    print(" NMStudio1 AI Engine - FILE 3: SECURE INTERACTOR MODULE INITIATED ")
    print("="*70)
    
    interactor = NMInteractorEngine()
    
    if not interactor.system_health_check():
        print("System safely halting. Awaiting data from File 2.")
        return
        
    interactor.load_data()
    interactor.execute_browser_session()
    interactor.update_database()
    
    print("="*70)
    print(" INTERACTOR EXECUTION COMPLETED (NO FATAL ERRORS RECORDED) ")
    print("="*70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Execution interrupted manually by User.")
    except Exception as e:
        logger.critical(f"SYSTEM FAILURE IN FILE 3: {e}")