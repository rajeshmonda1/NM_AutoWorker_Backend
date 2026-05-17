import os
import time
import subprocess

# সবগুলো ফাইলের পাথ
SCRIPTS = [
    "1_Explorer/file1_scraper.py",
    "2_Validator/file2_validator.py",
    "3_Interactor/file3_interactor.py",
    "5_Task_Reader/file5_task_reader.py",
    "6_Feasibility_Checker/file6_checker.py",
    "7_Worker_Hub/file7_main_hub.py",
    "7_Worker_Hub/task_submitter.py"
]

def run_system():
    print("🚀 NMStudio1 AI Engine Starting...")
    for script in SCRIPTS:
        print(f"\n[RUNNING] -> {script}")
        try:
            # স্ক্রিপ্ট রান করা হচ্ছে
            subprocess.run(["python", script], check=True)
            time.sleep(3) # একটি শেষ হলে ৩ সেকেন্ড ওয়েট করে পরেরটি ধরবে
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running {script}: {e}")
            break # কোনো ফাইলে এরর হলে সিস্টেম পজ হয়ে যাবে
            
    print("\n✅ ONE FULL CYCLE COMPLETED. Waiting 30 minutes for next cycle...")

if __name__ == "__main__":
    while True:
        run_system()
        time.sleep(1800) # প্রতি ৩০ মিনিট পর পর পুরো ইন্টারনেট আবার খুঁজবে