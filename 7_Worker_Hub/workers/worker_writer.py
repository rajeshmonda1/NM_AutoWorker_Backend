import os
import re
import json
import time
import logging
import traceback
import google.generativeai as genai
from datetime import datetime

# ==========================================
# ENTERPRISE PATH & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")
DELIVERABLES_FOLDER = os.path.join(DB_FOLDER, "Completed_Deliverables")

# Gemini API Configuration 
GEMINI_API_KEY = "AIzaSyCtGJWf-tb0Y6YTF3y86YoE3y5lZUNljTs"

# ==========================================
# WORKER SPECIFIC LOGGING
# ==========================================
def setup_writer_logger():
    logger = logging.getLogger("NM_Worker_Writer")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [WRITER_WORKER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    log_file = os.path.join(DB_FOLDER, "worker_writer_logs.txt")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_writer_logger()

# ==========================================
# NLP CONTENT GENERATION & VALIDATION ENGINE
# ==========================================
class WriterWorkerEngine:
    def __init__(self):
        if not os.path.exists(DELIVERABLES_FOLDER):
            os.makedirs(DELIVERABLES_FOLDER)
            
        self.is_api_ready = self.initialize_api()

    def initialize_api(self):
        """Gemini API সেটআপ করা কনটেন্ট রাইটিংয়ের জন্য"""
        if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
            logger.error("Gemini API Key missing. Worker cannot generate content.")
            return False
            
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # রাইটিংয়ের জন্য Pro বা Flash মডেল (Pro টেক্সটের জন্য ভালো)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini API successfully initialized for content writing.")
            return True
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini API: {e}")
            return False

    def extract_requirements(self, task_description):
        """ক্লায়েন্টের ডেসক্রিপশন থেকে ওয়ার্ড কাউন্ট এবং এসইও (SEO) রিকোয়ারমেন্ট বের করা"""
        requirements = {
            "target_words": 500, # Default
            "tone": "professional and engaging",
            "format": "markdown"
        }
        
        # Word count extraction
        word_match = re.search(r'(\d+)\s*(?:words|word)', task_description, re.IGNORECASE)
        if word_match:
            requirements["target_words"] = int(word_match.group(1))
            
        # Tone extraction
        desc_lower = task_description.lower()
        if "funny" in desc_lower or "humorous" in desc_lower:
            requirements["tone"] = "humorous and lighthearted"
        elif "technical" in desc_lower or "documentation" in desc_lower:
            requirements["tone"] = "highly technical and precise"
        elif "academic" in desc_lower or "essay" in desc_lower:
            requirements["tone"] = "academic, formal, and well-researched"
            
        return requirements

    def build_prompt(self, title, task_description, requirements, feedback=None):
        """AI কে ইনস্ট্রাকশন দেওয়ার জন্য মাস্টার প্রম্পট"""
        prompt = f"""
You are an expert, top-rated Content Writer and SEO Specialist.
Your task is to write high-quality, 100% original content based on the client's request.

CLIENT TASK TITLE: {title}
CLIENT INSTRUCTIONS: {task_description}

STRICT CONSTRAINTS & REQUIREMENTS:
1. TARGET LENGTH: Exactly around {requirements['target_words']} words.
2. TONE & STYLE: {requirements['tone']}.
3. FORMATTING: Use proper Markdown styling (H1, H2, bullet points) for readability.
4. NO FLUFF: Do not write generic introductions like "In today's fast-paced world." Get straight to the point.
5. Do not include any meta-conversation (e.g., "Here is your article:"). Just output the final content.
"""
        if feedback:
            prompt += f"\n\nFEEDBACK ON PREVIOUS DRAFT:\n{feedback}\nPlease revise the content to fix this issue."
            
        return prompt

    def count_words(self, text):
        """টেক্সটের আসল ওয়ার্ড কাউন্ট বের করা"""
        return len(re.findall(r'\b\w+\b', text))

    def quality_check(self, content, requirements):
        """এআইয়ের লেখা কনটেন্ট ক্লায়েন্টের রিকোয়ারমেন্ট পূরণ করেছে কিনা তা চেক করা"""
        word_count = self.count_words(content)
        target = requirements["target_words"]
        
        # 15% কম-বেশি হলে এক্সেপ্ট করবে, নাহলে রিজেক্ট করে এআইকে আবার লিখতে বলবে
        margin = target * 0.15
        
        if word_count < (target - margin):
            return False, f"The content is too short. You wrote {word_count} words, but the target is {target} words. Please expand the content with more valuable details."
        elif word_count > (target + margin):
            return False, f"The content is too long. You wrote {word_count} words, but the target is {target} words. Please make it more concise."
            
        # বেসিক এআই সিগনেচার চেক (যাতে ক্লায়েন্ট বুঝতে না পারে এটা এআইয়ের লেখা)
        ai_phrases = ["as an ai", "in conclusion", "it is important to note"]
        for phrase in ai_phrases:
            if phrase in content.lower():
                return False, f"Please remove robotic phrases like '{phrase}' and make it sound 100% human."

        logger.info(f"Quality Check PASSED. Word count: {word_count}/{target}")
        return True, None

    def generate_and_verify_content(self, task_data, max_retries=3):
        """কনটেন্ট জেনারেট করা এবং ভুল থাকলে অটোমেটিক কারেকশন করা"""
        if not self.is_api_ready:
            return None, "API Key Missing or Configuration Failed."

        title = task_data.get('title', 'Content Writing Task')
        description = task_data.get('task_description', '')
        requirements = self.extract_requirements(description)
        
        feedback = None
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"Generation Attempt {attempt}/{max_retries} for task: {task_data.get('job_id')}")
            prompt = self.build_prompt(title, description, requirements, feedback)
            
            try:
                response = self.model.generate_content(prompt)
                content = response.text.strip()
                
                # কোয়ালিটি চেকার
                is_valid, error_msg = self.quality_check(content, requirements)
                
                if is_valid:
                    return content, None
                else:
                    feedback = error_msg
                    logger.warning(f"Quality check failed on attempt {attempt}: {error_msg}")
                    time.sleep(3) # API রেট লিমিট প্রটেকশন
                    
            except Exception as e:
                logger.error(f"API Call failed on attempt {attempt}: {e}")
                feedback = f"API Error: {str(e)}"
                time.sleep(5)
                
        return None, f"Failed to generate acceptable content after {max_retries} attempts. Last issue: {feedback}"

    def save_deliverable(self, job_id, content_string):
        """কাজ শেষ হওয়ার পর টেক্সট বা মার্কডাউন ফাইলে সেভ করা"""
        safe_name = f"article_{job_id.split('/')[-1] if '/' in job_id else job_id}"
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == '_')
        file_path = os.path.join(DELIVERABLES_FOLDER, f"{safe_name}.md")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_string)
            logger.info(f"Deliverable successfully saved at: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save deliverable file: {e}")
            return None

