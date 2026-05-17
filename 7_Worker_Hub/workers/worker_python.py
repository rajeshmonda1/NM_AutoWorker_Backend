import os
import re
import ast
import time
import logging
import traceback
import google.generativeai as genai
from datetime import datetime
import json

# ==========================================
# ENTERPRISE PATH & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
DELIVERABLES_FOLDER = os.path.join(DB_FOLDER, "Completed_Deliverables")

# API Configuration (আপনার Gemini API Key এখানে বসাতে হবে)
# সিকিউরিটির জন্য এটি একটি .env ফাইল থেকেও লোড করা যায়
GEMINI_API_KEY = "AIzaSyCtGJWf-tb0Y6YTF3y86YoE3y5lZUNljTs"

# ==========================================
# WORKER SPECIFIC LOGGING
# ==========================================
def setup_worker_logger():
    logger = logging.getLogger("NM_Worker_Python")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [PYTHON_WORKER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    log_file = os.path.join(DB_FOLDER, "worker_python_logs.txt")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_worker_logger()

# ==========================================
# AI CODE GENERATION & VALIDATION ENGINE
# ==========================================
class PythonWorkerEngine:
    def __init__(self):
        self.is_api_ready = self.initialize_api()
        
        # ডেলিভারি ফোল্ডার তৈরি করা (যেখানে কোড সেভ হবে)
        if not os.path.exists(DELIVERABLES_FOLDER):
            os.makedirs(DELIVERABLES_FOLDER)

    def initialize_api(self):
        """Gemini API সেটআপ এবং ভ্যালিডেশন"""
        if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
            logger.error("Gemini API Key is missing. Worker cannot write code.")
            return False
            
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # কোডিংয়ের জন্য ফ্ল্যাশ বা প্রো মডেল ব্যবহার করা ভালো
            self.model = genai.GenerativeModel('gemini-1.5-flash') 
            logger.info("Gemini API successfully initialized for code generation.")
            return True
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini API: {e}")
            return False

    def build_prompt(self, task_data, error_feedback=None):
        """AI কে ইনস্ট্রাকশন দেওয়ার জন্য হার্ডকোর প্রম্পট ইঞ্জিনিয়ারিং"""
        title = task_data.get('title', 'Unknown Task')
        description = task_data.get('task_description', '')
        
        prompt = f"""
You are an expert, senior Python developer working for NMStudio1.
Your task is to write a complete, error-free, and production-ready Python script based on the following client request.

CLIENT TASK TITLE: {title}
CLIENT DESCRIPTION: {description}

STRICT CONSTRAINTS:
1. Provide ONLY the Python code. No explanations, no markdown formatting outside of the code block.
2. The code must be inside a single ```python ... 
``` block.
3. Include proper comments, error handling (try/except), and logging.
4. Ensure the code is memory efficient and compatible with Python 3.10+.
"""
        if error_feedback:
            prompt += f"\n\nWARNING: Your previous code had the following error. Fix it immediately:\n{error_feedback}"
            
        return prompt

    def extract_code(self, ai_response_text):
        """AI এর টেক্সট থেকে শুধু Python কোডটুকু রেজেক্স (Regex) দিয়ে বের করে আনা"""
        match = re.search(r'```python\s*(.*?)\s*```', ai_response_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # যদি AI ভুলে ব্যাকটিক (```) না দেয়
        logger.warning("No python code block found. Attempting raw text extraction.")
        return ai_response_text.strip()

    def validate_syntax(self, code_string):
        """
        সবচেয়ে গুরুত্বপূর্ণ পার্ট: 
        কোডটি ক্লায়েন্টকে দেওয়ার আগে AST (Abstract Syntax Tree) দিয়ে লোকালি চেক করা।
        """
        try:
            ast.parse(code_string)
            logger.info("Syntax Validation PASSED. The code is structurally correct.")
            return True, None
        except SyntaxError as e:
            error_msg = f"SyntaxError at line {e.lineno}, offset {e.offset}: {e.text}"
            logger.error(f"Syntax Validation FAILED: {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.error(f"Unknown parsing error: {e}")
            return False, str(e)

    def generate_and_verify_code(self, task_data, max_retries=3):
        """কোড জেনারেট করা এবং ভুল থাকলে নিজে নিজেই এআইকে দিয়ে ঠিক করানো"""
        if not self.is_api_ready:
            return None, "API Key Missing or Configuration Failed."

        error_feedback = None
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"Generation Attempt {attempt}/{max_retries} for task: {task_data.get('job_id')}")
            prompt = self.build_prompt(task_data, error_feedback)
            
            try:
                # API Call
                response = self.model.generate_content(prompt)
                raw_text = response.text
                
                # কোড এক্সট্রাক্ট করা
                clean_code = self.extract_code(raw_text)
                
                # সিনট্যাক্স চেক করা
                is_valid, error_msg = self.validate_syntax(clean_code)
                
                if is_valid:
                    return clean_code, None
                else:
                    error_feedback = error_msg # পরের লুপে এআইকে এই এররটা পাঠানো হবে
                    time.sleep(2) # API Rate limit বাঁচানোর জন্য ডিলে
                    
            except Exception as e:
                logger.error(f"API Call failed on attempt {attempt}: {e}")
                error_feedback = f"API Error: {str(e)}"
                time.sleep(5)
                
        return None, f"Failed to generate valid code after {max_retries} attempts. Last error: {error_feedback}"

    def save_deliverable(self, job_id, code_string):
        """কাজ শেষ হওয়ার পর কোডটি একটি ফাইলে সেভ করে রাখা ক্লায়েন্টকে দেওয়ার জন্য"""
        safe_name = f"task_{job_id.split('/')[-1] if '/' in job_id else job_id}.py"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in ['.', '_'])
        file_path = os.path.join(DELIVERABLES_FOLDER, safe_name)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code_string)
            logger.info(f"Deliverable successfully saved at: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save deliverable file: {e}")
            return None

