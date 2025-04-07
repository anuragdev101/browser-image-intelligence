import tkinter as tk
from tkinter import scrolledtext, messagebox, font as tkfont, ttk
import websocket
import threading
import json
import time
import ssl
import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
import io
import base64
import pyperclip
import boto3
import queue
from datetime import datetime

# --- Configuration & Setup ---

def get_application_path():
    if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
    else:
        try: script_path = os.path.abspath(__file__)
        except NameError: script_path = os.getcwd()
        application_path = os.path.dirname(script_path)
    return application_path

try:
    APP_PATH = get_application_path()
    dotenv_path = os.path.join(APP_PATH, '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path)
    else: print(f"Warning: .env file not found at '{dotenv_path}'.")
except ImportError: print("Warning: python-dotenv not installed.")
except Exception as e: print(f"Error loading .env: {e}")

# --- Essential Config ---
OPENAI_API_KEY = "YOUR_OPEN_AI_API_KEY"

// Get from cloudformation outputs
WSS_URL = os.getenv("WSS_URL", "YOUR_WEBSOCKET_URL")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "YOUR_S3_BUCKET_NAME")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

// Create API key via aws api gateway console
WEBSOCKET_SHARED_SECRET="RANDOM_API_KEY"
# --- WebSocket Keep-Alive Configuration ---
WEBSOCKET_PING_INTERVAL = 60
WEBSOCKET_PING_TIMEOUT = 10

# --- Global State & Clients ---
is_processing = False
is_connected = False
ws_app_instance = None
ws_thread = None
ping_thread = None
ping_thread_stop_event = threading.Event()
s3_client = None
oai_client = None
gui_queue = queue.Queue()


# --- Initializers ---
def log_to_console(message, level="INFO"):
     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
     formatted_message = f"[{timestamp}][{level}] {message}"
     print(formatted_message)

def initialize_s3_client():
    global s3_client
    import botocore.session
# Create your own session
    my_session = boto3.session.Session()

    # Now we can create low-level clients or resource clients from our custom session
    log_to_console("WARNING: Boto3 SSL verification DISABLED!")
    try: s3_client = my_session.client('s3', verify=False); log_to_console("INFO: AWS S3 client initialized."); return True
    except Exception as e: log_to_console(f"CRITICAL ERROR: Init S3 client failed: {e}", "ERROR"); s3_client = None; return False

def initialize_openai_client():
    global oai_client
    if not OPENAI_API_KEY: log_to_console("ERROR: OPENAI_API_KEY missing.", "ERROR"); return False
    try:
        # Use this block if you NEED to disable SSL verification (NOT RECOMMENDED)
        import httpx
        unsafe_http_client = httpx.Client(verify=False)
        oai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=unsafe_http_client)
        log_to_console("WARNING: OpenAI client initialized with SSL VERIFICATION DISABLED.")

        oai_client.models.list(); log_to_console(f"INFO: OpenAI client OK (Model: {OPENAI_MODEL})."); return True
    except Exception as e: log_to_console(f"ERROR: Init OpenAI client failed: {e}", "ERROR"); oai_client = None; return False


# --- Worker Functions ---
def download_image_from_s3(bucket, key):
    if not s3_client: log_to_console("ERROR: S3 client not init.", "ERROR"); return None
    log_to_console(f"INFO: Downloading s3://{bucket}/{key}...")
    try:
        s3_response = s3_client.get_object(Bucket=bucket, Key=key)
        image_bytes = s3_response['Body'].read()
        log_to_console(f"INFO: Downloaded {len(image_bytes)} bytes from S3.")
        return image_bytes
    except s3_client.exceptions.NoSuchKey: log_to_console(f"ERROR: S3 Key not found: s3://{bucket}/{key}", "ERROR"); return None
    except Exception as e: log_to_console(f"ERROR: S3 download failed (Bucket: {bucket}, Key: {key}): {e}", "ERROR"); return None

def get_mcq_answer_from_image_threaded(image_bytes):
    global is_processing
    log_to_console("INFO: OpenAI Thread: Starting analysis...")
    if not oai_client:
        error_msg = "OpenAI client not initialized."; log_to_console(f"ERROR: {error_msg}", "ERROR")
        if gui_queue: gui_queue.put(("openai_result", f"Error: {error_msg}"))
        is_processing = False; return
    try:
        base64_image_for_api = base64.b64encode(image_bytes).decode('utf-8')
        image_url_content = f"data:image/png;base64,{base64_image_for_api}"
        prompt_text = ("Analyze image containing MCQ. Determine answer(s). Respond only with choice(s)/text.")
        response = oai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user","content": [{"type": "text", "text": prompt_text},{"type": "image_url","image_url": {"url": image_url_content, "detail": "high"}}]}],
            max_tokens=400)
        answer = response.choices[0].message.content.strip()
        log_to_console(f"INFO: OpenAI Thread: Analysis Complete. Snippet: {answer[:100]}...")
        if gui_queue: gui_queue.put(("openai_result", answer))
    except Exception as e:
        error_message = f"Error OpenAI API: {e}"; log_to_console(f"ERROR: OpenAI API Call Failed: {error_message}", "ERROR")
        if gui_queue: gui_queue.put(("openai_result", f"Error: {error_message}"))
    finally: is_processing = False; log_to_console("INFO: Processing flag reset by OpenAI thread.")