# ==========================================
# STANDARD WORKER ENTRY POINT (CALLED BY FILE 7)
# ==========================================
def execute_task(task_data):
    """File 7 (Main Hub) এই ফাংশনটিকে কল করবে।"""
    logger.info(f"--- Writer Worker received task: {task_data.get('title')} ---")
    
    engine = WriterWorkerEngine()
    
    # কনটেন্ট জেনারেট করা
    final_content, error = engine.generate_and_verify_content(task_data)
    
    if final_content:
        # সফল হলে সেভ করে হাবকে ডেলিভারি পাথ জানিয়ে দেওয়া
        deliverable_path = engine.save_deliverable(task_data.get('job_id', str(time.time())), final_content)
        
        if deliverable_path:
            word_count = engine.count_words(final_content)
            return {
                "status": "success",
                "data": {
                    "deliverable_path": deliverable_path,
                    "word_count": word_count,
                    "content_snippet": final_content[:200] + "... (truncated)",
                    "message": f"Successfully wrote and verified {word_count} words of content."
                },
                "retry_allowed": False
            }
        else:
            return {
                "status": "failed",
                "error": "Content generated but failed to write to SSD.",
                "retry_allowed": True
            }
    else:
        # ফেইল করলে হাবের কাছে এরর পাঠানো
        return {
            "status": "failed",
            "error": error,
            "retry_allowed": True
        }

# ==========================================
# LOCAL TESTING BLOCK
# ==========================================
if __name__ == "__main__":
    print("Running diagnostic test for worker_writer.py...")
    dummy_task = {
        "job_id": "write_test_101",
        "title": "Write a blog post about AI in 2026",
        "task_description": "Please write a 300 words SEO optimized blog post about the future of AI in game development. Make it sound professional."
    }
    
    result = execute_task(dummy_task)
    print(json.dumps(result, indent=4))