# ==========================================
# STANDARD WORKER ENTRY POINT (CALLED BY FILE 7)
# ==========================================
def execute_task(task_data):
    """
    এই ফাংশনটি File 7 (Main Hub) কল করবে। 
    এটি অবশ্যই একটি ডিকশনারি রিটার্ন করবে যেখানে status, data এবং error থাকবে।
    """
    logger.info(f"--- Python Worker received task: {task_data.get('title')} ---")
    
    engine = PythonWorkerEngine()
    
    # কোড জেনারেট করা
    final_code, error = engine.generate_and_verify_code(task_data)
    
    if final_code:
        # সফল হলে কোড সেভ করে ডেলিভারি পাথ হাবকে জানিয়ে দেওয়া
        deliverable_path = engine.save_deliverable(task_data.get('job_id', str(time.time())), final_code)
        
        if deliverable_path:
            return {
                "status": "success",
                "data": {
                    "deliverable_path": deliverable_path,
                    "code_snippet": final_code[:200] + "... (truncated)",
                    "message": "Python script generated and syntax validated successfully."
                },
                "retry_allowed": False
            }
        else:
            return {
                "status": "failed",
                "error": "Code was generated but failed to save to disk.",
                "retry_allowed": True
            }
    else:
        # ফেইল করলে এরর মেসেজ হাবের কাছে পাঠিয়ে দেওয়া
        return {
            "status": "failed",
            "error": error,
            "retry_allowed": True # হাব এটিকে আবার অন্য থ্রেডে ট্রাই করতে পারে
        }

# ==========================================
# LOCAL TESTING BLOCK
# ==========================================
if __name__ == "__main__":
    # শুধুমাত্র ম্যানুয়াল টেস্টিংয়ের জন্য
    print("This file is a Worker Module. It is designed to be executed by file7_main_hub.py")
    print("Running a quick diagnostic test...")
    
    dummy_task = {
        "job_id": "test_123",
        "title": "Write a Python script to reverse a string",
        "task_description": "I need a simple python function that takes a string and returns it reversed. Include a print statement testing it."
    }
    
    result = execute_task(dummy_task)
    print(json.dumps(result, indent=4))