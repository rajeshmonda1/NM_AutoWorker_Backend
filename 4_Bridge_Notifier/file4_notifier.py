import os
import json
import time
import logging
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import firebase_admin
from firebase_admin import credentials, messaging

# ==========================================
# ENTERPRISE PATH & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FOLDER = os.path.join(BASE_DIR, "Database_Logs")

# ডাটাবেস ফাইল পাথ
PENDING_ACTION_FILE = os.path.join(DB_FOLDER, "pending_human_action.json")
SENT_ALERTS_FILE = os.path.join(DB_FOLDER, "sent_alerts_log.json")
NOTIFIER_LOG_FILE = os.path.join(DB_FOLDER, "notifier_system_logs.txt")

# ফায়ারবেস কনফিগারেশন পাথ (আপনার ফ্লাটার প্রজেক্টের সার্ভিস একাউন্ট JSON এখানে রাখবেন)
FIREBASE_CREDENTIALS_PATH = os.path.join(BASE_DIR, "firebase_admin_key.json")
# আপনার মোবাইলের ফ্লাটার অ্যাপের FCM Device Token
FLUTTER_DEVICE_TOKEN = "YOUR_MOBILE_DEVICE_FCM_TOKEN_HERE" 

# লোকাল ওয়েব হুক সার্ভার কনফিগারেশন (যাতে ফ্লাটার অ্যাপ সিগন্যাল পাঠাতে পারে)
WEBHOOK_HOST = '0.0.0.0' # লোকাল নেটওয়ার্কের যেকোনো ডিভাইস থেকে এক্সেস করা যাবে
WEBHOOK_PORT = 8080

# ==========================================
# ADVANCED LOGGING ARCHITECTURE
# ==========================================
def setup_notifier_logger():
    logger = logging.getLogger("NM_Notifier_Bridge")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [NOTIFIER] [%(levelname)s] -> %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    file_handler = logging.FileHandler(NOTIFIER_LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

logger = setup_notifier_logger()

# ==========================================
# FIREBASE PUSH NOTIFICATION ENGINE
# ==========================================
class FirebaseEngine:
    """ফায়ারবেসের মাধ্যমে সিকিউরলি নোটিফিকেশন পাঠানোর লজিক"""
    
    def __init__(self):
        self.is_initialized = False
        self.initialize_firebase()

    def initialize_firebase(self):
        if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
            logger.error(f"Firebase key not found at {FIREBASE_CREDENTIALS_PATH}. Notifications disabled.")
            return

        try:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            self.is_initialized = True
            logger.info("Firebase Admin SDK successfully initialized.")
        except ValueError:
            # যদি আগে থেকেই ইনিশিয়ালাইজ করা থাকে
            self.is_initialized = True
            logger.info("Firebase Admin SDK already initialized.")
        except Exception as e:
            logger.critical(f"Failed to initialize Firebase: {e}")

    def send_alert_to_flutter(self, title, body, data_payload):
        """ফ্লাটার কন্ট্রোল অ্যাপে ডিরেক্ট পুশ নোটিফিকেশন পাঠানো"""
        if not self.is_initialized:
            logger.warning("Cannot send notification. Firebase is offline.")
            return False

        if FLUTTER_DEVICE_TOKEN == "YOUR_MOBILE_DEVICE_FCM_TOKEN_HERE":
            logger.warning("FCM Device Token is missing. Please update FLUTTER_DEVICE_TOKEN.")
            return False

        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data_payload, # অ্যাপের ব্যাকগ্রাউন্ড লজিকের জন্য ডাটা
                token=FLUTTER_DEVICE_TOKEN,
            )
            response = messaging.send(message)
            logger.info(f"FCM Push successful! Message ID: {response}")
            return True
        except Exception as e:
            logger.error(f"FCM Push failed: {e}")
            return False

# ==========================================
# LOCAL WEBHOOK SERVER FOR FLUTTER APP
# ==========================================
class FlutterWebhookHandler(BaseHTTPRequestHandler):
    """
    ফ্লাটার অ্যাপ থেকে সিগন্যাল রিসিভ করার জন্য লোকাল সার্ভার।
    যখন আপনি মোবাইলে ক্যাপচা সলভ করে 'Done' চাপবেন, অ্যাপটি http://<PC_IP>:8080/resolved এ হিট করবে।
    """
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/resolved':
            query_components = parse_qs(parsed_path.query)
            job_id = query_components.get('job_id', [None])[0]
            
            if job_id:
                logger.info(f"Received RESOLVED signal from Flutter App for Job ID: {job_id}")
                self.remove_pending_action(job_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Automation resumed"}).encode('utf-8'))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing job_id parameter")
        else:
            self.send_response(404)
            self.end_headers()

    def remove_pending_action(self, job_id):
        """অ্যাপ থেকে সিগন্যাল পেলে পেন্ডিং লিস্ট থেকে জব ডিলিট করা যাতে File 3 আবার কাজ শুরু করে"""
        try:
            with open(PENDING_ACTION_FILE, 'r', encoding='utf-8') as f:
                pending_actions = json.load(f)
                
            updated_actions = [action for action in pending_actions if action.get('job_id') != job_id]
            
            with open(PENDING_ACTION_FILE, 'w', encoding='utf-8') as f:
                json.dump(updated_actions, f, indent=4)
                
            logger.info(f"Job {job_id} cleared from pending list. System unblocked.")
        except Exception as e:
            logger.error(f"Error updating pending action file via Webhook: {e}")

