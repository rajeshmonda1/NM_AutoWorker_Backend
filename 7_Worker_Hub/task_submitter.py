import os
import json
import time
import logging
import traceback
import random
import google.generativeai as genai
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==========================================
# ENTERPRISE PATH & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
DELIVERABLES_FOLDER = os.path.join(DB_FOLDER, "Completed_Deliverables")

# Input & Output Files
COMPLETED_TASKS_FILE = os.path.join(DB_FOLDER, "completed_tasks.json") # File 7 থেকে এসেছে
PENDING_PAYMENT_FILE = os.path.join(DB_FOLDER, "pending_payment.json") # File 8 এর জন্য যাবে
SUBMITTER_LOG_FILE = os.path.join(DB_FOLDER, "task_submitter_logs.txt")
PENDING_ACTION_FILE = os.path.join(DB_FOLDER, "pending_human_action.json") # যদি সাবমিটে ক্যাপচা আসে

# Gemini API Configuration
GEMINI_API_KEY = "AIzaSyCtGJWf-tb0Y6YTF3y86YoE3y5lZUNljTs"

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_submitter_logger():
    logger = logging.getLogger("NM_Task_Submitter")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [SUBMITTER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(SUBMITTER_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_submitter_logger()

# ==========================================
# AI SUBMISSION MESSAGE GENERATOR
# ==========================================
class MessageGenerator:
    """কাজ সাবমিট করার সময় একটি প্রফেশনাল কভার লেটার বা মেসেজ তৈরি করবে"""
    def __init__(self):
        self.is_api_ready = False
        if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                self.is_api_ready = True
            except Exception as e:
                logger.error(f"Gemini API init failed in submitter: {e}")

    def generate_delivery_message(self, task_title, task_type):
        if not self.is_api_ready:
            return f"Hello, I have completed the task: {task_title}. Please find the attached files. Let me know if you need any modifications. Thank you!"

        prompt = f"""
You are a highly professional freelance worker delivering a completed project to a client.
Write a short, polite, and confident delivery message.

Task Title: {task_title}
Task Type: {task_type}

Rules:
1. Keep it under 50 words.
2. Mention that the requested file is attached.
3. Offer free revisions if needed.
4. Do not include placeholders like [Client Name]. Start with "Hello,".
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate AI message: {e}")
            return "Hello, the project is completed and the files are attached. Thank you!"

# ==========================================
# PLAYWRIGHT AUTOMATED SUBMISSION BROWSER
# ==========================================
class SubmitterBrowser:
    """ওয়েবসাইটে গিয়ে ফাইল আপলোড এবং সাবমিট বাটনে ক্লিক করার লজিক"""
    
    # সাধারণত ওয়েবসাইটগুলোতে আপলোড এবং সাবমিট বাটনের যে HTML ট্যাগ থাকে
    UPLOAD_SELECTORS = ["input[type='file']", "button:has-text('Upload File')", "button:has-text('Attach')"]
    MESSAGE_SELECTORS = ["textarea", "div[contenteditable='true']", "input[type='text']"]
    SUBMIT_SELECTORS = ["button:has-text('Submit')", "button:has-text('Send')", "button:has-text('Deliver')"]

    @staticmethod
    def human_delay(min_s=1.0, max_s=3.0):
        time.sleep(random.uniform(min_s, max_s))

    def attempt_submission(self, url, file_path, delivery_message):
        logger.info(f"Initiating Browser for submission at: {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
                
                # পেজে যাওয়া
                page.goto(url, timeout=60000)
                self.human_delay(2, 4)
                
                # ক্যাপচা বা লগইন চেক (File 3 এর মতো)
                if page.locator("iframe[src*='recaptcha']").count() > 0 or page.locator("input[type='password']").count() > 0:
                    logger.warning("Submission blocked by Security/Login. Sending to App Notifier.")
                    browser.close()
                    return False, "CAPTCHA_OR_LOGIN_REQUIRED", page.url
                
                # স্টেপ ১: ফাইল আপলোড করা
                file_uploaded = False
                for selector in self.UPLOAD_SELECTORS:
                    if page.locator(selector).count() > 0:
                        try:
                            # Playwright এর file chooser লজিক
                            with page.expect_file_chooser() as fc_info:
                                page.locator(selector).first.click()
                            file_chooser = fc_info.value
                            file_chooser.set_files(file_path)
                            file_uploaded = True
                            logger.info("File successfully attached.")
                            self.human_delay()
                            break
                        except Exception as e:
                            logger.debug(f"Selector {selector} failed: {e}")

                # স্টেপ ২: ডেলিভারি মেসেজ লেখা
                for selector in self.MESSAGE_SELECTORS:
                    if page.locator(selector).count() > 0:
                        try:
                            page.locator(selector).first.fill(delivery_message)
                            logger.info("Delivery message typed successfully.")
                            self.human_delay()
                            break
                        except:
                            pass

                # স্টেপ ৩: সাবমিট বাটনে ক্লিক করা
                submitted = False
                for selector in self.SUBMIT_SELECTORS:
                    if page.locator(selector).count() > 0:
                        try:
                            page.locator(selector).first.click()
                            page.wait_for_load_state('networkidle')
                            submitted = True
                            logger.info("Submit button clicked! Delivery successful.")
                            break
                        except:
                            pass

                browser.close()
                
                if submitted:
                    return True, "Successfully Delivered", ""
                else:
                    return False, "Could not find submit buttons. Site layout unknown.", page.url
                    
        except PlaywrightTimeoutError:
            logger.error(f"Timeout while loading {url}")
            return False, "TIMEOUT", url
        except Exception as e:
            logger.error(f"Browser automation failed: {e}")
            return False, str(e), url

# ==========================================
# MAIN SUBMITTER ENGINE (ORCHESTRATOR)
# ==========================================
class NMSubmitterEngine:
    def __init__(self):
        self.completed_tasks = []
        self.pending_payments = []
        self.pending_human_actions = []
        self.msg_generator = MessageGenerator()
        self.browser = SubmitterBrowser()

    def load_data(self):
        """File 7 থেকে আসা কমপ্লিট টাস্ক লোড করা"""
        if os.path.exists(COMPLETED_TASKS_FILE):
            try:
                with open(COMPLETED_TASKS_FILE, 'r', encoding='utf-8') as f:
                    self.completed_tasks = json.load(f)
                logger.info(f"Loaded {len(self.completed_tasks)} tasks ready for submission.")
            except Exception as e:
                logger.error(f"Failed to load completed tasks: {e}")

        # আগের পেমেন্ট লিস্ট লোড
        if os.path.exists(PENDING_PAYMENT_FILE):
            try:
                with open(PENDING_PAYMENT_FILE, 'r', encoding='utf-8') as f:
                    self.pending_payments = json.load(f)
            except:
                pass

        # আগের পেন্ডিং একশন লোড
        if os.path.exists(PENDING_ACTION_FILE):
            try:
                with open(PENDING_ACTION_FILE, 'r', encoding='utf-8') as f:
                    self.pending_human_actions = json.load(f)
            except:
                pass

    def trigger_app_notifier(self, task, reason, page_url):
        """যদি সাবমিট করতে গিয়ে আটকে যায়, ফ্লাটার অ্যাপে মেসেজ পাঠাবে (File 4 এর মাধ্যমে)"""
        action_payload = {
            "job_id": task.get("job_id"),
            "title": f"Submission Failed: {task.get('title')}",
            "url": page_url,
            "reason": reason,
            "timestamp": time.time(),
            "status": "waiting_for_user_submission"
        }
        
        if not any(a['job_id'] == action_payload['job_id'] for a in self.pending_human_actions):
            self.pending_human_actions.append(action_payload)
            logger.warning(f"Sent task {task.get('title')} to manual submission queue.")

    def process_submissions(self):
        """সবগুলো কাজ একটা একটা করে সাবমিট করা"""
        if not self.completed_tasks:
            return

        tasks_to_keep = []

        for task in self.completed_tasks:
            title = task.get('title', 'Unknown Task')
            url = task.get('source_url')
            execution_data = task.get('execution_result', {})
            file_path = execution_data.get('deliverable_path')

            # ডাটা ভ্যালিডেশন
            if not url or not file_path or not os.path.exists(file_path):
                logger.error(f"Missing URL or File for task: {title}. Skipping.")
                tasks_to_keep.append(task)
                continue

            # এআই মেসেজ বানানো
            delivery_msg = self.msg_generator.generate_delivery_message(title, task.get('assigned_worker'))
            
            # ব্রাউজারে সাবমিট করা
            success, reason, current_url = self.browser.attempt_submission(url, file_path, delivery_msg)

            if success:
                # সাবমিট সফল হলে Payment File এ যোগ করা
                task['status'] = "submitted_waiting_for_payment"
                task['submission_time'] = time.time()
                self.pending_payments.append(task)
                
                # SSD বাঁচানোর জন্য আসল ফাইলটা ডিলিট করে দেওয়া
                try:
                    os.remove(file_path)
                    logger.info(f"SSD Auto-Clean: Deleted {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(f"Could not delete deliverable file: {e}")
            else:
                # আটকে গেলে বা এরর হলে File 4 (Notifier) কে ডাকা
                self.trigger_app_notifier(task, reason, current_url)
                tasks_to_keep.append(task) # কিউ তে রেখে দেবে ম্যানুয়াল সলভের জন্য

        self.completed_tasks = tasks_to_keep

    def save_and_cleanup(self):
        """সব ডাটাবেস আপডেট করা"""
        try:
            with open(COMPLETED_TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.completed_tasks, f, indent=4)
                
            with open(PENDING_PAYMENT_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pending_payments, f, indent=4)
                
            with open(PENDING_ACTION_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pending_human_actions, f, indent=4)
                
            logger.info("Submission databases completely synced.")
        except Exception as e:
            logger.error(f"Failed to save final state: {e}")

# ==========================================
# MAIN EXECUTION THREAD
# ==========================================
def main():
    print("\n" + "="*75)
    print(" NMStudio1 AI Engine - TASK SUBMITTER MODULE INITIATED ")
    print("="*75)
    
    submitter = NMSubmitterEngine()
    
    submitter.load_data()
    submitter.process_submissions()
    submitter.save_and_cleanup()
    
    print("="*75)
    print(" SUBMITTER EXECUTION COMPLETE (SSD CLEANED & PAYMENTS ROUTED) ")
    print("="*75 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Submitter interrupted manually.")
    except Exception as e:
        logger.critical(f"FATAL ERROR IN SUBMITTER: {traceback.format_exc()}")