# --- WebSocket Callbacks ---
def on_message(ws, message):
    global is_processing
    log_to_console(f"<-- WSS Message Received (Length: {len(message)})")
    try:
        data = json.loads(message)
        action = data.get("action")
        if action == "processS3Image":
            log_to_console("INFO: 'processS3Image' action received.")
            if is_processing: log_to_console("WARNING: Already processing, ignoring.", "WARN"); return
            s3_key = data.get("s3Key")
            target_bucket = data.get("s3Bucket") or S3_BUCKET_NAME
            if not s3_key or not target_bucket:
                 log_to_console(f"ERROR: Missing s3Key/Bucket. Key:{s3_key}, Bucket:{target_bucket}", "ERROR"); return
            log_to_console(f"INFO: Processing requested for s3://{target_bucket}/{s3_key}")
            is_processing = True
            if gui_queue: gui_queue.put(("status", f"Processing S3: {s3_key[:20]}..."))
            image_bytes = download_image_from_s3(target_bucket, s3_key)
            if image_bytes:
                 threading.Thread(target=get_mcq_answer_from_image_threaded, args=(image_bytes,), daemon=True).start()
            else: log_to_console("ERROR: Img download failed.", "ERROR"); gui_queue.put(("status", "Error: DL Failed.")); is_processing = False
        elif action == "error": log_to_console(f"ERROR relayed via WSS: {data.get('message', 'Unknown')}", "ERROR")
        else: log_to_console(f"INFO: Unhandled WSS action: '{action}'", "WARN")
    except json.JSONDecodeError: log_to_console(f"WARNING: Non-JSON WSS message: {message[:200]}...", "WARN")
    except Exception as e: log_to_console(f"ERROR: Processing WSS message: {e}", "ERROR"); is_processing = False

def on_error(ws, error):
    log_to_console(f"--- WebSocket Error: {error} ---", "ERROR")
    if gui_queue: gui_queue.put(("connection_state", False)); gui_queue.put(("status", f"WebSocket Error: Check Logs"))

def on_close(ws, close_status_code, close_msg):
    status_str = f"Status:{close_status_code}" if close_status_code else "N/A"
    msg_str = f"Msg:{close_msg}" if close_msg else "N/A"
    log_to_console(f"### WebSocket Closed ### {status_str}, {msg_str}", "WARN")
    if gui_queue: gui_queue.put(("connection_state", False)); gui_queue.put(("status", "WebSocket Disconnected."))
    if ping_thread_stop_event: ping_thread_stop_event.set()

def on_open(ws):
    log_to_console("### WebSocket Connection Opened ###")
    log_to_console(f"Connected to endpoint (via auth param). Base URL: {WSS_URL}")
    if gui_queue: gui_queue.put(("connection_state", True)); gui_queue.put(("status", "WebSocket Connected. Listening..."))
    global ping_thread, ping_thread_stop_event
    ping_thread_stop_event.clear()
    def ws_ping_thread_worker():
        global ws_app_instance
        log_to_console("INFO: Ping Thread Started.", "DEBUG")
        while not ping_thread_stop_event.is_set():
            try:
                if ws_app_instance and ws_app_instance.sock and ws_app_instance.sock.connected:
                     log_to_console("-> Sending WebSocket PING frame", "DEBUG")
                     ws_app_instance.send(data=None, opcode=websocket.ABNF.OPCODE_PING)
                     ping_thread_stop_event.wait(timeout=WEBSOCKET_PING_INTERVAL)
                else: log_to_console("INFO: Ping Thread: Socket not connected.", "DEBUG"); break
            except websocket.WebSocketConnectionClosedException: log_to_console("INFO: Ping Thread: Connection closed.", "WARN"); break
            except Exception as e: log_to_console(f"ERROR: Ping thread exception: {e}", "ERROR"); break
        log_to_console("INFO: Ping Thread Exited.", "DEBUG")
    ping_thread = threading.Thread(target=ws_ping_thread_worker, daemon=True)
    ping_thread.start()