def run_webhook_server():
    """ব্যাকগ্রাউন্ড থ্রেডে সার্ভার রান করার ফাংশন"""
    try:
        server = HTTPServer((WEBHOOK_HOST, WEBHOOK_PORT), FlutterWebhookHandler)
        logger.info(f"Local Flutter Webhook Server running on port {WEBHOOK_PORT}...")
        server.serve_forever()
    except Exception as e:
        logger.critical(f"Webhook Server Crash: {e}")

# ==========================================
# MAIN NOTIFIER ENGINE
# ==========================================
class NMNotifierBridge:
    def __init__(self):
        self.firebase = FirebaseEngine()
        self.sent_alerts = self.load_sent_alerts()

    def load_sent_alerts(self):
        """স্প্যামিং কমানোর জন্য আগে পাঠানো অ্যালার্টের লিস্ট লোড করা"""
        if os.path.exists(SENT_ALERTS_FILE):
            try:
                with open(SENT_ALERTS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_sent_alerts(self):
        with open(SENT_ALERTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.sent_alerts, f, indent=4)

    def process_pending_actions(self):
        """ডাটাবেস চেক করে নোটিফিকেশন পাঠানো"""
        if not os.path.exists(PENDING_ACTION_FILE):
            return

        try:
            with open(PENDING_ACTION_FILE, 'r', encoding='utf-8') as f:
                pending_actions = json.load(f)
        except json.JSONDecodeError:
            return
        except Exception as e:
            logger.error(f"Error reading pending actions: {e}")
            return

        for action in pending_actions:
            job_id = action.get("job_id")
            reason = action.get("reason", "ATTENTION REQUIRED")
            title = action.get("title", "Unknown Job")
            url = action.get("url", "")
            
            # স্প্যাম প্রটেকশন (একই জবের জন্য বারবার মেসেজ পাঠাবে না)
            if job_id in self.sent_alerts:
                continue

            # ফ্লাটার অ্যাপে পাঠানোর ডাটা পেলোড
            payload = {
                "job_id": job_id,
                "action_url": url,
                "reason": reason,
                "module": "File_3_Interactor"
            }

            logger.info(f"New pending action detected! Triggering alert for: {title}")
            
            # পুশ নোটিফিকেশন ফায়ার করা
            success = self.firebase.send_alert_to_flutter(
                title="🚨 AI Worker Blocked!",
                body=f"Manual action required for '{title}'. Reason: {reason}",
                data_payload=payload
            )

            if success:
                self.sent_alerts[job_id] = time.time()
                self.save_sent_alerts()

# ==========================================
# INITIALIZATION & CONTINUOUS LOOP
# ==========================================
def main():
    print("\n" + "="*70)
    print(" NMStudio1 AI Engine - FILE 4: BRIDGE & NOTIFIER MODULE INITIATED ")
    print("="*70)

    # স্টেপ ১: ফ্লাটার অ্যাপের সাথে কথা বলার জন্য ব্যাকগ্রাউন্ডে সার্ভার স্টার্ট করা
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()

    # স্টেপ ২: মেইন নোটিফায়ার ইঞ্জিন ইনিশিয়ালাইজ করা
    notifier = NMNotifierBridge()

    logger.info("Notifier Engine is active and monitoring for blockages. Press Ctrl+C to stop.")

    # স্টেপ ৩: কন্টিনিউয়াস মনিটরিং লুপ (যাতে কোনো এরর ছাড়াই আজীবন চলতে পারে)
    try:
        while True:
            notifier.process_pending_actions()
            time.sleep(5) # প্রতি ৫ সেকেন্ড পর পর চেক করবে, CPU এর উপর চাপ পড়বে না
            
    except KeyboardInterrupt:
        logger.warning("Notifier Module manually shut down by User.")
    except Exception as e:
        logger.critical(f"FATAL NOTIFIER LOOP CRASH: {traceback.format_exc()}")

if __name__ == "__main__":
    main()