import os
import json
import time
import logging
import importlib.util
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime

# ==========================================
# ENTERPRISE PATH CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
WORKERS_DIR = os.path.join(os.path.dirname(__file__), "workers")

# Input & Output Data Files
HUB_QUEUE_FILE = os.path.join(DB_FOLDER, "hub_queue.json") # File 6 থেকে আসবে
COMPLETED_TASKS_FILE = os.path.join(DB_FOLDER, "completed_tasks.json") # Task Submitter এর জন্য
FAILED_TASKS_FILE = os.path.join(DB_FOLDER, "failed_hub_tasks.json")
HUB_LOG_FILE = os.path.join(DB_FOLDER, "worker_hub_logs.txt")

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_hub_logger():
    """Fail-proof Logging System for the Main Hub"""
    logger = logging.getLogger("NM_Worker_Hub")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [HUB_MANAGER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(HUB_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_hub_logger()

# ==========================================
# DYNAMIC WORKER LOADER ENGINE
# ==========================================
class WorkerLoader:
    """
    এই ক্লাসটি ডায়নামিকভাবে নির্দিষ্ট ওয়ার্কার ফাইল লোড করবে (যেমন worker_python.py)।
    এর ফলে হাব ফাইলটি নিজে ভারী হবে না এবং ক্র্যাশ করবে না।
    """
    
    @staticmethod
    def load_and_execute_worker(worker_name, task_data):
        """Python এর importlib ব্যবহার করে রানটাইমে ওয়ার্কার লোড করা"""
        worker_file_path = os.path.join(WORKERS_DIR, f"{worker_name}.py")
        
        # ওয়ার্কার ফাইল আছে কিনা চেক করা (যেহেতু আমরা এখনো বানাইনি, এটি সেফগার্ড দেবে)
        if not os.path.exists(worker_file_path):
            error_msg = f"Worker file missing: {worker_name}.py"
            logger.error(error_msg)
            return {"status": "failed", "error": error_msg, "retry_allowed": False}
            
        try:
            logger.debug(f"Dynamically loading module: {worker_name}")
            spec = importlib.util.spec_from_file_location(worker_name, worker_file_path)
            worker_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker_module)
            
            # প্রতিটি ওয়ার্কার ফাইলে 'execute_task' নামের একটি ফাংশন থাকতে হবে
            if hasattr(worker_module, 'execute_task'):
                logger.info(f"Handing over task '{task_data.get('title')[:20]}...' to {worker_name}")
                
                # ওয়ার্কারকে কাজ দেওয়া এবং রেজাল্ট নেওয়া
                result = worker_module.execute_task(task_data)
                return result
            else:
                return {"status": "failed", "error": f"Function 'execute_task' not found in {worker_name}.py", "retry_allowed": False}
                
        except Exception as e:
            logger.error(f"Worker Crash ({worker_name}): {traceback.format_exc()}")
            return {"status": "failed", "error": str(e), "retry_allowed": True}

# ==========================================
# HUB ORCHESTRATION & QUEUE MANAGEMENT
# ==========================================
class NMWorkerHubEngine:
    def __init__(self):
        self.pending_queue = []
        self.completed_tasks = []
        self.failed_tasks = []
        self.execution_timeout_seconds = 1800 # একটি কাজের জন্য সর্বোচ্চ ৩০ মিনিট সময়

    def system_health_check(self):
        """SSD ফোল্ডার এবং ফাইল স্ট্রাকচার চেক করা"""
        logger.info("Initializing Main Hub Diagnostics...")
        
        # Workers ফোল্ডার না থাকলে তৈরি করা
        if not os.path.exists(WORKERS_DIR):
            os.makedirs(WORKERS_DIR)
            logger.info(f"Created workers directory at: {WORKERS_DIR}")
            
        if not os.path.exists(HUB_QUEUE_FILE) or os.path.getsize(HUB_QUEUE_FILE) == 0:
            logger.warning("Hub Queue is empty or missing. Awaiting verified tasks from File 6.")
            return False
            
        return True

    def load_queue(self):
        """File 6 থেকে আসা ভেরিফায়েড কাজের লিস্ট লোড করা"""
        try:
            with open(HUB_QUEUE_FILE, 'r', encoding='utf-8') as f:
                self.pending_queue = json.load(f)
            logger.info(f"Successfully loaded {len(self.pending_queue)} tasks into the execution pipeline.")
        except Exception as e:
            logger.critical(f"Failed to load Hub Queue: {e}")
            self.pending_queue = []

        # এক্সিস্টিং কমপ্লিট ডাটা লোড (ওভাররাইট ঠেকানোর জন্য)
        if os.path.exists(COMPLETED_TASKS_FILE):
            try:
                with open(COMPLETED_TASKS_FILE, 'r', encoding='utf-8') as f:
                    self.completed_tasks = json.load(f)
            except:
                self.completed_tasks = []

    def execute_tasks(self):
        """মাল্টি-থ্রেডিং ব্যবহার করে কাজ এক্সিকিউট করা এবং টাইমআউট হ্যান্ডেল করা"""
        if not self.pending_queue:
            return

        logger.info(f"Commencing Execution of {len(self.pending_queue)} tasks...")
        tasks_to_keep_in_queue = []
        
        # থ্রেডপুল এক্সিকিউটর (যাতে কোনো ওয়ার্কার ক্র্যাশ করলে হাব বেঁচে থাকে)
        with ThreadPoolExecutor(max_workers=3) as executor: # একসাথে ৩টি কাজ করতে পারবে
            for task in self.pending_queue:
                assigned_worker = task.get('assigned_worker')
                job_id = task.get('job_id')
                
                if not assigned_worker:
                    logger.error(f"Task {job_id} has no assigned worker. Moving to failed.")
                    task['error_log'] = "Orphan Task - No worker assigned by File 6"
                    self.failed_tasks.append(task)
                    continue

                logger.info(f"Dispatching task to -> {assigned_worker.upper()}")
                
                # ফিউচার টাস্ক সাবমিট করা
                future = executor.submit(WorkerLoader.load_and_execute_worker, assigned_worker, task)
                
                try:
                    # নির্দিষ্ট সময়ের মধ্যে কাজ শেষ না হলে TimeoutError থ্রো করবে
                    worker_response = future.result(timeout=self.execution_timeout_seconds)
                    
                    if worker_response.get("status") == "success":
                        task['execution_result'] = worker_response.get("data")
                        task['status'] = "ready_for_submission"
                        task['completed_at'] = time.time()
                        self.completed_tasks.append(task)
                        logger.info(f"SUCCESS: {assigned_worker} completed task {task.get('title')[:20]}")
                        
                    else:
                        logger.warning(f"FAILED: {assigned_worker} failed on task {job_id}. Reason: {worker_response.get('error')}")
                        if worker_response.get("retry_allowed"):
                            task['retry_count'] = task.get('retry_count', 0) + 1
                            if task['retry_count'] < 3: # ৩ বার রি-ট্রাই করবে
                                tasks_to_keep_in_queue.append(task)
                            else:
                                task['error_log'] = worker_response.get('error')
                                self.failed_tasks.append(task)
                        else:
                            task['error_log'] = worker_response.get('error')
                            self.failed_tasks.append(task)
                            
                except TimeoutError:
                    logger.error(f"TIMEOUT: {assigned_worker} took longer than {self.execution_timeout_seconds}s. Force terminating task.")
                    task['error_log'] = "Execution Timeout (Force Killed)"
                    self.failed_tasks.append(task)
                except Exception as e:
                    logger.error(f"CRITICAL EXECUTION ERROR for {job_id}: {e}")
                    task['error_log'] = str(e)
                    self.failed_tasks.append(task)

        # কিউ আপডেট করা (যেগুলো রি-ট্রাই হবে সেগুলো রেখে বাকি সব ক্লিন)
        self.pending_queue = tasks_to_keep_in_queue
        logger.info("Execution phase completed.")

    def save_and_cleanup(self):
        """সব ডাটাবেস সেফলি সেভ এবং আপডেট করা (File 8 / Submitter এর জন্য)"""
        
        # ১. Completed Tasks সেভ (task_submitter.py এটি রিড করবে)
        if self.completed_tasks:
            try:
                with open(COMPLETED_TASKS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.completed_tasks, f, indent=4, ensure_ascii=False)
                logger.info(f"Saved {len(self.completed_tasks)} completed tasks ready for final submission.")
            except Exception as e:
                logger.error(f"Failed to save COMPLETED_TASKS: {e}")

        # ২. Failed Tasks সেভ (লগিং এবং ম্যানুয়াল রিভিউর জন্য)
        if self.failed_tasks:
            try:
                mode = 'r+' if os.path.exists(FAILED_TASKS_FILE) else 'w'
                if mode == 'r+':
                    with open(FAILED_TASKS_FILE, 'r', encoding='utf-8') as f:
                        try:
                            existing_failed = json.load(f)
                        except:
                            existing_failed = []
                    self.failed_tasks.extend(existing_failed)
                    
                with open(FAILED_TASKS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.failed_tasks, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save FAILED_TASKS: {e}")

        # ৩. Hub Queue আপডেট করা (যেগুলো প্রসেস হয়ে গেছে সেগুলো রিমুভ করা)
        try:
            with open(HUB_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pending_queue, f, indent=4)
            logger.info("Hub Queue synchronized and cleaned.")
        except Exception as e:
            logger.error(f"Failed to clean Hub Queue file: {e}")

# ==========================================
# MAIN EXECUTION THREAD
# ==========================================
def main():
    print("\n" + "="*75)
    print(" NMStudio1 AI Engine - FILE 7: MAIN WORKER HUB MODULE INITIATED ")
    print("="*75)
    
    hub = NMWorkerHubEngine()
    
    if not hub.system_health_check():
        print("System safely halting. No pending tasks found.")
        return
        
    hub.load_queue()
    hub.execute_tasks()
    hub.save_and_cleanup()
    
    print("="*75)
    print(" HUB EXECUTION COMPLETE (ALL DELEGATED TASKS PROCESSED SAFELY) ")
    print("="*75 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Hub Engine execution manually interrupted by User.")
    except Exception as e:
        logger.critical(f"FATAL HUB ENGINE CRASH: {traceback.format_exc()}")