# --- GUI Application Class ---
class HostAppGUI:
    def __init__(self, master):
        self.master = master
        master.title("MCQ Solver Host Listener v2.1 (Secured)")
        master.geometry("700x600")
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.mono_font = tkfont.Font(family="Consolas", size=10)
        self.status_font = tkfont.Font(family=self.default_font.actual("family"), size=10, weight="bold")
        master.tk_setPalette(background='#ececec', foreground='black')
        log_bg, answer_bg, status_bar_bg, button_frame_bg = "#f0f0f0", "#ffffff", "#e0e0e0", "#d9d9d9"

        button_frame = tk.Frame(master, relief=tk.RAISED, bd=2, bg=button_frame_bg)
        button_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        style = ttk.Style(); style.configure("Connect.TButton", padding=6); style.configure("Disconnect.TButton", padding=6)
        self.connect_button = ttk.Button(button_frame, text="Connect WebSocket", command=self.connect_websocket, style="Connect.TButton")
        self.connect_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.disconnect_button = ttk.Button(button_frame, text="Disconnect WebSocket", command=self.disconnect_websocket, state=tk.DISABLED, style="Disconnect.TButton")
        self.disconnect_button.pack(side=tk.LEFT, padx=10, pady=5)

        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(master, textvariable=self.status_var, font=self.status_font, bd=1, relief=tk.SUNKEN, anchor=tk.W, padx=5, bg=status_bar_bg)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.pane = tk.PanedWindow(master, orient=tk.VERTICAL, sashrelief=tk.RAISED, bd=2)
        self.pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        log_frame = tk.Frame(self.pane, bd=1, relief=tk.SUNKEN)
        tk.Label(log_frame, text="Event Log:", font=self.default_font).pack(anchor=tk.NW, padx=5, pady=2)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, font=self.mono_font, bg=log_bg)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5)); self.log_text.configure(state='disabled')
        self.pane.add(log_frame, stretch="always")
        answer_frame = tk.Frame(self.pane, bd=1, relief=tk.SUNKEN)
        tk.Label(answer_frame, text="Last Received Answer:", font=self.default_font).pack(anchor=tk.NW, padx=5, pady=2)
        self.answer_text = scrolledtext.ScrolledText(answer_frame, wrap=tk.WORD, height=12, font=self.default_font, bg=answer_bg)
        self.answer_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5)); self.answer_text.configure(state='disabled')
        self.pane.add(answer_frame, stretch="always"); self.pane.sash_place(0, 0, 280)

        self._is_connected = False
        master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.log_message("--- Initializing Clients & Config ---", "INFO")
        if not self._validate_config():
             self.status_var.set("Config Error! Check .env/script & logs.")
             messagebox.showerror("Config Error", "Essential configuration missing. Check logs & .env.")
             master.after(100, master.destroy); return
        if not s3_client: self.status_var.set("S3 Init Failed!")
        elif not oai_client: self.status_var.set("OpenAI Init Failed!")
        else: self.status_var.set("Ready to Connect.")

        self.master.after(100, self._process_gui_queue)
        self.log_message("--- Host App GUI Ready ---", "INFO")
        self.update_button_states()

    def log_message(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}][{level}] {message}\n"
        print(formatted_message.strip())
        if gui_queue: gui_queue.put(("log", formatted_message))

    def _validate_config(self, check_only=False):
        ok = True; log_prefix = "" if check_only else "CRITICAL ERROR: "; log_level = "INFO" if check_only else "ERROR"
        def log_or_check(msg, level):
            if not check_only: self.log_message(msg, level)
        if not WSS_URL or WSS_URL == "YOUR_WEBSOCKET_API_ENDPOINT_HERE": log_or_check(f"{log_prefix}WSS_URL missing.", log_level); ok = False
        if not OPENAI_API_KEY: log_or_check(f"{log_prefix}OPENAI_API_KEY missing.", log_level); ok = False
        if not S3_BUCKET_NAME or S3_BUCKET_NAME == "YOUR_S3_BUCKET_NAME_HERE": log_or_check(f"{log_prefix}S3_BUCKET_NAME missing.", log_level); ok = False
        if not WEBSOCKET_SHARED_SECRET or WEBSOCKET_SHARED_SECRET == "YourSuperSecretValueHere123!@#": log_or_check(f"{log_prefix}WEBSOCKET_SECRET missing.", log_level); ok = False
        if not s3_client and not check_only: log_or_check(f"{log_prefix}S3 client failed init.", log_level); ok = False
        if not oai_client and not check_only: log_or_check(f"{log_prefix}OpenAI client failed init.", log_level); ok = False
        if not check_only and not ok: messagebox.showerror("Config Error", "Essential config/clients failed. Check logs & .env.")
        return ok

    def update_button_states(self):
        if self._is_connected:
            self.connect_button.config(state=tk.DISABLED); self.disconnect_button.config(state=tk.NORMAL)
        else:
            can_connect = s3_client and oai_client and self._validate_config(check_only=True)
            self.connect_button.config(state=tk.NORMAL if can_connect else tk.DISABLED); self.disconnect_button.config(state=tk.DISABLED)

    def connect_websocket(self):
        global ws_app_instance, ws_thread
        if self._is_connected: self.log_message("INFO: Already connected.", "WARN"); return
        if not self._validate_config(): return

        target_wss_url = WSS_URL
        if WEBSOCKET_SHARED_SECRET: target_wss_url = f"{WSS_URL}?auth={WEBSOCKET_SHARED_SECRET}"
        else: self.log_message("WARNING: WEBSOCKET_SECRET missing. Connecting without auth param.", "WARN")

        self.log_message(f"INFO: Attempting connection to WebSocket (using auth param)... Base: {WSS_URL}")
        self._update_status_bar("Connecting WebSocket..."); self.connect_button.config(state=tk.DISABLED)
        ping_thread_stop_event.clear()
        ssl_opts = {}
        self.log_message(f"DEBUG_SECRET_CHECK: Secret read by host app = '{WEBSOCKET_SHARED_SECRET}'") # Check value read
        self.log_message(f"DEBUG_SECRET_CHECK: Full URL being used = '{target_wss_url}'") # Check URL construction
        # Uncomment below ONLY if you have SSL verification issues AND understand the risk
        # if target_wss_url.startswith("wss://"): ssl_opts = {"sslopt": {"cert_reqs": ssl.CERT_NONE}}

        ws_app = websocket.WebSocketApp(target_wss_url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
        ws_app_instance = ws_app
        ws_thread = threading.Thread(target=ws_app.run_forever, kwargs=ssl_opts, daemon=True)
        ws_thread.start()

    def disconnect_websocket(self):
        global ws_app_instance, ping_thread_stop_event
        if not self._is_connected: self.log_message("INFO: Not currently connected.", "WARN"); return
        self.log_message("INFO: Disconnecting WebSocket...", "WARN"); self.disconnect_button.config(state=tk.DISABLED)
        self._update_status_bar("Disconnecting...")
        ping_thread_stop_event.set()
        if ws_app_instance:
            try: ws_app_instance.close()
            except Exception as e: self.log_message(f"WARN: Error on ws_app.close(): {e}", "WARN")

    def _update_log_widget(self, message):
        self.log_text.configure(state='normal'); self.log_text.insert(tk.END, message); self.log_text.see(tk.END); self.log_text.configure(state='disabled')

    def _update_answer_widget(self, answer):
        self.answer_text.configure(state='normal'); self.answer_text.delete('1.0', tk.END); self.answer_text.insert('1.0', answer); self.answer_text.configure(state='disabled')
        try: pyperclip.copy(answer); self.log_message("INFO: Answer copied to clipboard!", "INFO")
        except Exception as e: self.log_message(f"ERROR: Failed copy to clipboard: {e}", "ERROR")

    def _update_status_bar(self, status_text): self.status_var.set(status_text)

    def _update_connection_state(self, connected_bool):
        self._is_connected = connected_bool; self.log_message(f"INFO: GUI Connection state set: {self._is_connected}", "DEBUG"); self.update_button_states()

    def _process_gui_queue(self):
        try:
            while True:
                message_type, data = gui_queue.get_nowait()
                if message_type == "log": self._update_log_widget(data)
                elif message_type == "status": self._update_status_bar(data)
                elif message_type == "openai_result":
                     self._update_answer_widget(data)
                     status_msg = "Ready. Listening..." if self._is_connected else "Ready to Connect."
                     if isinstance(data, str) and data.startswith("Error:"): status_msg = "Error Processing. Check log."
                     self._update_status_bar(status_msg)
                elif message_type == "connection_state": self._update_connection_state(data)
                else: log_to_console(f"WARN: Unknown GUI queue type: {message_type}", "WARN")
        except queue.Empty: pass
        finally: self.master.after(100, self._process_gui_queue)

    def on_closing(self):
        self.log_message("--- Shutdown Requested ---", "WARN")
        if messagebox.askokcancel("Quit", "Disconnect WebSocket and exit?"):
             ping_thread_stop_event.set()
             if self._is_connected: self.disconnect_websocket()
             time.sleep(0.1)
             self.log_message("INFO: Closing GUI window.")
             self.master.destroy()
        else: self.log_message("INFO: Shutdown cancelled.", "INFO")


# --- Main Execution ---
if __name__ == "__main__":
    log_to_console("--- Host App Starting Init (Manual Connect GUI - Secured) ---")
    s3_ok = initialize_s3_client()
    oai_ok = initialize_openai_client()

    root = tk.Tk()
    app_gui = HostAppGUI(root)
    root.mainloop()

    log_to_console("--- Host App Main Process Exiting ---")