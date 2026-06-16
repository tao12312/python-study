import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import json
import os
import datetime
import subprocess
import sys
import random
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import threading
import time
import base64
import hashlib
import shutil

# ==========================================
# 0. API 설정 (사용자 입력)
# ==========================================
# Vertex AI 서비스 계정 JSON 키를 아래 큰따옴표 3개 안에 그대로 붙여넣으세요.
# 예: VERTEX_SERVICE_ACCOUNT_JSON = """{ "type": "service_account", ... }"""
VERTEX_SERVICE_ACCOUNT_JSON = r""""""
VERTEX_PROJECT_ID = ""                       # 비워두면 JSON 키의 project_id를 사용합니다.
VERTEX_LOCATION = "global"
PROBLEM_GEMINI_MODEL = "gemini-3.5-flash"                    # 문제 출제 전용 모델명 입력칸. 비워두면 아래 피드백 모델을 사용합니다.
GEMINI_MODEL = "gemini-3.1-flash-lite"       # 피드백/주관식 채점용 모델
API_CALL_DELAY_SECONDS = 4.0                # API 호출 사이 최소 휴식 시간
API_MAX_RETRIES = 3                         # 429 등 일시 오류 재시도 횟수
API_RETRY_BASE_DELAY_SECONDS = 8.0          # 429 재시도 기본 대기 시간
API_MAX_OUTPUT_TOKENS = 10000               # AI 응답 최대 출력 토큰
_api_rate_lock = threading.Lock()
_last_api_call_at = 0.0
_vertex_token_cache = {"access_token": None, "expires_at": 0}

# ==========================================
# 1. 환경 설정 및 상수 정의
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CONCEPTS_DIR = os.path.join(BASE_DIR, "concepts")
CONFIG_FILE = os.path.join(BASE_DIR, "prompts.json")
APP_STATE_FILE = os.path.join(BASE_DIR, "app_state.json")

REQUIRED_PROMPT_CONFIG = {
    "system_prompt": "",
    "schema_prompt": "",
    "mode_notes": {
        "python": "",
        "ex": ""
    },
    "mode_prompts": {
        "concept": "",
        "learning": "",
        "test": ""
    },
    "type_prompts": {
        "objective": "",
        "subjective": ""
    },
    "ex_type_prompts": {
        "objective": "",
        "subjective": ""
    },
    "request_prompts": {
        "concept": "",
        "learning": "",
        "test": ""
    },
    "feedback_prompt": "",
    "ex_feedback_prompt": ""
}

# 테마 컬러 정의 (Modern White Mode Theme)
COLOR_BG = "#ffffff"          # 전체 배경색 (순수 흰색)
COLOR_CARD = "#ffffff"        # 카드/컨테이너 배경색 (흰색)
COLOR_HEADER = "#1f2937"      # 헤더 배경색 (진한 그레이)
COLOR_NAV_BG = "#ffffff"      # 네비게이션 바 배경
COLOR_NAV_BORDER = "#e5e7eb"  # 네비게이션 보더
COLOR_PRIMARY = "#3b82f6"     # 주조색 (파랑)
COLOR_PRIMARY_HOVER = "#2563eb" # 파랑 호버
COLOR_DARK = "#1f2937"        # 어두운 색 (텍스트 및 헤더)
COLOR_TEXT = "#111827"        # 주 텍스트
COLOR_TEXT_MUTED = "#6b7280"  # 연한 텍스트 (그레이)
COLOR_SUCCESS = "#10b981"     # 성공/정답 (초록)
COLOR_SUCCESS_LIGHT = "#ecfdf5"# 연한 초록 (배경용)
COLOR_ERROR = "#ef4444"       # 실패/오답 (빨강)
COLOR_ERROR_LIGHT = "#fef2f2"  # 연한 빨강 (배경용)
COLOR_BORDER = "#e5e7eb"      # 보더/구분선
COLOR_BUTTON_BG = "#f3f4f6"   # 버튼 배경 (밝은 회색)

def list_concept_files():
    try:
        files = [f for f in os.listdir(CONCEPTS_DIR) if f.endswith(".txt")]
        files.sort()
        return files
    except Exception:
        return []

def safe_concept_filename(title):
    safe = "".join(ch if ch.isalnum() or ch in (" ", "_", "-") else "_" for ch in title.strip())
    safe = safe.replace(" ", "_").strip("_")
    return f"{safe or 'concept'}.txt"

def load_all_concepts_content(selected_files=None):
    """concepts 폴더의 모든 .txt 개념글 목록 및 내용을 로드합니다."""
    concepts_text = ""
    try:
        if os.path.exists(CONCEPTS_DIR):
            files = selected_files if selected_files else list_concept_files()
            for f in files:
                title = f.replace(".txt", "").replace("_", " ")
                filepath = os.path.join(CONCEPTS_DIR, f)
                with open(filepath, "r", encoding="utf-8") as file:
                    content = file.read()
                concepts_text += f"=== 단원 제목: {title} ===\n{content}\n\n"
    except Exception as e:
        print(f"개념을 읽는 도중 오류가 발생했습니다: {e}")
    if not concepts_text:
        concepts_text = "개념이 로드되지 않았습니다. 기본 파이썬 개념(변수, 자료형, 조건문, 반복문, 함수, 클래스 등)을 기반으로 문제를 출제해 주세요."
    return concepts_text

def load_single_concept_content(filename):
    """지정된 파일명의 개념글 내용을 로드합니다."""
    try:
        title = filename.replace(".txt", "").replace("_", " ")
        filepath = os.path.join(CONCEPTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read()
        return f"=== 단원 제목: {title} ===\n{content}"
    except Exception as e:
        return f"개념을 읽을 수 없습니다: {e}"

def make_empty_prompt_config():
    return {"config": json.loads(json.dumps(REQUIRED_PROMPT_CONFIG, ensure_ascii=False))}

def merge_prompt_config_shape(config_data):
    if not isinstance(config_data, dict):
        config_data = {}
    cfg = config_data.setdefault("config", {})
    for key, value in REQUIRED_PROMPT_CONFIG.items():
        if isinstance(value, dict):
            target = cfg.setdefault(key, {})
            if not isinstance(target, dict):
                cfg[key] = value.copy()
                continue
            for sub_key, sub_value in value.items():
                target.setdefault(sub_key, sub_value)
        else:
            cfg.setdefault(key, value)
    return config_data

def clean_json_string(s):
    """Gemini API 응답에서 첫 JSON 객체/배열만 추출합니다."""
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    decoder = json.JSONDecoder()
    for start, ch in enumerate(s):
        if ch not in "{[":
            continue
        candidate = s[start:]
        try:
            _, end = decoder.raw_decode(candidate)
            return candidate[:end].strip()
        except json.JSONDecodeError:
            continue
    return s

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def der_read_length(data, pos):
    first = data[pos]
    pos += 1
    if first < 0x80:
        return first, pos
    size = first & 0x7F
    return int.from_bytes(data[pos:pos + size], "big"), pos + size

def der_read_tlv(data, pos):
    tag = data[pos]
    pos += 1
    length, pos = der_read_length(data, pos)
    value = data[pos:pos + length]
    return tag, value, pos + length

def der_read_integer(data, pos):
    tag, value, pos = der_read_tlv(data, pos)
    if tag != 0x02:
        raise ValueError("RSA 키 파싱 실패: INTEGER가 필요합니다.")
    return int.from_bytes(value, "big", signed=False), pos

def pem_to_der(pem):
    lines = [line.strip() for line in pem.strip().splitlines() if line and not line.startswith("-----")]
    return base64.b64decode("".join(lines))

def parse_rsa_private_numbers_from_der(der):
    tag, seq, _ = der_read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("RSA 키 파싱 실패: SEQUENCE가 필요합니다.")
    pos = 0
    _, pos = der_read_integer(seq, pos)
    if pos < len(seq) and seq[pos] == 0x30:
        _, _, pos = der_read_tlv(seq, pos)
        if pos < len(seq) and seq[pos] == 0x04:
            _, private_octets, _ = der_read_tlv(seq, pos)
            return parse_rsa_private_numbers_from_der(private_octets)
    pos = 0
    _, pos = der_read_integer(seq, pos)
    n, pos = der_read_integer(seq, pos)
    _, pos = der_read_integer(seq, pos)
    d, pos = der_read_integer(seq, pos)
    return n, d

def rsa_sha256_sign(private_key_pem, message):
    n, d = parse_rsa_private_numbers_from_der(pem_to_der(private_key_pem))
    key_len = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(message).digest()
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + digest
    padding_len = key_len - len(digest_info) - 3
    if padding_len < 8:
        raise ValueError("RSA 키 길이가 너무 짧습니다.")
    encoded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    return pow(int.from_bytes(encoded, "big"), d, n).to_bytes(key_len, "big")

def load_vertex_service_account():
    raw = VERTEX_SERVICE_ACCOUNT_JSON.strip()
    if not raw:
        raise ValueError("VERTEX_SERVICE_ACCOUNT_JSON에 Vertex AI 서비스 계정 JSON 키를 붙여넣어 주세요.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"서비스 계정 JSON 형식이 올바르지 않습니다: {e}")

    missing = [key for key in ("project_id", "client_email", "private_key") if not str(data.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Vertex 서비스 계정 JSON에 필수 값이 없습니다: {', '.join(missing)}")
    return data

def get_vertex_access_token():
    cached = _vertex_token_cache.get("access_token")
    if cached and time.time() < _vertex_token_cache.get("expires_at", 0) - 60:
        return cached
    service_account = load_vertex_service_account()
    client_email = service_account.get("client_email")
    private_key = service_account.get("private_key")
    if not client_email or not private_key:
        raise ValueError("서비스 계정 JSON에 client_email/private_key가 없습니다.")
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": client_email,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600
    }
    signing_input = f"{b64url(json.dumps(header, separators=(',', ':')).encode())}.{b64url(json.dumps(claim, separators=(',', ':')).encode())}".encode()
    assertion = signing_input.decode() + "." + b64url(rsa_sha256_sign(private_key, signing_input))
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        token_data = json.loads(response.read().decode("utf-8"))
    _vertex_token_cache["access_token"] = token_data["access_token"]
    _vertex_token_cache["expires_at"] = time.time() + int(token_data.get("expires_in", 3600))
    return token_data["access_token"]

def call_generative_api_raw(prompt, system_prompt=None, model_name=None):
    """Gemini API를 REST 호출 형태로 통신합니다."""
    global _last_api_call_at
    service_account = load_vertex_service_account()
    project_id = VERTEX_PROJECT_ID.strip() or service_account.get("project_id")
    if not project_id:
        raise ValueError("VERTEX_PROJECT_ID가 비어 있고 서비스 계정 JSON에도 project_id가 없습니다.")
    location = VERTEX_LOCATION.strip() or "global"
    selected_model = (model_name or GEMINI_MODEL).strip()
    if not selected_model:
        raise ValueError("사용할 Gemini 모델명이 비어 있습니다.")
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    url = (
        f"https://{host}/v1/projects/{project_id}/locations/{location}"
        f"/publishers/google/models/{selected_model}:generateContent"
    )
    access_token = get_vertex_access_token()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "contents": [{
            "role": "user",    
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7,
            "maxOutputTokens": API_MAX_OUTPUT_TOKENS
        }
    }
    
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{
                "text": system_prompt
            }]
        }
        
    body = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(API_MAX_RETRIES + 1):
        with _api_rate_lock:
            wait_seconds = API_CALL_DELAY_SECONDS - (time.time() - _last_api_call_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            _last_api_call_at = time.time()

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return text
        except urllib.error.HTTPError as e:
            try:
                err_msg = e.read().decode("utf-8")
            except Exception:
                err_msg = str(e)
            last_error = RuntimeError(f"{e} - {err_msg}")
            if e.code == 429 and attempt < API_MAX_RETRIES:
                time.sleep(API_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
                continue
            raise last_error
        except Exception as e:
            if hasattr(e, "read"):
                try:
                    err_msg = e.read().decode("utf-8")
                    last_error = RuntimeError(f"{e} - {err_msg}")
                except Exception:
                    last_error = RuntimeError(str(e))
            else:
                last_error = RuntimeError(str(e))
            if attempt < API_MAX_RETRIES:
                time.sleep(2)
                continue
            raise last_error
    raise last_error or RuntimeError("API 호출에 실패했습니다.")

def ensure_environment():
    """기본 폴더가 존재하는지 확인합니다."""
    if not os.path.exists(LIBRARY_DIR):
        os.makedirs(LIBRARY_DIR)
    if not os.path.exists(CONCEPTS_DIR):
        os.makedirs(CONCEPTS_DIR)

# ==========================================
# 2. UI 공통 컴포넌트 및 유틸 클래스
# ==========================================
def create_flat_button(parent, text, bg, fg, hover_bg, command, font=("Malgun Gothic", 10, "bold"), **kwargs):
    """마우스 호버 효과가 있는 플랫한 현대적 버튼을 생성합니다."""
    btn = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=hover_bg, activeforeground=fg,
                    font=font, relief="flat", bd=0, cursor="hand2", command=command, **kwargs)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg) if btn['state'] != 'disabled' else None)
    btn.bind("<Leave>", lambda e: btn.config(bg=bg) if btn['state'] != 'disabled' else None)
    return btn

def estimate_text_height(text, width_chars=72, min_height=2, max_height=6):
    """긴 문제 본문은 고정 높이 안에서 스크롤되도록 대략적인 줄 수를 계산합니다."""
    lines = 0
    for line in str(text).splitlines() or [""]:
        lines += max(1, (len(line) // width_chars) + 1)
    return max(min_height, min(max_height, lines))

def create_scrollable_question_box(parent, text, bg=COLOR_CARD, fg=COLOR_DARK, font=("Malgun Gothic", 12, "bold"),
                                   min_height=2, max_height=6, width_chars=72):
    """문제 본문용 읽기 전용 스크롤 박스."""
    frame = tk.Frame(parent, bg=bg, bd=1, relief="solid", highlightthickness=0)
    line_count = estimate_text_height(text, width_chars=width_chars, min_height=1, max_height=999)
    height = estimate_text_height(text, width_chars=width_chars, min_height=min_height, max_height=max_height)
    needs_scroll = line_count > max_height
    
    scrollbar = ttk.Scrollbar(frame, orient="vertical")
    text_widget = tk.Text(frame, wrap="word", height=height, font=font, bg=bg, fg=fg,
                          relief="flat", bd=0, padx=10, pady=8, cursor="arrow",
                          yscrollcommand=scrollbar.set)
    scrollbar.config(command=text_widget.yview)
    
    text_widget.insert("1.0", text)
    text_widget.config(state="disabled")
    text_widget.pack(side="left", fill="both", expand=True)
    if needs_scroll:
        scrollbar.pack(side="right", fill="y")
    
    def on_question_wheel(event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = int(-1 * (event.delta / 120))
        text_widget.yview_scroll(delta, "units")
        return "break"
    
    if needs_scroll:
        text_widget.bind("<MouseWheel>", on_question_wheel)
        text_widget.bind("<Button-4>", on_question_wheel)
        text_widget.bind("<Button-5>", on_question_wheel)
    return frame

class ScrollableFrame(tk.Frame):
    """스크롤이 가능한 프레임 클래스 (Canvas + Scrollbar)"""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=COLOR_BG)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # 마우스 휠 바인딩 (컴포넌트에 진입/퇴출 시 활성화)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.scrollable_frame.bind("<Button-4>", self._on_mousewheel)
        self.scrollable_frame.bind("<Button-5>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        
    def bind_children_to_mousewheel(self, widget=None):
        """Bind wheel events to all current descendants of the scroll area."""
        widget = widget or self.scrollable_frame
        for child in widget.winfo_children():
            child.bind("<MouseWheel>", self._on_mousewheel, add="+")
            child.bind("<Button-4>", self._on_mousewheel, add="+")
            child.bind("<Button-5>", self._on_mousewheel, add="+")
            self.bind_children_to_mousewheel(child)

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = int(-1 * (event.delta / 120))
        self.canvas.yview_scroll(delta, "units")
        return "break"

# ==========================================
# 2-1. 네비게이션 바 컴포넌트
# ==========================================
class NavigationBar(tk.Frame):
    """상단에 고정되는 네비게이션 바"""
    def __init__(self, parent, app_ref, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app = app_ref
        self.config(bg=COLOR_NAV_BG, height=50)
        
        # 구분선 (보더)
        border = tk.Frame(self, bg=COLOR_NAV_BORDER, height=1)
        border.pack(fill="x", side="bottom")
        
        # 네비게이션 콘텐츠
        nav_content = tk.Frame(self, bg=COLOR_NAV_BG)
        nav_content.pack(fill="x", padx=15, pady=8)
        
        # 좌측: 메뉴 + 홈 + 이전 버튼
        left_frame = tk.Frame(nav_content, bg=COLOR_NAV_BG)
        left_frame.pack(side="left", fill="x", expand=False)
        
        self.menu_btn = create_flat_button(
            left_frame, "☰ 목록", COLOR_BUTTON_BG, COLOR_DARK, COLOR_BORDER,
            lambda: self.app.toggle_sidebar(),
            font=("Malgun Gothic", 9, "bold")
        )
        self.menu_btn.pack(side="left", padx=2, ipady=4, ipadx=8)
        
        create_flat_button(
            left_frame, "🏠 홈", COLOR_BUTTON_BG, COLOR_DARK, COLOR_BORDER,
            self.app.show_main_menu,
            font=("Malgun Gothic", 9, "bold")
        ).pack(side="left", padx=2, ipady=4, ipadx=8)
        
        self.back_btn = create_flat_button(
            left_frame, "⬅ 이전", COLOR_BUTTON_BG, COLOR_DARK, COLOR_BORDER,
            self.app.go_back,
            font=("Malgun Gothic", 9, "bold")
        )
        self.back_btn.pack(side="left", padx=2, ipady=4, ipadx=8)
        
        # 우측: 정보 + 종료 버튼
        right_frame = tk.Frame(nav_content, bg=COLOR_NAV_BG)
        right_frame.pack(side="right", fill="x", expand=False)
        
        self.info_label = tk.Label(right_frame, text="", font=("Malgun Gothic", 9), 
                                   fg=COLOR_TEXT_MUTED, bg=COLOR_NAV_BG)
        self.info_label.pack(side="left", padx=10)
        
        create_flat_button(
            right_frame, "❌ 종료", "#fecaca", "#dc2626", "#fca5a5",
            self.app.quit,
            font=("Malgun Gothic", 9, "bold")
        ).pack(side="right", padx=2, ipady=4, ipadx=8)
        
    def update_info(self, text):
        """정보 라벨 업데이트"""
        self.info_label.config(text=text)

# ==========================================
# 2-2. 사이드 패널 (목록)
# ==========================================
class SidebarPanel(tk.Frame):
    """좌측 사이드 패널 (섹션 기반 메뉴)"""
    def __init__(self, parent, app_ref, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.app = app_ref
        self.config(bg=COLOR_CARD, width=250)
        
        # 패널 헤더
        header = tk.Frame(self, bg=COLOR_HEADER)
        header.pack(fill="x", padx=0, pady=0)
        
        title = tk.Label(header, text="🐍 학습 내용", font=("Malgun Gothic", 12, "bold"),
                        fg="#ffffff", bg=COLOR_HEADER)
        title.pack(padx=15, pady=10)
        
        # 스크롤 프레임
        canvas_frame = tk.Frame(self, bg=COLOR_CARD)
        canvas_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(canvas_frame, bg=COLOR_CARD, highlightthickness=0, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.canvas.yview)
        
        self.scroll_frame = tk.Frame(self.canvas, bg=COLOR_CARD)
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 마우스 휠 스크롤
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # 섹션 1: 개념모드
        self._create_section("📚 개념모드", "concept")
        
        # 섹션 2: 학습모드
        self._create_learning_section()
        
        # 섹션 3: 시험모드
        self._create_section("✏️ 시험모드", "test")
        
        # 섹션 4: 기록실
        self._create_section("📊 기록실", "library")
    
    def _create_section(self, title, mode):
        """메뉴 섹션 생성"""
        section_frame = tk.Frame(self.scroll_frame, bg=COLOR_CARD)
        section_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # 섹션 제목
        title_label = tk.Label(section_frame, text=title, font=("Malgun Gothic", 10, "bold"),
                               fg=COLOR_PRIMARY, bg=COLOR_CARD)
        title_label.pack(anchor="w", pady=(0, 5))
        
        if mode == "concept":
            # 개념 목록
            concepts = list_concept_files()
            for idx, concept in enumerate(concepts):
                label = concept.replace(".txt", "").replace("_", " ")
                btn_text = f"• {label}"
                btn = create_flat_button(section_frame, btn_text, COLOR_BUTTON_BG, COLOR_DARK, "#e5e7eb",
                                        lambda c=concept: self._on_concept_click(c),
                                        font=("Malgun Gothic", 9))
                btn.pack(fill="x", pady=2)
        
        elif mode == "test":
            btn = create_flat_button(section_frame, "⏱️ 시험 시작", COLOR_ERROR, "#ffffff", "#dc2626",
                                    lambda: self._navigate_to("test"),
                                    font=("Malgun Gothic", 9, "bold"))
            btn.pack(fill="x", pady=2)
        
        elif mode == "library":
            btn = create_flat_button(section_frame, "📈 성적 조회", COLOR_SUCCESS, "#ffffff", "#059669",
                                    lambda: self._navigate_to("library"),
                                    font=("Malgun Gothic", 9, "bold"))
            btn.pack(fill="x", pady=2)
    
    def _create_learning_section(self):
        """학습모드 섹션 (객관식/주관식)"""
        section_frame = tk.Frame(self.scroll_frame, bg=COLOR_CARD)
        section_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        title_label = tk.Label(section_frame, text="⚡ 학습모드", font=("Malgun Gothic", 10, "bold"),
                               fg=COLOR_PRIMARY, bg=COLOR_CARD)
        title_label.pack(anchor="w", pady=(0, 5))
        
        btn_obj = create_flat_button(section_frame, "📝 객관식 학습", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER,
                                     lambda: self._navigate_to("learning_obj"),
                                     font=("Malgun Gothic", 9))
        btn_obj.pack(fill="x", pady=2)
        
        btn_sub = create_flat_button(section_frame, "💻 주관식 학습", "#319795", "#ffffff", "#2c7a7b",
                                     lambda: self._navigate_to("learning_sub"),
                                     font=("Malgun Gothic", 9))
        btn_sub.pack(fill="x", pady=2)
    
    def _on_concept_click(self, filename):
        """개념 클릭"""
        self.app.show_concept_content(filename)
        self.app.toggle_sidebar(False)  # 사이드바 자동 닫기
    
    def _navigate_to(self, mode):
        """네비게이션"""
        if mode == "test":
            self.app.start_test_mode()
        elif mode == "library":
            self.app.show_library()
        elif mode == "learning_obj":
            self.app.start_learning_session("objective")
        elif mode == "learning_sub":
            self.app.start_learning_session("subjective")
        self.app.toggle_sidebar(False)  # 사이드바 자동 닫기
    
    def _on_concept_select(self, event):
        """개념 더블클릭 시"""
        selection = self.concept_listbox.curselection()
        if selection:
            idx = selection[0]
            concepts = list_concept_files()
            if 0 <= idx < len(concepts):
                # 개념 뷰 화면으로
                self.app.show_concept_content(concepts[idx])

# ==========================================
# 3. 메인 애플리케이션 클래스
# ==========================================
class PythonTutorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Python Learning Program")
        self.geometry("1100x750")
        self.configure(bg=COLOR_BG)
        
        # 상태 변수 (State)
        self.current_session_quizzes = [] # 현재 세션에서 풀 문제 리스트 (최대 10개)
        self.current_q_index = 0     # 현재 문제 인덱스 (개념, 학습모드용)
        self.session_results = []    # 풀이 결과 리스트
        self.current_mode = ""       # "concept", "learning", "test"
        self.selected_concepts = []
        self.ex_mode = False
        
        # 네비게이션 상태
        self.navigation_stack = []   # 뒤로가기 스택
        self.sidebar_visible = False # 사이드바 표시 여부
        
        # 시험 모드용 타이머
        self.test_timer_id = None
        self.test_remaining_time = 0
        
        # 시험 모드용 임시 저장 변수
        # 구조: { quiz_id: { "objective_ans": int, "subjective_code": str, "saved": bool } }
        self.test_temp_answers = {}
        self.test_answer_widgets = {}
        
        # UI 프레임 참조 변수
        self.main_container = None
        self.navigation_bar = None
        self.sidebar_panel = None
        
        # 초기화 및 메뉴 렌더링
        ensure_environment()
        self.load_config()
        self.ensure_config_defaults()
        self.load_app_state()
        self.setup_ui_layout()
        self.show_main_menu()

    def load_config(self):
        """prompts.json에서 프롬프트 설정을 로드하거나 없으면 빈 구조를 생성합니다."""
        default_config = make_empty_prompt_config()
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    raw = f.read()
                self.config_data = json.loads(clean_json_string(raw))
            else:
                self.config_data = default_config
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.config_data = default_config
            print(f"설정 로드 중 오류 발생: {e}")

    def load_app_state(self):
        self.selected_concepts = []
        self.ex_mode = False
        try:
            if os.path.exists(APP_STATE_FILE):
                with open(APP_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                available = set(list_concept_files())
                self.selected_concepts = [f for f in data.get("selected_concepts", []) if f in available]
                self.ex_mode = bool(data.get("ex_mode", False))
        except Exception as e:
            print(f"앱 상태 로드 실패: {e}")

    def save_app_state(self):
        data = {
            "selected_concepts": self.selected_concepts,
            "ex_mode": self.ex_mode
        }
        try:
            with open(APP_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"앱 상태 저장 실패: {e}")

    def get_active_concept_files(self):
        available = list_concept_files()
        selected = [f for f in self.selected_concepts if f in available]
        return selected or available

    def get_active_scope_label(self):
        active = self.get_active_concept_files()
        if not active:
            return "출제 범위: 개념서 없음"
        if len(active) == len(list_concept_files()):
            return f"출제 범위: 전체 개념서 {len(active)}개"
        return f"출제 범위: 선택 개념서 {len(active)}개"

    # ==========================================
    # 네비게이션 및 UI 관리 메서드
    # ==========================================
    def setup_ui_layout(self):
        """전체 UI 레이아웃 설정 (네비게이션 바, 사이드바, 컨테이너)"""
        # 최상단 네비게이션 바
        self.navigation_bar = NavigationBar(self, self)
        self.navigation_bar.pack(fill="x", side="top")
        
        # 메인 콘텐츠 영역 (네비게이션 바 제외)
        content_frame = tk.Frame(self, bg=COLOR_BG)
        content_frame.pack(fill="both", expand=True, side="bottom")
        
        # 메인 컨테이너 (사이드바 토글 시 좌측에 배치)
        self.main_container = tk.Frame(content_frame, bg=COLOR_BG)
        self.main_container.pack(fill="both", expand=True, side="left")
    
    def toggle_sidebar(self, force_state=None):
        """사이드바 표시/숨김
        Args:
            force_state: None (토글), True (표시), False (숨김)
        """
        if force_state is None:
            # 토글
            state = not self.sidebar_visible
        else:
            # 강제 설정
            state = force_state
        
        if state:
            # 사이드바 표시
            parent = self.main_container.master
            if not self.sidebar_panel:
                self.sidebar_panel = SidebarPanel(parent, self, bg=COLOR_CARD)
            if not self.sidebar_visible:
                self.sidebar_panel.pack(fill="y", side="left", before=self.main_container)
            self.sidebar_visible = True
        else:
            # 사이드바 숨기기
            if self.sidebar_panel:
                self.sidebar_panel.pack_forget()
            self.sidebar_visible = False
    
    def go_back(self):
        """이전 화면으로 돌아가기"""
        if len(self.navigation_stack) > 0:
            prev_screen = self.navigation_stack.pop()
            prev_screen()
        else:
            self.show_main_menu()
    
    def push_navigation(self, screen_func):
        """현재 화면을 스택에 저장"""
        self.navigation_stack.append(screen_func)

    def ensure_config_defaults(self):
        """prompts.json에 필요한 키 구조만 보장합니다."""
        self.config_data = merge_prompt_config_shape(getattr(self, "config_data", None))
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"prompts.json 저장 실패: {e}")

    def get_wrong_feedback(self, q_data, selected_key):
        """선택한 오답에 대한 피드백을 JSON 구조에 맞춰 반환합니다."""
        feedbacks = q_data.get("wrong_feedbacks", [])
        correct_key = q_data.get("key")
        
        # selected_key는 1-indexed 숫자
        if selected_key == correct_key:
            return "정답입니다!"
        
        # wrong_feedbacks가 리스트인 경우 (새 규격)
        if isinstance(feedbacks, list):
            # correct_key가 제외된 순서대로 정렬되어 있음
            # 예: key=3 이면 wrong_feedbacks는 1, 2, 4, 5 오답용 피드백을 가짐
            # 1 -> index 0, 2 -> index 1, 4 -> index 2, 5 -> index 3
            if selected_key < correct_key:
                idx = selected_key - 1
            else:
                idx = selected_key - 2
                
            if 0 <= idx < len(feedbacks):
                return feedbacks[idx]
            else:
                return "오답입니다."
        
        # wrong_feedbacks가 사전인 경우 (기존 규격 대비 예외 처리)
        elif isinstance(feedbacks, dict):
            return feedbacks.get(str(selected_key), "오답입니다.")
            
        return "오답입니다."

    def generate_ai_quizzes_async(self, mode, concept_filename=None, q_type=None):
        # Vertex 서비스 계정 JSON 확인
        if not VERTEX_SERVICE_ACCOUNT_JSON.strip():
            self.show_generation_error_screen(
                mode,
                concept_filename,
                q_type,
                "VERTEX_SERVICE_ACCOUNT_JSON에 Vertex AI 서비스 계정 JSON 키를 붙여넣어 주세요."
            )
            return

        # 로딩 오버레이
        overlay = tk.Frame(self.main_container, bg=COLOR_BG)
        overlay.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        lbl_title = tk.Label(overlay, text="AI 문제 생성 중", font=("Malgun Gothic", 16, "bold"), fg=COLOR_DARK, bg=COLOR_BG)
        lbl_title.pack(pady=(150, 10))

        lbl_status = tk.Label(overlay, text="Vertex AI를 통해 맞춤형 퀴즈를 생성하고 있습니다.\n잠시만 기다려 주세요...", 
                              font=("Malgun Gothic", 11), fg=COLOR_TEXT_MUTED, bg=COLOR_BG, justify="center")
        lbl_status.pack(pady=10)

        dots_label = tk.Label(overlay, text=". . .", font=("Malgun Gothic", 24, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        dots_label.pack(pady=20)
        
        def animate_dots():
            if overlay.winfo_exists():
                current = dots_label.cget("text")
                if current == ". . .":
                    dots_label.config(text=".")
                elif current == ".":
                    dots_label.config(text=". .")
                elif current == ". .":
                    dots_label.config(text=". . .")
                self.after(500, animate_dots)
        
        animate_dots()
        
        def api_worker():
            try:
                system_p, user_p = self.build_generation_prompt(mode, concept_filename, q_type)
                problem_model = PROBLEM_GEMINI_MODEL.strip() or GEMINI_MODEL
                raw_response = call_generative_api_raw(user_p, system_p, model_name=problem_model)
                cleaned_response = clean_json_string(raw_response)
                
                response_json = json.loads(cleaned_response)
                quiz_set = response_json.get("quiz_set", [])
                
                if not quiz_set:
                    raise ValueError("생성된 퀴즈 셋이 비어 있습니다.")
                
                # 가공 처리
                quiz_set = self.normalize_ai_quiz_set(quiz_set, mode, q_type, concept_filename)
                if mode == "concept":
                    quiz_set = [q for q in quiz_set if q.get("type") == "objective"][:5]
                elif mode == "learning":
                    quiz_set = [q for q in quiz_set if q.get("type") == q_type][:10]
                elif mode == "test":
                    objectives = [q for q in quiz_set if q.get("type") == "objective"][:5]
                    subjectives = [q for q in quiz_set if q.get("type") == "subjective"][:5]
                    quiz_set = objectives + subjectives
                
                # 순차적 ID 부여 및 메타 정보 기록
                for idx, q in enumerate(quiz_set):
                    q["id"] = idx + 1
                    if mode == "concept":
                        q["concept"] = concept_filename
                
                self.after(0, lambda quizzes=quiz_set: success_callback(quizzes))
                
            except Exception as err:
                self.after(0, lambda err=err: error_callback(err))
        
        def success_callback(quizzes):
            if not overlay.winfo_exists():
                return
            overlay.destroy()
            
            self.current_session_quizzes = quizzes
            
            if mode == "concept":
                self.show_concept_quiz_question()
            elif mode == "learning":
                self.show_learning_question()
            elif mode == "test":
                self.test_temp_answers = {}
                self.test_answer_widgets = {}
                for q in self.current_session_quizzes:
                    self.test_temp_answers[q["id"]] = {
                        "objective_ans": None,
                        "subjective_code": "",
                        "saved": False
                    }
                self.show_test_paper()
                
        def error_callback(err):
            if not overlay.winfo_exists():
                return
            overlay.destroy()
            self.show_generation_error_screen(mode, concept_filename, q_type, err)
            return
            
            messagebox.showerror(
                "문제 생성 실패", 
                f"AI 문제를 생성하는 도중 오류가 발생했습니다.\\n\\n오류 내용:\\n{err}"
            )
            if mode == "concept":
                self.show_concept_selection()
            elif mode == "learning":
                self.show_learning_selection()
            else:
                self.show_main_menu()
                
        threading.Thread(target=api_worker, daemon=True).start()

    def show_generation_error_screen(self, mode, concept_filename=None, q_type=None, err=None):
        """AI 문제 생성 실패 시 재시도/메뉴 이동 버튼을 제공합니다."""
        self.init_container()

        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(
            header,
            text="AI 문제 생성 실패",
            font=("Malgun Gothic", 16, "bold"),
            fg="#ffffff",
            bg=COLOR_DARK
        ).pack(pady=8)

        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=45, pady=35)

        card = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card.pack(fill="both", expand=True)

        pad = tk.Frame(card, bg=COLOR_CARD, padx=28, pady=26)
        pad.pack(fill="both", expand=True)

        tk.Label(
            pad,
            text="AI 응답을 받지 못했거나 JSON 형식이 맞지 않습니다.",
            font=("Malgun Gothic", 13, "bold"),
            fg=COLOR_ERROR,
            bg=COLOR_CARD
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            pad,
            text="다시 시도하면 같은 모드와 범위로 문제 생성을 재요청합니다. API 키, 네트워크, prompts.json 설정도 함께 확인하세요.",
            font=("Malgun Gothic", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD,
            justify="left",
            wraplength=760
        ).pack(anchor="w", pady=(0, 15))

        err_box = tk.Text(
            pad,
            height=8,
            font=("Consolas", 9),
            bg="#1a202c",
            fg="#f7fafc",
            padx=10,
            pady=8,
            relief="flat",
            wrap="word"
        )
        err_box.pack(fill="both", expand=True, pady=(0, 18))
        err_box.insert(tk.END, str(err) if err else "오류 내용이 없습니다.")
        err_box.config(state="disabled")

        btn_frame = tk.Frame(pad, bg=COLOR_CARD)
        btn_frame.pack(fill="x")

        create_flat_button(
            btn_frame,
            "메인 메뉴로",
            COLOR_DARK,
            "#ffffff",
            "#4a5568",
            self.show_main_menu,
            font=("Malgun Gothic", 10, "bold")
        ).pack(side="left", ipadx=18, ipady=5)

        create_flat_button(
            btn_frame,
            "다시 시도",
            COLOR_PRIMARY,
            "#ffffff",
            COLOR_PRIMARY_HOVER,
            lambda: self.generate_ai_quizzes_async(mode, concept_filename, q_type),
            font=("Malgun Gothic", 10, "bold")
        ).pack(side="right", ipadx=18, ipady=5)

    def get_ai_feedback(self, question, user_code, stdout, is_correct):
        """AI를 이용해 제출 답안에 대한 피드백을 실시간 생성합니다."""
        if not VERTEX_SERVICE_ACCOUNT_JSON.strip():
            if is_correct:
                return "정답입니다. 코드 실행 결과가 정상적으로 수행되었습니다."
            else:
                return f"에러가 발생했습니다: {stdout}"
                
        system_prompt = self.config_data.get("config", {}).get("system_prompt", "")
        feedback_prompt = self.config_data.get("config", {}).get("feedback_prompt", "")
        
        prompt = f"""
{feedback_prompt}

[문제 정보]
질문: {question}

[사용자 답안 정보]
제출한 소스코드:
{user_code}

실행 결과(stdout/stderr):
{stdout}

정답 여부: {"정답" if is_correct else "오답"}
"""
        try:
            feedback = call_generative_api_raw(prompt, system_prompt)
            return feedback.strip()
        except Exception as e:
            print(f"피드백 생성 실패: {e}")
            if is_correct:
                return "정답입니다! 코드가 문법 에러 없이 정상적으로 수행되었습니다."
            else:
                return f"실행 에러가 발생했습니다. {stdout}"

    def build_generation_prompt(self, mode, concept_filename=None, q_type=None):
        """API 문제 생성 프롬프트를 현재 범위와 EX 모드에 맞게 구성합니다."""
        config = self.config_data.get("config", {})
        system_prompt = config.get("system_prompt", "")
        schema_prompt = config.get("schema_prompt", "")
        mode_notes = config.get("mode_notes", {})
        mode_prompts = config.get("mode_prompts", {})
        normal_type_prompts = config.get("type_prompts", {})
        ex_type_prompts = config.get("ex_type_prompts", {})
        request_prompts = config.get("request_prompts", {})
        type_prompts = ex_type_prompts if self.ex_mode else normal_type_prompts

        mode_note = mode_notes.get("ex" if self.ex_mode else "python", "")
        full_system_prompt = "\n".join(part for part in (system_prompt, mode_note, schema_prompt) if part)

        if mode == "concept":
            concept_text = load_single_concept_content(concept_filename)
            request_text = request_prompts.get("concept", "")
            user_prompt = (
                f"{mode_prompts.get('concept', '')}\n\n"
                f"[문제 유형]\n{type_prompts.get('objective', '')}\n\n"
                f"[출제 범위: 선택한 개념서]\n{concept_text}\n\n"
                f"{request_text}"
            )
        elif mode == "learning":
            concepts_text = load_all_concepts_content(self.get_active_concept_files())
            type_desc = "객관식(objective)" if q_type == "objective" else "주관식(subjective)"
            mode_prompt = mode_prompts.get("learning", "").replace("{type_desc}", type_desc)
            request_text = request_prompts.get("learning", "").format(q_type=q_type, type_desc=type_desc)
            user_prompt = (
                f"{mode_prompt}\n\n"
                f"[문제 유형]\n{type_prompts.get(q_type, '')}\n\n"
                f"[출제 범위: {self.get_active_scope_label()}]\n{concepts_text}\n\n"
                f"{request_text}"
            )
        else:
            concepts_text = load_all_concepts_content(self.get_active_concept_files())
            request_text = request_prompts.get("test", "")
            user_prompt = (
                f"{mode_prompts.get('test', '')}\n\n"
                f"[객관식 형식]\n{type_prompts.get('objective', '')}\n\n"
                f"[주관식 형식]\n{type_prompts.get('subjective', '')}\n\n"
                f"[출제 범위: {self.get_active_scope_label()}]\n{concepts_text}\n\n"
                f"{request_text}"
            )
        return full_system_prompt, user_prompt

    def normalize_ai_quiz_set(self, quiz_set, mode, q_type=None, concept_filename=None):
        """AI 응답을 모드별 요구 개수와 순서에 맞게 검증/정리합니다."""
        if not isinstance(quiz_set, list):
            raise ValueError("quiz_set은 배열이어야 합니다.")

        def valid_objective(q):
            return (
                isinstance(q, dict)
                and q.get("type") == "objective"
                and isinstance(q.get("question"), str)
                and isinstance(q.get("options"), list)
                and len(q.get("options", [])) == 5
                and isinstance(q.get("key"), int)
                and 1 <= q.get("key") <= 5
            )

        def valid_subjective(q):
            return (
                isinstance(q, dict)
                and q.get("type") == "subjective"
                and isinstance(q.get("question"), str)
            )

        objectives = [q for q in quiz_set if valid_objective(q)]
        subjectives = [q for q in quiz_set if valid_subjective(q)]

        if mode == "concept":
            selected = objectives[:5]
            if len(selected) < 5:
                raise ValueError("개념 모드는 유효한 객관식 5문제가 필요합니다.")
        elif mode == "learning":
            selected = (objectives if q_type == "objective" else subjectives)[:10]
            if len(selected) < 10:
                raise ValueError("학습 모드는 선택한 유형의 유효한 문제 10개가 필요합니다.")
        else:
            selected = objectives[:5] + subjectives[:5]
            if len(objectives) < 5 or len(subjectives) < 5:
                raise ValueError("시험 모드는 객관식 5문제와 주관식 5문제가 필요합니다.")

        for idx, q in enumerate(selected, start=1):
            q["id"] = idx
            q.setdefault("hint", "")
            if q["type"] == "objective":
                q.setdefault("wrong_feedbacks", [])
            else:
                q.setdefault("evaluation_criteria", "")
            if mode == "concept":
                q["concept"] = concept_filename
        return selected

    def evaluate_subjective_answer(self, question, evaluation_criteria, user_code, stdout, local_success):
        """로컬 실행 결과와 AI 판정을 합쳐 주관식 정답 여부와 피드백을 반환합니다."""
        if not VERTEX_SERVICE_ACCOUNT_JSON.strip():
            return {
                "is_correct": bool(local_success),
                "feedback": "API 키가 없어 로컬 실행 결과만 기준으로 판정했습니다."
            }

        config = self.config_data.get("config", {})
        system_prompt = config.get("system_prompt", "")
        if self.ex_mode:
            feedback_prompt = config.get("ex_feedback_prompt", "")
        else:
            feedback_prompt = config.get("feedback_prompt", "")
        prompt = f"""
{feedback_prompt}

[문제]
{question}

[평가 기준]
{evaluation_criteria}

[사용자 코드]
{user_code}

[로컬 실행 성공 여부]
{local_success}

[로컬 실행 결과 stdout/stderr]
{stdout}
"""
        try:
            raw = call_generative_api_raw(prompt, system_prompt)
            data = json.loads(clean_json_string(raw))
            return {
                "is_correct": bool(data.get("is_correct", False)) and bool(local_success),
                "feedback": str(data.get("feedback", "")).strip() or "AI 피드백이 비어 있습니다."
            }
        except Exception as e:
            return {
                "is_correct": bool(local_success),
                "feedback": f"AI 판정 호출에 실패해 로컬 실행 결과만 적용했습니다. 오류: {e}"
            }

    def init_container(self):
        """메인 컨테이너의 모든 자식 요소를 제거합니다."""
        for child in self.main_container.winfo_children():
            child.destroy()

    # ==========================================
    # 4. 화면 구현 (Views)
    # ==========================================
    
    def show_main_menu(self):
        """메인 메뉴 화면 (4개의 모드 카드 제공)"""
        self.init_container()
        self.navigation_stack.clear()
        
        # 네비게이션 바 정보 업데이트
        self.navigation_bar.update_info("홈 화면")
        
        # 타이틀 영역
        header_frame = tk.Frame(self.main_container, bg="#f9fafb")
        header_frame.pack(fill="x", padx=0, pady=0)
        
        title_pad = tk.Frame(header_frame, bg="#f9fafb", padx=30, pady=25)
        title_pad.pack(fill="x")
        
        lbl_title = tk.Label(title_pad, text="🐍 Python Learning Program", font=("Malgun Gothic", 24, "bold"), fg=COLOR_DARK, bg="#f9fafb")
        lbl_title.pack(anchor="w")
        
        lbl_subtitle = tk.Label(title_pad, text="AI 튜터 기반의 개인화된 파이썬 학습 환경", font=("Malgun Gothic", 12), fg=COLOR_TEXT_MUTED, bg="#f9fafb")
        lbl_subtitle.pack(anchor="w", pady=(5, 0))
        
        # 도구 버튼 (EX 모드, 개념서 관리)
        tools_frame = tk.Frame(title_pad, bg="#f9fafb")
        tools_frame.pack(fill="x", pady=(15, 0))
        
        ex_text = "🟢 EX 모드: ON" if self.ex_mode else "⚪ EX 모드: OFF"
        create_flat_button(
            tools_frame,
            ex_text,
            COLOR_BUTTON_BG,
            COLOR_DARK,
            "#e5e7eb",
            self.toggle_ex_mode,
            font=("Malgun Gothic", 9, "bold")
        ).pack(side="left", ipadx=10, ipady=4, padx=3)
        
        create_flat_button(
            tools_frame,
            "⚙️ 개념서/범위 관리",
            COLOR_BUTTON_BG,
            COLOR_DARK,
            "#e5e7eb",
            self.show_concept_manager,
            font=("Malgun Gothic", 9, "bold")
        ).pack(side="left", ipadx=10, ipady=4, padx=3)
        
        # 카드 프레임 레이아웃
        cards_container = tk.Frame(self.main_container, bg=COLOR_BG)
        cards_container.pack(expand=True, fill="both", padx=40, pady=40)
        
        # 2x2 그리드 설정
        cards_container.grid_columnconfigure(0, weight=1)
        cards_container.grid_columnconfigure(1, weight=1)
        cards_container.grid_rowconfigure(0, weight=1)
        cards_container.grid_rowconfigure(1, weight=1)
        
        # 각 카드 데이터
        modes = [
            {
                "title": "📚 개념 모드",
                "desc": "단원별 개념을 읽고\n이해도를 검증하는 객관식 5문제 풀이",
                "color": COLOR_PRIMARY,
                "hover": COLOR_PRIMARY_HOVER,
                "cmd": self.show_concept_selection
            },
            {
                "title": "⚡ 학습 모드",
                "desc": "객관식 또는 주관식을 선택하여\n1문제씩 즉시 피드백을 받으며 학습",
                "color": "#10b981",
                "hover": "#059669",
                "cmd": self.show_learning_selection
            },
            {
                "title": "📝 시험 모드",
                "desc": "10문제를 시험지로 풀고\n답안 제출 후 종합 평가 받기",
                "color": "#8b5cf6",
                "hover": "#7c3aed",
                "cmd": lambda: self.start_test_mode()
            },
            {
                "title": "🗂️ 기록실",
                "desc": "이전 풀이 기록과 채점 결과\n확인 및 재도전하기",
                "color": "#f59e0b",
                "hover": "#d97706",
                "cmd": self.show_library
            }
        ]
        
        for idx, mode in enumerate(modes):
            row = idx // 2
            col = idx % 2
            
            # 카드 프레임 (박스 섀도우 효과)
            card = tk.Frame(cards_container, bg=COLOR_CARD)
            card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
            
            # 왼쪽 컬러 바
            color_bar = tk.Frame(card, bg=mode["color"], width=5)
            color_bar.pack(side="left", fill="y", padx=0, pady=0)
            
            # 우측 콘텐츠
            content = tk.Frame(card, bg=COLOR_CARD, padx=20, pady=20)
            content.pack(fill="both", expand=True, side="right")
            
            # 타이틀
            tk.Label(content, text=mode["title"], font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w")
            
            # 설명
            tk.Label(content, text=mode["desc"], font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left").pack(anchor="w", pady=(6, 12))
            
            # 버튼
            btn_frame = tk.Frame(content, bg=COLOR_CARD)
            btn_frame.pack(fill="x")
            
            create_flat_button(
                btn_frame,
                "입장 →",
                mode["color"],
                "#ffffff",
                mode["hover"],
                mode["cmd"],
                font=("Malgun Gothic", 10, "bold")
            ).pack(ipadx=12, ipady=5)

    # ------------------------------------------
    # 4-1. 개념 모드 관련 화면
    # ------------------------------------------
    
    def toggle_ex_mode(self):
        self.ex_mode = not self.ex_mode
        self.save_app_state()
        self.show_main_menu()

    def show_concept_manager(self):
        self.init_container()

        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="개념서/출제 범위 관리", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack(pady=8)

        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=36, pady=24)

        info = tk.Label(
            body,
            text="체크한 개념서는 학습 모드와 시험 모드의 출제 범위로 저장됩니다. 선택이 없으면 전체 개념서를 사용합니다.",
            font=("Malgun Gothic", 10),
            fg=COLOR_DARK,
            bg=COLOR_BG,
            justify="left"
        )
        info.pack(anchor="w", pady=(0, 12))

        list_frame = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid")
        list_frame.pack(fill="both", expand=True)

        inner = tk.Frame(list_frame, bg=COLOR_CARD, padx=18, pady=14)
        inner.pack(fill="both", expand=True)

        concept_files = list_concept_files()
        selected_set = set(self.selected_concepts)
        vars_by_file = {}

        if not concept_files:
            tk.Label(inner, text="아직 개념서가 없습니다. 아래 버튼으로 .txt 파일을 추가하세요.", font=("Malgun Gothic", 11), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD).pack(anchor="w", pady=12)
        else:
            for filename in concept_files:
                display = filename.replace(".txt", "").replace("_", " ")
                var = tk.BooleanVar(value=(filename in selected_set))
                vars_by_file[filename] = var
                cb = tk.Checkbutton(
                    inner,
                    text=display,
                    variable=var,
                    font=("Malgun Gothic", 11),
                    bg=COLOR_CARD,
                    activebackground=COLOR_CARD,
                    fg=COLOR_DARK,
                    selectcolor=COLOR_CARD,
                    anchor="w"
                )
                cb.pack(fill="x", anchor="w", pady=3)

        btn_row = tk.Frame(body, bg=COLOR_BG)
        btn_row.pack(fill="x", pady=(14, 0))

        def save_scope():
            self.selected_concepts = [name for name, var in vars_by_file.items() if var.get()]
            self.save_app_state()
            messagebox.showinfo("저장 완료", self.get_active_scope_label())

        def import_concept_file():
            path = filedialog.askopenfilename(
                title="추가할 개념서 선택",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if not path:
                return
            dest = os.path.join(CONCEPTS_DIR, os.path.basename(path))
            if os.path.exists(dest):
                base, ext = os.path.splitext(os.path.basename(path))
                dest = os.path.join(CONCEPTS_DIR, f"{base}_{datetime.datetime.now().strftime('%H%M%S')}{ext}")
            shutil.copyfile(path, dest)
            self.show_concept_manager()

        def create_concept_file():
            title = simpledialog.askstring("새 개념서", "개념서 제목을 입력하세요.")
            if not title:
                return
            content = simpledialog.askstring("새 개념서", "개념 내용을 입력하세요.")
            if content is None:
                return
            filename = safe_concept_filename(title)
            filepath = os.path.join(CONCEPTS_DIR, filename)
            if os.path.exists(filepath):
                filename = safe_concept_filename(f"{title}_{datetime.datetime.now().strftime('%H%M%S')}")
                filepath = os.path.join(CONCEPTS_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self.show_concept_manager()

        def delete_selected_files():
            targets = [name for name, var in vars_by_file.items() if var.get()]
            if not targets:
                messagebox.showwarning("주의", "삭제할 개념서를 체크하세요.")
                return
            if not messagebox.askyesno("삭제 확인", f"선택한 개념서 {len(targets)}개를 삭제할까요?"):
                return
            for name in targets:
                path = os.path.join(CONCEPTS_DIR, name)
                if os.path.exists(path):
                    os.remove(path)
            self.selected_concepts = [name for name in self.selected_concepts if name not in targets]
            self.save_app_state()
            self.show_concept_manager()

        def edit_selected_file():
            targets = [name for name, var in vars_by_file.items() if var.get()]
            if len(targets) != 1:
                messagebox.showwarning("주의", "수정할 개념서 하나만 체크하세요.")
                return
            self.show_concept_editor(targets[0])

        create_flat_button(btn_row, "범위 저장", COLOR_SUCCESS, "#ffffff", "#38a169", save_scope).pack(side="left", ipadx=14, ipady=4)
        create_flat_button(btn_row, "txt 파일 추가", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, import_concept_file).pack(side="left", padx=(8, 0), ipadx=14, ipady=4)
        create_flat_button(btn_row, "새 개념서 작성", "#319795", "#ffffff", "#2c7a7b", create_concept_file).pack(side="left", padx=(8, 0), ipadx=14, ipady=4)
        create_flat_button(btn_row, "선택 수정", "#805ad5", "#ffffff", "#6b46c1", edit_selected_file).pack(side="left", padx=(8, 0), ipadx=14, ipady=4)
        create_flat_button(btn_row, "선택 삭제", COLOR_ERROR, "#ffffff", "#c53030", delete_selected_files).pack(side="left", padx=(8, 0), ipadx=14, ipady=4)
        create_flat_button(btn_row, "메인 메뉴로", COLOR_DARK, "#ffffff", "#4a5568", self.show_main_menu).pack(side="right", ipadx=14, ipady=4)

    def show_concept_editor(self, filename):
        """개념서 제목과 본문을 수정하는 화면"""
        self.init_container()
        
        old_path = os.path.join(CONCEPTS_DIR, filename)
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception as e:
            messagebox.showerror("오류", f"개념서를 읽을 수 없습니다.\n{e}")
            self.show_concept_manager()
            return
        
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="개념서 수정", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack(pady=8)
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=36, pady=24)
        
        card = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", padx=22, pady=18)
        card.pack(fill="both", expand=True)
        
        tk.Label(card, text="개념서 제목", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w")
        title_var = tk.StringVar(value=filename.replace(".txt", "").replace("_", " "))
        title_entry = tk.Entry(card, textvariable=title_var, font=("Malgun Gothic", 11), relief="solid", bd=1)
        title_entry.pack(fill="x", pady=(6, 14))
        
        tk.Label(card, text="개념 내용", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w")
        editor_frame = tk.Frame(card, bg=COLOR_CARD)
        editor_frame.pack(fill="both", expand=True, pady=(6, 14))
        
        scrollbar = ttk.Scrollbar(editor_frame, orient="vertical")
        text_area = tk.Text(editor_frame, wrap="word", font=("Malgun Gothic", 11), bg="#ffffff", fg=COLOR_DARK,
                            relief="solid", bd=1, padx=10, pady=10, yscrollcommand=scrollbar.set)
        scrollbar.config(command=text_area.yview)
        text_area.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text_area.insert("1.0", old_content)
        
        btn_row = tk.Frame(card, bg=COLOR_CARD)
        btn_row.pack(fill="x")
        
        def save_changes():
            new_title = title_var.get().strip()
            if not new_title:
                messagebox.showwarning("주의", "개념서 제목을 입력하세요.")
                return
            
            new_filename = safe_concept_filename(new_title)
            new_path = os.path.join(CONCEPTS_DIR, new_filename)
            if new_filename != filename and os.path.exists(new_path):
                messagebox.showwarning("주의", "같은 이름의 개념서가 이미 있습니다. 다른 제목을 입력하세요.")
                return
            
            content = text_area.get("1.0", tk.END).rstrip()
            try:
                with open(new_path, "w", encoding="utf-8") as f:
                    f.write(content)
                if new_filename != filename and os.path.exists(old_path):
                    os.remove(old_path)
                    self.selected_concepts = [new_filename if name == filename else name for name in self.selected_concepts]
                    self.save_app_state()
                messagebox.showinfo("저장 완료", "개념서가 수정되었습니다.")
                self.show_concept_manager()
            except Exception as e:
                messagebox.showerror("오류", f"개념서를 저장할 수 없습니다.\n{e}")
        
        create_flat_button(btn_row, "저장", COLOR_SUCCESS, "#ffffff", "#38a169", save_changes).pack(side="right", ipadx=18, ipady=4)
        create_flat_button(btn_row, "취소", COLOR_DARK, "#ffffff", "#4a5568", self.show_concept_manager).pack(side="right", padx=(0, 8), ipadx=18, ipady=4)

    def show_concept_selection(self):
        """개념 모드: 개념지 목록 선택 화면"""
        self.init_container()
        self.navigation_bar.update_info("개념 모드 - 단원 선택")
        
        # 헤더
        header = tk.Frame(self.main_container, bg="#f9fafb")
        header.pack(fill="x", padx=0, pady=0)
        
        header_content = tk.Frame(header, bg="#f9fafb", padx=30, pady=20)
        header_content.pack(fill="x")
        
        tk.Label(header_content, text="📚 개념 모드", font=("Malgun Gothic", 18, "bold"), 
                fg=COLOR_DARK, bg="#f9fafb").pack(anchor="w")
        tk.Label(header_content, text="공부하고 싶은 단원을 선택하세요", font=("Malgun Gothic", 11), 
                fg=COLOR_TEXT_MUTED, bg="#f9fafb").pack(anchor="w", pady=(3, 0))
        
        # 구분선
        sep = tk.Frame(header, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x")
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=30)
        
        # 개념 파일 목록 확인
        files_frame = tk.Frame(body, bg=COLOR_BG)
        files_frame.pack(fill="both", expand=True)
        
        try:
            concept_files = [f for f in os.listdir(CONCEPTS_DIR) if f.endswith(".txt")]
            concept_files.sort()
        except Exception as e:
            concept_files = []
            messagebox.showerror("오류", f"concepts 디렉토리를 읽을 수 없습니다.\n{e}")
            
        if not concept_files:
            tk.Label(files_frame, text="생성된 개념 파일이 없습니다. concepts 폴더를 확인하세요.", 
                     font=("Malgun Gothic", 12), fg=COLOR_ERROR, bg=COLOR_BG).pack(pady=40)
        else:
            for idx, file in enumerate(concept_files):
                # 카드 형태로 렌더링
                file_card = tk.Frame(files_frame, bg=COLOR_CARD, bd=1, relief="ridge", pady=15, padx=20)
                file_card.pack(fill="x", pady=6)
                
                # 파일명에서 단원명 추출
                display_name = file.replace(".txt", "").replace("_", " ")
                
                lbl_name = tk.Label(file_card, text=f"📖 {display_name}", font=("Malgun Gothic", 12, "bold"), fg=COLOR_DARK, bg=COLOR_CARD)
                lbl_name.pack(side="left")
                
                # 학습 시작 버튼
                btn_start = create_flat_button(file_card, "개념 읽기 ➔", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                               lambda f=file: self.show_concept_content(f))
                btn_start.pack(side="right", ipadx=15, ipady=3)
                
        # 뒤로 가기
        btn_back = create_flat_button(body, "⬅ 메인 메뉴로", COLOR_DARK, "#ffffff", "#4a5568", self.show_main_menu)
        btn_back.pack(pady=20, ipadx=20, ipady=5)

    def show_concept_content(self, filename):
        """개념지 텍스트 뷰어 화면"""
        self.init_container()
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        
        display_name = filename.replace(".txt", "").replace("_", " ")
        tk.Label(header, text=f"📖 개념 학습: {display_name}", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 본문 영역 (텍스트 스크롤 가능하게 구성)
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=20)
        
        # 스크롤 텍스트 위젯
        text_frame = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        text_frame.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")
        
        txt_widget = tk.Text(text_frame, wrap="word", font=("Malgun Gothic", 11), bg=COLOR_CARD, fg=COLOR_DARK,
                             padx=20, pady=20, spacing1=6, spacing2=4, yscrollcommand=scrollbar.set, relief="flat")
        txt_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=txt_widget.yview)
        
        # 파일 읽어서 텍스트 입력
        filepath = os.path.join(CONCEPTS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            txt_widget.insert(tk.END, content)
        except Exception as e:
            txt_widget.insert(tk.END, f"개념 파일을 읽는 도중 오류가 발생했습니다: {e}")
            
        txt_widget.config(state="disabled") # 읽기 전용
        
        # 하단 하위 내비게이션
        footer = tk.Frame(body, bg=COLOR_BG)
        footer.pack(fill="x", pady=(15, 0))
        
        btn_back = create_flat_button(footer, "⬅ 목록으로", COLOR_DARK, "#ffffff", "#4a5568", self.show_concept_selection)
        btn_back.pack(side="left", ipadx=15, ipady=5)

        btn_home = create_flat_button(footer, "메인 메뉴로", "#4a5568", "#ffffff", COLOR_DARK, self.show_main_menu)
        btn_home.pack(side="left", padx=(10, 0), ipadx=15, ipady=5)
        
        btn_start_quiz = create_flat_button(footer, "개념 검증 문제 풀기 ➔", COLOR_SUCCESS, "#ffffff", "#38a169", 
                                            lambda: self.start_concept_quiz_session(filename))
        btn_start_quiz.pack(side="right", ipadx=20, ipady=5)

    def start_concept_quiz_session(self, filename):
        """개념 모드 퀴즈 세션 시작"""
        self.current_mode = "concept"
        self.current_q_index = 0
        self.session_results = []
        self.generate_ai_quizzes_async(mode="concept", concept_filename=filename, q_type="objective")

    def show_concept_quiz_question(self):
        """개념 모드: 문제 1개씩 렌더링"""
        self.init_container()
        
        if self.current_q_index >= len(self.current_session_quizzes):
            self.show_session_end()
            return
            
        q_data = self.current_session_quizzes[self.current_q_index]
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text=f"📚 개념 검증 테스트 ({self.current_q_index + 1} / {len(self.current_session_quizzes)})", 
                 font=("Malgun Gothic", 15, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 본문 카드
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=25)
        
        card = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=10)
        
        content_frame = tk.Frame(card, bg=COLOR_CARD, padx=30, pady=25)
        content_frame.pack(fill="both", expand=True)
        
        # 문제 출력
        question_box = create_scrollable_question_box(
            content_frame,
            f"Q. {q_data['question']}",
            font=("Malgun Gothic", 13, "bold"),
            max_height=6,
            width_chars=68
        )
        question_box.pack(fill="x", pady=(0, 20))
        
        # 피드백용 프레임 및 라벨 (처음엔 숨김)
        fb_frame = tk.Frame(content_frame, bg=COLOR_CARD)
        fb_lbl = tk.Label(fb_frame, text="", font=("Malgun Gothic", 11), justify="left", bg=COLOR_CARD, wraplength=700)
        fb_lbl.pack(anchor="w", pady=10)
        
        # 객관식 선지 렌더링
        options = q_data.get("options", [])
        correct_key = q_data.get("key")
        
        btn_refs = {}
        
        def on_select(selected_num):
            # 중복 클릭 방지 (비활성화)
            for btn in btn_refs.values():
                btn.config(state="disabled")
                
            is_correct = (selected_num == correct_key)
            fb_frame.pack(fill="x", pady=15)
            
            if is_correct:
                btn_refs[selected_num].config(bg=COLOR_SUCCESS, fg="white")
                fb_lbl.config(text="✓ 정답입니다!", fg=COLOR_SUCCESS, font=("Malgun Gothic", 11, "bold"))
                applied_feedback = "정답"
            else:
                btn_refs[selected_num].config(bg=COLOR_ERROR, fg="white")
                btn_refs[correct_key].config(bg=COLOR_SUCCESS, fg="white") # 정답 표시
                wrong_fb = self.get_wrong_feedback(q_data, selected_num)
                fb_lbl.config(text=f"✗ 오답입니다.\n피드백: {wrong_fb}", fg=COLOR_ERROR, font=("Malgun Gothic", 11))
                applied_feedback = wrong_fb
                
            # 결과 임시 기록
            self.session_results.append({
                "question": q_data.get("question"),
                "type": "objective",
                "user_answer": selected_num,
                "is_correct": is_correct,
                "applied_feedback": applied_feedback
            })
            
            # 다음 버튼 노출
            btn_next.config(state="normal")
            
        for i, opt_text in enumerate(options):
            num = i + 1
            btn = tk.Button(content_frame, text=f"{num}. {opt_text}", font=("Malgun Gothic", 11),
                            bg="#ffffff", activebackground=COLOR_BG, activeforeground=COLOR_DARK,
                            relief="ridge", bd=1, anchor="w", padx=15, pady=8, cursor="hand2",
                            command=lambda n=num: on_select(n))
            btn.pack(fill="x", pady=5)
            btn_refs[num] = btn
            
        # 하단 조작계 (힌트, 다음 문제)
        footer = tk.Frame(content_frame, bg=COLOR_CARD)
        footer.pack(fill="x", side="bottom", pady=(20, 0))
        
        hint_txt = q_data.get("hint", "제공된 힌트가 없습니다.")
        btn_hint = create_flat_button(footer, "💡 힌트 보기", "#e2e8f0", COLOR_DARK, "#cbd5e0", 
                                      lambda: messagebox.showinfo("힌트", hint_txt), font=("Malgun Gothic", 10))
        btn_hint.pack(side="left", ipadx=12, ipady=4)
        
        btn_next = create_flat_button(footer, "다음 문제 ➔", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                      self.next_concept_question, font=("Malgun Gothic", 10, "bold"))
        btn_next.pack(side="right", ipadx=15, ipady=4)
        btn_next.config(state="disabled") # 먼저 정답 제출해야 넘어갈 수 있음

    def next_concept_question(self):
        self.current_q_index += 1
        self.show_concept_quiz_question()

    # ------------------------------------------
    # 4-2. 학습 모드 관련 화면
    # ------------------------------------------
    
    def show_learning_selection(self):
        """학습 모드 진입 전 객관식 vs 주관식 유형 선택"""
        self.init_container()
        self.navigation_bar.update_info("학습 모드 - 유형 선택")
        
        header = tk.Frame(self.main_container, bg="#f9fafb")
        header.pack(fill="x", padx=0, pady=0)
        
        header_content = tk.Frame(header, bg="#f9fafb", padx=30, pady=20)
        header_content.pack(fill="x")
        
        tk.Label(header_content, text="⚡ 학습 모드", font=("Malgun Gothic", 18, "bold"), 
                fg=COLOR_DARK, bg="#f9fafb").pack(anchor="w")
        tk.Label(header_content, text="원하는 문항 형태를 선택하세요", font=("Malgun Gothic", 11), 
                fg=COLOR_TEXT_MUTED, bg="#f9fafb").pack(anchor="w", pady=(3, 0))
        
        # 구분선
        sep = tk.Frame(header, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x")
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=40)
        
        cards_frame = tk.Frame(body, bg=COLOR_BG)
        cards_frame.pack(fill="x")
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)
        
        # 객관식 카드
        card_obj = tk.Frame(cards_frame, bg=COLOR_CARD)
        card_obj.grid(row=0, column=0, padx=12, pady=10, sticky="nsew")
        
        color_bar_obj = tk.Frame(card_obj, bg=COLOR_PRIMARY, height=3)
        color_bar_obj.pack(fill="x")
        
        card_obj_pad = tk.Frame(card_obj, bg=COLOR_CARD, padx=20, pady=20)
        card_obj_pad.pack(fill="both", expand=True)
        
        tk.Label(card_obj_pad, text="📝 객관식 학습", font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 15))
        tk.Label(card_obj_pad, text="5지선다 문항으로\n1문제씩 즉시 피드백을 받으며\n학습을 진행할 수 있습니다.", 
                 font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left").pack(anchor="w", pady=(0, 25), expand=True)
        create_flat_button(card_obj_pad, "객관식 시작 →", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                           lambda: self.start_learning_session("objective")).pack(fill="x", ipady=6)
        
        # 주관식 카드
        card_sub = tk.Frame(cards_frame, bg=COLOR_CARD)
        card_sub.grid(row=0, column=1, padx=12, pady=10, sticky="nsew")
        
        color_bar_sub = tk.Frame(card_sub, bg="#10b981", height=3)
        color_bar_sub.pack(fill="x")
        
        card_sub_pad = tk.Frame(card_sub, bg=COLOR_CARD, padx=20, pady=20)
        card_sub_pad.pack(fill="both", expand=True)
        
        tk.Label(card_sub_pad, text="💻 주관식 코딩 학습", font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 15))
        tk.Label(card_sub_pad, text="직접 코드를 작성하고\n실시간으로 실행해 보며\n피드백을 받습니다.", 
                 font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left").pack(anchor="w", pady=(0, 25), expand=True)
        create_flat_button(card_sub_pad, "주관식 시작 ➔", "#319795", "#ffffff", "#2c7a7b", 
                           lambda: self.start_learning_session("subjective")).pack(fill="x", ipady=6)
        
        btn_back = create_flat_button(body, "⬅ 메인 메뉴로", COLOR_DARK, "#ffffff", "#4a5568", self.show_main_menu)
        scope_row = tk.Frame(body, bg=COLOR_BG)
        scope_row.pack(fill="x", pady=(22, 0))
        tk.Label(scope_row, text=self.get_active_scope_label(), font=("Malgun Gothic", 10, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG).pack(side="left")
        create_flat_button(scope_row, "출제 범위 관리", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, self.show_concept_manager, font=("Malgun Gothic", 9, "bold")).pack(side="right", ipadx=12, ipady=3)
        btn_back.pack(pady=40, ipadx=20, ipady=5)

    def start_learning_session(self, q_type):
        """학습 모드 세션 시작 (API 동적 생성)"""
        if not self.get_active_concept_files():
            messagebox.showwarning("개념서 없음", "학습 문제를 만들 개념서가 없습니다. 먼저 개념서를 추가하세요.")
            self.show_concept_manager()
            return
        self.toggle_sidebar(False)  # 사이드바 닫기
        self.current_mode = "learning"
        self.current_q_index = 0
        self.session_results = []
        self.generate_ai_quizzes_async(mode="learning", q_type=q_type)

    def show_learning_question(self):
        """학습 모드 문제 렌더링"""
        self.init_container()
        
        if self.current_q_index >= len(self.current_session_quizzes):
            self.show_session_end()
            return
            
        q_data = self.current_session_quizzes[self.current_q_index]
        q_type = q_data.get("type")
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        title_text = f"⚡ 학습 모드 - {'객관식' if q_type == 'objective' else '주관식'} ({self.current_q_index + 1} / {len(self.current_session_quizzes)})"
        tk.Label(header, text=title_text, font=("Malgun Gothic", 15, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 본문 카드
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=25)
        
        card = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=10)
        
        content_frame = tk.Frame(card, bg=COLOR_CARD, padx=30, pady=25)
        content_frame.pack(fill="both", expand=True)
        
        # 문제 출력
        question_box = create_scrollable_question_box(
            content_frame,
            f"Q. {q_data['question']}",
            font=("Malgun Gothic", 13, "bold"),
            max_height=6,
            width_chars=68
        )
        question_box.pack(fill="x", pady=(0, 20))
        
        # 피드백 패널 (공통)
        fb_frame = tk.Frame(content_frame, bg=COLOR_CARD)
        fb_lbl = tk.Label(fb_frame, text="", font=("Malgun Gothic", 11), justify="left", bg=COLOR_CARD, wraplength=700)
        fb_lbl.pack(anchor="w", pady=10)
        
        # 다음 버튼 조작 패널
        footer = tk.Frame(content_frame, bg=COLOR_CARD)
        footer.pack(fill="x", side="bottom", pady=(10, 0))
        
        hint_txt = q_data.get("hint", "제공된 힌트가 없습니다.")
        btn_hint = create_flat_button(footer, "💡 힌트 보기", "#e2e8f0", COLOR_DARK, "#cbd5e0", 
                                      lambda: messagebox.showinfo("힌트", hint_txt), font=("Malgun Gothic", 10))
        btn_hint.pack(side="left", ipadx=12, ipady=4)
        
        btn_next = create_flat_button(footer, "다음 문제 ➔", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                      self.next_learning_question, font=("Malgun Gothic", 10, "bold"))
        btn_next.pack(side="right", ipadx=15, ipady=4)
        btn_next.config(state="disabled")
        
        if q_type == "objective":
            # 객관식 선지 렌더링
            options = q_data.get("options", [])
            correct_key = q_data.get("key")
            btn_refs = {}
            
            def on_select(selected_num):
                for btn in btn_refs.values():
                    btn.config(state="disabled")
                is_correct = (selected_num == correct_key)
                fb_frame.pack(fill="x", pady=15)
                
                if is_correct:
                    btn_refs[selected_num].config(bg=COLOR_SUCCESS, fg="white")
                    fb_lbl.config(text="✓ 정답입니다!", fg=COLOR_SUCCESS, font=("Malgun Gothic", 11, "bold"))
                    applied_fb = "정답"
                else:
                    btn_refs[selected_num].config(bg=COLOR_ERROR, fg="white")
                    btn_refs[correct_key].config(bg=COLOR_SUCCESS, fg="white")
                    wrong_fb = self.get_wrong_feedback(q_data, selected_num)
                    fb_lbl.config(text=f"✗ 오답입니다.\n피드백: {wrong_fb}", fg=COLOR_ERROR, font=("Malgun Gothic", 11))
                    applied_fb = wrong_fb
                    
                self.session_results.append({
                    "question": q_data.get("question"),
                    "type": "objective",
                    "user_answer": selected_num,
                    "is_correct": is_correct,
                    "applied_feedback": applied_fb
                })
                btn_next.config(state="normal")
                
            for i, opt_text in enumerate(options):
                num = i + 1
                btn = tk.Button(content_frame, text=f"{num}. {opt_text}", font=("Malgun Gothic", 11),
                                bg="#ffffff", activebackground=COLOR_BG, activeforeground=COLOR_DARK,
                                relief="ridge", bd=1, anchor="w", padx=15, pady=8, cursor="hand2",
                                command=lambda n=num: on_select(n))
                btn.pack(fill="x", pady=5)
                btn_refs[num] = btn
                
        else:
            # 주관식 코드 입력 렌더링
            answer_label = "텍스트 답안을 작성하세요:" if self.ex_mode else "파이썬 코드를 작성하세요 (결과가 에러 없이 작동해야 정답 판정):"
            code_label = tk.Label(content_frame, text=answer_label, 
                                  font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=COLOR_CARD)
            code_label.pack(anchor="w", pady=(12, 6))
            
            # 에디터 프레임
            editor_frame = tk.Frame(content_frame, bg="#2d3748", bd=1, relief="solid")
            editor_frame.pack(fill="both", expand=True, pady=(0, 10))
            
            text_area = tk.Text(editor_frame, height=8, font=("Consolas", 11), bg="#2d3748", fg="#f7fafc", 
                                insertbackground="white", padx=10, pady=10, relief="flat")
            text_area.pack(fill="both", expand=True)
            
            # 기본 템플릿 코드 삽입
            text_area.insert(tk.END, "여기에 답안을 입력하세요\n" if self.ex_mode else "# 여기에 코드를 입력하세요\n")
            
            # 실행 결과 화면
            console_frame = tk.Frame(content_frame, bg="#1a202c", bd=1, relief="solid")
            console_lbl = tk.Label(console_frame, text="[실행 콘솔 출력 결과]", font=("Consolas", 10), fg="#a0aec0", bg="#1a202c", justify="left", anchor="nw")
            console_lbl.pack(fill="both", expand=True, padx=10, pady=8)
            
            def run_code():
                user_code = text_area.get("1.0", tk.END).strip()
                original_user_answer = user_code
                if not user_code or user_code in ("여기에 답안을 입력하세요", "# 여기에 코드를 입력하세요", "# Write your Python code here"):
                    messagebox.showwarning("경고", "답안을 입력하세요.")
                    return
                
                temp_file = None
                stdout_str = ""
                is_correct = False
                if self.ex_mode:
                    stdout_str = "EX 모드: 파이썬 실행 없이 텍스트 답안으로 채점합니다."
                    is_correct = True
                    console_frame.pack(fill="x", pady=(0, 10))
                    console_lbl.config(text=stdout_str, fg="#48bb78")
                else:
                    pass
                
                try:
                    with tempfile.NamedTemporaryFile("w", suffix=".txt" if self.ex_mode else ".py", encoding="utf-8", delete=False) as f:
                        if self.ex_mode:
                            f.write('"""\\n' + original_user_answer.replace('"""', '\\"\\"\\"') + '\\n"""')
                        else:
                            f.write(user_code)
                        temp_file = f.name
                    
                    # 2초 타임아웃
                    result = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=2.0)
                    
                    # 콘솔 프레임 노출
                    console_frame.pack(fill="x", pady=(0, 10))
                    
                    if result.returncode == 0:
                        is_correct = True
                        stdout_str = result.stdout.strip()
                        console_lbl.config(text=f"▶ 실행 결과 (성공):\n{stdout_str}", fg="#48bb78")
                    else:
                        is_correct = False
                        stdout_str = result.stderr.strip()
                        console_lbl.config(text=f"▶ 실행 결과 (에러):\n{stdout_str}", fg="#f56565")
                        
                except subprocess.TimeoutExpired:
                    is_correct = False
                    console_frame.pack(fill="x", pady=(0, 10))
                    stdout_str = "[Timeout] 무한 루프가 발생하여 2초 후 중단되었습니다."
                    console_lbl.config(text=f"▶ 실행 결과:\n{stdout_str}", fg="#f56565")
                except Exception as e:
                    is_correct = False
                    console_frame.pack(fill="x", pady=(0, 10))
                    stdout_str = f"시스템 에러: {e}"
                    console_lbl.config(text=f"▶ 시스템 에러:\n{stdout_str}", fg="#f56565")
                finally:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                
                # 피드백 UI 프레임 노출 및 로딩 표시
                fb_frame.pack(fill="x", pady=10)
                if is_correct:
                    fb_lbl.config(text="✓ 채점 완료. AI 튜터 피드백 생성 중...", fg=COLOR_SUCCESS, font=("Malgun Gothic", 11, "bold"))
                else:
                    fb_lbl.config(text="✗ 채점 실패. AI 튜터 피드백 생성 중...", fg=COLOR_ERROR, font=("Malgun Gothic", 11))
                
                # AI 피드백을 비동기 스레드로 가져오기
                def fetch_feedback():
                    evaluation = self.evaluate_subjective_answer(
                        q_data["question"],
                        q_data.get("evaluation_criteria", ""),
                        original_user_answer,
                        stdout_str,
                        is_correct
                    )
                    final_correct = evaluation["is_correct"]
                    feedback = evaluation["feedback"]
                    
                    def update_ui():
                        if final_correct:
                            fb_lbl.config(text=f"✓ 채점 완료: {feedback}", fg=COLOR_SUCCESS, font=("Malgun Gothic", 11, "bold"))
                        else:
                            fb_lbl.config(text=f"✗ 채점 실패: {feedback}", fg=COLOR_ERROR, font=("Malgun Gothic", 11))
                        
                        # 상태 기록 저장/업데이트
                        save_result = {
                            "question": q_data.get("question"),
                            "type": "subjective",
                            "user_code": original_user_answer,
                            "stdout": stdout_str,
                            "is_correct": final_correct,
                            "applied_feedback": feedback
                        }
                        
                        if len(self.session_results) > self.current_q_index:
                            self.session_results[self.current_q_index] = save_result
                        else:
                            # 패딩
                            while len(self.session_results) < self.current_q_index:
                                self.session_results.append({})
                            self.session_results.append(save_result)
                            
                        # 실행 성공인 경우 비활성화하고 '다음 문제' 잠금 해제
                        if final_correct:
                            text_area.config(state="disabled")
                            btn_run.config(state="disabled")
                            btn_next.config(state="normal")
                        else:
                            btn_next.config(state="normal")
                            
                    self.after(0, update_ui)
                
                threading.Thread(target=fetch_feedback, daemon=True).start()
            
            run_label = "텍스트 답안 채점하기" if self.ex_mode else "💻 코드 실행 및 채점하기"
            btn_run = create_flat_button(content_frame, run_label, "#4a5568", "#ffffff", "#2d3748", 
                                        run_code, font=("Malgun Gothic", 10, "bold"))
            btn_run.pack(anchor="e", pady=(0, 10))

    def next_learning_question(self):
        self.current_q_index += 1
        self.show_learning_question()

    # ------------------------------------------
    # 4-3. 시험 모드 관련 화면 (스크롤 카드 10문항)
    # ------------------------------------------
    
    def start_test_mode(self):
        """시험 모드 시작 (API 동적 생성)"""
        if not self.get_active_concept_files():
            messagebox.showwarning("개념서 없음", "시험 문제를 만들 개념서가 없습니다. 먼저 개념서를 추가하세요.")
            self.show_concept_manager()
            return
        self.current_mode = "test"
        self.session_results = []
        self.test_temp_answers = {}
        self.test_answer_widgets = {}
        self.test_remaining_time = 30 * 60  # 30분 = 1800초
        self.generate_ai_quizzes_async(mode="test")

    def update_test_timer(self):
        """시험 타이머 업데이트"""
        if self.test_remaining_time <= 0:
            # 시간 종료
            if self.test_timer_id:
                self.after_cancel(self.test_timer_id)
            messagebox.showwarning("시간 종료", "시험 시간이 종료되었습니다. 자동으로 제출됩니다.")
            self.submit_test_paper()
            return
        
        # 타이머 라벨 업데이트
        if hasattr(self, '_timer_label') and self._timer_label.winfo_exists():
            minutes = self.test_remaining_time // 60
            seconds = self.test_remaining_time % 60
            time_text = f"{minutes}:{seconds:02d}"
            
            # 시간이 적으면 색상 변경
            if self.test_remaining_time <= 300:  # 5분 이하
                color = COLOR_ERROR
            elif self.test_remaining_time <= 600:  # 10분 이하
                color = "#f59e0b"
            else:
                color = COLOR_SUCCESS
            
            self._timer_label.config(text=time_text, fg=color)
        
        self.test_remaining_time -= 1
        self.test_timer_id = self.after(1000, self.update_test_timer)
    
    def scroll_to_question(self, scroll_frame, question_index):
        """시험지에서 특정 문제로 스크롤"""
        # TODO: 이 기능은 추후 구현 (Canvas에서 yview_moveto 사용)
        pass


    def show_test_paper(self):
        """시험 모드: 스크롤 형태로 10문제 배치 + 타이머"""
        self.init_container()
        self.navigation_bar.update_info(f"시험모드 - {len(self.current_session_quizzes)}문제")
        
        # 헤더
        header = tk.Frame(self.main_container, bg="#f9fafb")
        header.pack(fill="x", padx=0, pady=0)
        
        header_content = tk.Frame(header, bg="#f9fafb", padx=30, pady=15)
        header_content.pack(fill="x")
        
        # 좌측: 타이틀
        left_title = tk.Frame(header_content, bg="#f9fafb")
        left_title.pack(side="left", fill="x", expand=True)
        
        tk.Label(left_title, text="📝 시험 모드", font=("Malgun Gothic", 18, "bold"), 
                fg=COLOR_DARK, bg="#f9fafb").pack(anchor="w")
        tk.Label(left_title, text=f"총 {len(self.current_session_quizzes)}문항 (객관식 5 + 주관식 5)", 
                font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg="#f9fafb").pack(anchor="w", pady=(2, 0))
        
        # 우측: 타이머
        timer_frame = tk.Frame(header_content, bg="#f9fafb")
        timer_frame.pack(side="right", fill="y")
        
        timer_label_text = tk.Label(timer_frame, text="⏱ 남은 시간:", font=("Malgun Gothic", 11), 
                                    fg=COLOR_DARK, bg="#f9fafb")
        timer_label_text.pack(side="left", padx=(0, 8))
        
        minutes = self.test_remaining_time // 60
        seconds = self.test_remaining_time % 60
        self._timer_label = tk.Label(timer_frame, text=f"{minutes}:{seconds:02d}", 
                                     font=("Malgun Gothic", 14, "bold"), fg=COLOR_SUCCESS, bg="#f9fafb")
        self._timer_label.pack(side="left")
        
        # 타이머 시작
        if self.test_timer_id:
            self.after_cancel(self.test_timer_id)
        self.test_timer_id = self.after(1000, self.update_test_timer)
        
        # 구분선
        sep = tk.Frame(header, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x")
        
        # 스크롤 가능한 본문 영역 생성
        scroll_container = ScrollableFrame(self.main_container)
        scroll_container.pack(expand=True, fill="both")
        
        sf = scroll_container.scrollable_frame
        
        # 상단 안내 문구
        lbl_info = tk.Label(sf, text="각 문제를 풀고 [임시 저장]을 누를 수 있습니다. 하단의 [최종 제출]로 답안을 제출하세요.",
                            font=("Malgun Gothic", 10), fg=COLOR_PRIMARY, bg=COLOR_BG, justify="center", pady=10)
        lbl_info.pack(fill="x", padx=30, pady=(15, 5))
        
        # 문제 카드들 렌더링
        self.test_answer_widgets = {}
        for idx, q_data in enumerate(self.current_session_quizzes):
            q_id = q_data["id"]
            q_type = q_data.get("type")
            
            # 카드 박스
            card = tk.Frame(sf, bg=COLOR_CARD)
            card.pack(fill="x", padx=30, pady=10)
            
            # 카드 상단 분류 표시
            type_bar = tk.Frame(card, bg=COLOR_PRIMARY if q_type == "objective" else "#8b5cf6", height=3)
            type_bar.pack(fill="x")
            
            pad_frame = tk.Frame(card, bg=COLOR_CARD, padx=20, pady=15)
            pad_frame.pack(fill="x")
            
            # 문제 타이틀
            lbl_title = tk.Label(pad_frame, text=f"문제 {idx + 1}. ({'객관식' if q_type == 'objective' else '주관식'})", 
                                 font=("Malgun Gothic", 11, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
            lbl_title.pack(anchor="w", pady=(0, 5))
            
            question_box = create_scrollable_question_box(
                pad_frame,
                q_data["question"],
                font=("Malgun Gothic", 12, "bold"),
                max_height=5,
                width_chars=78
            )
            question_box.pack(anchor="w", fill="x", pady=(0, 12))
            
            # 힌트 라벨 및 버튼 영역
            hint_lbl = tk.Label(pad_frame, text="", font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left")
            
            # 임시 저장 피드백 라벨
            status_lbl = tk.Label(pad_frame, text="미작성", font=("Malgun Gothic", 10, "bold"), fg=COLOR_ERROR, bg=COLOR_CARD)
            status_lbl.pack(side="top", anchor="e")
            
            # 문제 내용 영역 분기
            if q_type == "objective":
                # 라디오 버튼 변수
                var = tk.IntVar(value=0)
                # 만약 이전에 임시 저장한 값이 있으면 복구
                if self.test_temp_answers[q_id]["objective_ans"] is not None:
                    var.set(self.test_temp_answers[q_id]["objective_ans"])
                    status_lbl.config(text="임시 저장됨 ✓", fg=COLOR_SUCCESS)
                self.test_answer_widgets[q_id] = {
                    "type": "objective",
                    "var": var,
                    "status": status_lbl
                }
                    
                radio_buttons = []
                for i, opt_text in enumerate(q_data.get("options", [])):
                    num = i + 1
                    rb = tk.Radiobutton(pad_frame, text=opt_text, value=num, variable=var, 
                                        font=("Malgun Gothic", 10), bg=COLOR_CARD, activebackground=COLOR_CARD,
                                        fg=COLOR_DARK, selectcolor=COLOR_CARD)
                    rb.pack(anchor="w", padx=10, pady=3)
                    radio_buttons.append(rb)
                    
                # 객관식용 저장 람다
                def make_save_obj(qid=q_id, v=var, sl=status_lbl):
                    ans = v.get()
                    if ans == 0:
                        messagebox.showwarning("주의", "답안 번호를 선택한 후 저장해주세요.")
                        return
                    self.test_temp_answers[qid]["objective_ans"] = ans
                    self.test_temp_answers[qid]["saved"] = True
                    sl.config(text="임시 저장됨 ✓", fg=COLOR_SUCCESS)
                    
                save_cmd = make_save_obj
                
            else:
                # 주관식 코딩 에디터
                editor_frame = tk.Frame(pad_frame, bg="#2d3748", bd=1, relief="solid")
                editor_frame.pack(fill="x", pady=(12, 5))
                
                txt_area = tk.Text(editor_frame, height=5, font=("Consolas", 10), bg="#2d3748", fg="#f7fafc", 
                                   insertbackground="white", padx=8, pady=8, relief="flat")
                txt_area.pack(fill="x")
                
                # 기존 임시 저장된 코드 복구
                if self.test_temp_answers[q_id]["subjective_code"]:
                    txt_area.insert(tk.END, self.test_temp_answers[q_id]["subjective_code"])
                    status_lbl.config(text="임시 저장됨 ✓", fg=COLOR_SUCCESS)
                else:
                    txt_area.insert(tk.END, "여기에 답안을 입력하세요\n" if self.ex_mode else "# 코드를 작성하세요\n")
                self.test_answer_widgets[q_id] = {
                    "type": "subjective",
                    "text": txt_area,
                    "status": status_lbl
                }
                    
                # 주관식용 저장 람다
                def make_save_sub(qid=q_id, ta=txt_area, sl=status_lbl):
                    code = ta.get("1.0", tk.END).strip()
                    empty_markers = ("여기에 답안을 입력하세요", "# 코드를 작성하세요")
                    if not code or code in empty_markers:
                        messagebox.showwarning("주의", "답안을 작성한 후 저장해주세요.")
                        return
                    self.test_temp_answers[qid]["subjective_code"] = code
                    self.test_temp_answers[qid]["saved"] = True
                    sl.config(text="임시 저장됨 ✓", fg=COLOR_SUCCESS)
                    
                save_cmd = make_save_sub
                
            # 카드 내부 하단 컨트롤러 프레임
            ctrl_frame = tk.Frame(pad_frame, bg=COLOR_CARD)
            ctrl_frame.pack(fill="x", pady=(10, 0))
            
            # 힌트 보기 토글 버튼
            def make_toggle_hint(hl=hint_lbl, ht=q_data.get("hint", "힌트가 없습니다.")):
                if hl.cget("text"):
                    hl.config(text="")
                else:
                    hl.config(text=f"💡 힌트: {ht}")
            
            btn_hint = create_flat_button(ctrl_frame, "💡 힌트 보기", "#e2e8f0", COLOR_DARK, "#cbd5e0", 
                                          make_toggle_hint, font=("Malgun Gothic", 9))
            btn_hint.pack(side="left", ipadx=10, ipady=3)
            
            # 힌트 텍스트 라벨 패킹 위치 잡기 (컨트롤 밑에)
            hint_lbl.pack(anchor="w", pady=(5, 0))
            
            # 각 문항 '임시 저장' 버튼
            btn_save = create_flat_button(ctrl_frame, "💾 임시 저장", "#edf2f7", COLOR_DARK, "#cbd5e0", 
                                          save_cmd, font=("Malgun Gothic", 9, "bold"))
            btn_save.pack(side="right", ipadx=10, ipady=3)
            
        # 최하단 최종 제출 영역
        submit_card = tk.Frame(sf, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        submit_card.pack(fill="x", padx=30, pady=(15, 40))
        
        submit_pad = tk.Frame(submit_card, bg=COLOR_CARD, padx=25, pady=25)
        submit_pad.pack(fill="both", expand=True)
        
        tk.Label(submit_pad, text="모든 문제 풀이를 완료하셨다면 최종 제출을 눌러주세요.", 
                 font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD).pack(anchor="center", pady=(0, 10))
                 
        btn_final_submit = create_flat_button(submit_pad, "🚀 최종 제출 및 채점하기", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                             self.submit_test_paper, font=("Malgun Gothic", 12, "bold"))
        btn_final_submit.pack(fill="x", ipady=5)
        scroll_container.bind_children_to_mousewheel()

    def auto_save_unsaved_test_answers(self):
        """최종 제출 직전에 임시 저장되지 않은 입력값만 화면에서 읽어 저장한다."""
        auto_saved = []
        still_unsaved = []
        empty_markers = ("여기에 답안을 입력하세요", "# 코드를 작성하세요")
        
        for idx, q in enumerate(self.current_session_quizzes):
            q_id = q["id"]
            answer_state = self.test_temp_answers.get(q_id)
            if not answer_state or answer_state.get("saved"):
                continue
            
            widget_info = self.test_answer_widgets.get(q_id, {})
            q_type = q.get("type")
            
            if q_type == "objective":
                var = widget_info.get("var")
                ans = var.get() if var else 0
                if ans:
                    answer_state["objective_ans"] = ans
                    answer_state["saved"] = True
                    status_lbl = widget_info.get("status")
                    if status_lbl and status_lbl.winfo_exists():
                        status_lbl.config(text="자동 저장됨 ✓", fg=COLOR_SUCCESS)
                    auto_saved.append(idx + 1)
                else:
                    still_unsaved.append(idx + 1)
            else:
                text_widget = widget_info.get("text")
                user_text = text_widget.get("1.0", tk.END).strip() if text_widget else ""
                if user_text and user_text not in empty_markers:
                    answer_state["subjective_code"] = user_text
                    answer_state["saved"] = True
                    status_lbl = widget_info.get("status")
                    if status_lbl and status_lbl.winfo_exists():
                        status_lbl.config(text="자동 저장됨 ✓", fg=COLOR_SUCCESS)
                    auto_saved.append(idx + 1)
                else:
                    still_unsaved.append(idx + 1)
        
        return auto_saved, still_unsaved

    def submit_test_paper(self):
        """시험 최종 제출 처리 및 로딩 오버레이 채점 진행바 구동"""
        auto_saved, still_unsaved = self.auto_save_unsaved_test_answers()
        
        if still_unsaved:
            msg = f"답안이 비어 있는 문항이 있습니다: {still_unsaved}번\n비어 있는 상태로 최종 제출하시겠습니까?"
            if auto_saved:
                msg = f"임시 저장하지 않은 답안 {auto_saved}번은 자동 저장했습니다.\n\n{msg}"
            if not messagebox.askyesno("미작성 문항 존재", msg):
                return
        else:
            msg = "정말로 최종 제출하시겠습니까?\n제출 후에는 답안을 수정할 수 없습니다."
            if auto_saved:
                msg = f"임시 저장하지 않은 답안 {auto_saved}번은 자동 저장했습니다.\n\n{msg}"
            if not messagebox.askyesno("최종 제출", msg):
                return

        # 채점 프로그레스 오버레이 생성
        overlay = tk.Frame(self.main_container, bg="white")
        overlay.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)
        
        lbl_info = tk.Label(overlay, text="시험 답안을 전송 중입니다...", font=("Malgun Gothic", 14, "bold"), fg=COLOR_DARK, bg="white")
        lbl_info.pack(pady=(200, 20))
        
        progress_val = tk.DoubleVar()
        progress_bar = ttk.Progressbar(overlay, variable=progress_val, maximum=len(self.current_session_quizzes), length=400)
        progress_bar.pack(pady=10)
        
        lbl_count = tk.Label(overlay, text="채점 중입니다... (0/10)", font=("Malgun Gothic", 11), fg=COLOR_PRIMARY, bg="white")
        lbl_count.pack()
        
        # 비동기 단계별 채점 시뮬레이션 구현 (after를 통한 루프)
        results = []
        
        def grade_step(idx):
            if idx >= len(self.current_session_quizzes):
                # 모든 채점 완료
                overlay.destroy()
                self.finalize_test_grading(results)
                return
            
            q_data = self.current_session_quizzes[idx]
            q_id = q_data["id"]
            q_type = q_data["type"]
            ans_info = self.test_temp_answers[q_id]
            
            # 프로그레스바 및 라벨 업데이트
            progress_val.set(idx + 1)
            lbl_count.config(text=f"채점 중입니다... ({idx + 1}/{len(self.current_session_quizzes)})")
            
            def grade_worker():
                is_correct = False
                applied_feedback = ""
                stdout = ""
                user_input = ""
                
                if q_type == "objective":
                    user_ans = ans_info["objective_ans"]
                    user_input = user_ans
                    correct_key = q_data.get("key")
                    if user_ans is not None:
                        if user_ans == correct_key:
                            is_correct = True
                            applied_feedback = "정답입니다!"
                        else:
                            is_correct = False
                            applied_feedback = self.get_wrong_feedback(q_data, user_ans)
                    else:
                        is_correct = False
                        applied_feedback = "제출된 답안이 없습니다."
                else:
                    user_code = ans_info["subjective_code"]
                    user_input = user_code
                    if user_code:
                        # 로컬 컴파일/실행
                        temp_file = None
                        try:
                            with tempfile.NamedTemporaryFile("w", suffix=".txt" if self.ex_mode else ".py", encoding="utf-8", delete=False) as f:
                                if self.ex_mode:
                                    f.write('"""\\n' + user_code.replace('"""', '\\"\\"\\"') + '\\n"""')
                                else:
                                    f.write(user_code)
                                temp_file = f.name
                            # 2초 제한
                            res = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=2.0)
                            stdout = res.stdout.strip()
                            if res.returncode == 0:
                                is_correct = True
                            else:
                                is_correct = False
                                stdout = res.stderr.strip()
                        except subprocess.TimeoutExpired:
                            is_correct = False
                            stdout = "[Timeout] 무한 루프가 발생하여 2초 후 중단되었습니다."
                        except Exception as e:
                            is_correct = False
                            stdout = f"시스템 에러: {e}"
                        finally:
                            if temp_file and os.path.exists(temp_file):
                                try:
                                    os.remove(temp_file)
                                except:
                                    pass
                        
                        # AI 피드백 적용
                        evaluation = self.evaluate_subjective_answer(
                            q_data["question"],
                            q_data.get("evaluation_criteria", ""),
                            user_code,
                            stdout,
                            is_correct
                        )
                        is_correct = evaluation["is_correct"]
                        applied_feedback = evaluation["feedback"]
                    else:
                        is_correct = False
                        applied_feedback = "제출된 답안이 없습니다."
                
                results.append({
                    "id": q_id,
                    "type": q_type,
                    "question": q_data["question"],
                    "options": q_data.get("options", []),
                    "key": q_data.get("key", None),
                    "wrong_feedbacks": q_data.get("wrong_feedbacks", []),
                    "hint": q_data.get("hint", ""),
                    "evaluation_criteria": q_data.get("evaluation_criteria", ""),
                    "user_input": user_input,
                    "is_correct": is_correct,
                    "stdout": stdout,
                    "applied_feedback": applied_feedback
                })
                
                # 다음 문항 채점 실행 (시각적 채점 바 체감을 위해 200ms 지연)
                self.after(200, lambda: grade_step(idx + 1))
            
            threading.Thread(target=grade_worker, daemon=True).start()
            
        # 첫 번째 문제 채점 시작
        grade_step(0)

    def finalize_test_grading(self, results):
        """시험 채점이 완료된 후, 결과를 기록실에 저장하고 결과 화면을 렌더링합니다."""
        self.session_results = results
        correct_count = sum(1 for r in results if r["is_correct"])
        score_percentage = int((correct_count / len(results)) * 100)
        
        # 파일 저장
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{now_str}_시험모드.json"
        filepath = os.path.join(LIBRARY_DIR, filename)
        
        user_results_list = []
        for r in results:
            item = {
                "type": r["type"],
                "is_correct": r["is_correct"],
                "applied_feedback": r["applied_feedback"]
            }
            if r["type"] == "objective":
                item["user_answer"] = r["user_input"]
            else:
                item["user_code"] = r["user_input"]
                item["stdout"] = r["stdout"]
            user_results_list.append(item)

        save_data = {
            "session_info": {
                "mode": "test",
                "date_time": now_str,
                "total_questions": len(results),
                "score": f"{correct_count}/{len(results)}",
                "score_percentage": score_percentage
            },
            # 기록 다시 풀기 시 문제 세트를 복구할 수 있도록 퀴즈 원본과 결과를 구조화하여 합병해서 보존함
            "quiz_set": [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "question": r["question"],
                    "options": r["options"],
                    "key": r["key"],
                    "wrong_feedbacks": r["wrong_feedbacks"],
                    "hint": r["hint"],
                    "evaluation_criteria": r.get("evaluation_criteria", "")
                } for r in results
            ],
            "user_results": user_results_list
        }
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("저장 오류", f"기록실 저장에 실패했습니다.\n{e}")
            
        # 시험 평가 결과 리뷰 창 띄우기
        self.show_test_review_screen(correct_count, score_percentage)

    def show_test_review_screen(self, correct_count, score_percentage):
        """시험 제출 완료 후 결과를 카드로 덮어쓰고 피드백을 노출하는 상세 리뷰 화면"""
        self.init_container()
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="📊 시험 평가 결과 리포트", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 스크롤 가능 뷰어
        scroll_container = ScrollableFrame(self.main_container)
        scroll_container.pack(expand=True, fill="both")
        
        sf = scroll_container.scrollable_frame
        
        # 성적 카드 요약
        score_card = tk.Frame(sf, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        score_card.pack(fill="x", padx=30, pady=15)
        
        score_pad = tk.Frame(score_card, bg=COLOR_CARD, padx=25, pady=20)
        score_pad.pack(fill="both", expand=True)
        
        tk.Label(score_pad, text="💯 시험 성적 요약", font=("Malgun Gothic", 14, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w")
        
        score_info_frame = tk.Frame(score_pad, bg=COLOR_CARD)
        score_info_frame.pack(fill="x", pady=10)
        
        tk.Label(score_info_frame, text=f"맞춘 문항 수: {correct_count} / {len(self.session_results)}", 
                 font=("Malgun Gothic", 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_CARD).pack(side="left")
        tk.Label(score_info_frame, text=f"점수: {score_percentage}점", 
                 font=("Malgun Gothic", 13, "bold"), fg=COLOR_SUCCESS if score_percentage >= 60 else COLOR_ERROR, bg=COLOR_CARD).pack(side="right")
        
        # 문제 및 채점 내역 피드백 렌더링
        for idx, res in enumerate(self.session_results):
            is_correct = res["is_correct"]
            q_type = res["type"]
            
            # 카드 박스 (정답 여부에 따라 배경색 하이라이트)
            card_bg = COLOR_SUCCESS_LIGHT if is_correct else COLOR_ERROR_LIGHT
            card_border_color = COLOR_SUCCESS if is_correct else COLOR_ERROR
            
            card = tk.Frame(sf, bg=card_bg, bd=1, relief="solid", highlightthickness=0, highlightbackground=card_border_color)
            card.pack(fill="x", padx=30, pady=8)
            
            pad_frame = tk.Frame(card, bg=card_bg, padx=20, pady=15)
            pad_frame.pack(fill="x")
            
            # 문항 타이틀
            status_text = "정답 ✓" if is_correct else "오답 ✗"
            lbl_title = tk.Label(pad_frame, text=f"문제 {idx + 1}. ({'객관식' if q_type == 'objective' else '주관식'}) - {status_text}", 
                                 font=("Malgun Gothic", 11, "bold"), fg=COLOR_SUCCESS if is_correct else COLOR_ERROR, bg=card_bg)
            lbl_title.pack(anchor="w", pady=(0, 5))
            
            # 문제 내용
            question_box = create_scrollable_question_box(
                pad_frame,
                res["question"],
                bg=card_bg,
                font=("Malgun Gothic", 11, "bold"),
                max_height=5,
                width_chars=78
            )
            question_box.pack(anchor="w", fill="x", pady=(0, 10))
            
            # 작성한 답안 표시 및 피드백 덮어쓰기
            if q_type == "objective":
                # 선택 선지 내용 보여주기
                user_ans = res["user_input"]
                options = res.get("options", [])
                correct_key = res.get("key")
                
                ans_text = "없음"
                if user_ans is not None and 1 <= user_ans <= len(options):
                    ans_text = f"[{user_ans}번] {options[user_ans - 1]}"
                
                correct_text = f"[{correct_key}번] {options[correct_key - 1]}"
                
                lbl_user_ans = tk.Label(pad_frame, text=f"내가 선택한 답안: {ans_text}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=card_bg)
                lbl_user_ans.pack(anchor="w")
                
                lbl_correct_ans = tk.Label(pad_frame, text=f"정답 선지: {correct_text}", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=card_bg)
                lbl_correct_ans.pack(anchor="w", pady=(0, 5))
                
                lbl_fb = tk.Label(pad_frame, text=f"💡 채점 피드백: {res['applied_feedback']}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=card_bg, wraplength=780, justify="left")
                lbl_fb.pack(anchor="w")
                
            else:
                # 주관식 소스 코드
                lbl_code_title = tk.Label(pad_frame, text="제출한 소스코드:", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=card_bg)
                lbl_code_title.pack(anchor="w")
                
                code_text = tk.Text(pad_frame, height=4, font=("Consolas", 9), bg="#2d3748", fg="#f7fafc", padx=5, pady=5, relief="flat")
                code_text.pack(fill="x", pady=(2, 5))
                code_text.insert(tk.END, res["user_input"])
                code_text.config(state="disabled")
                
                # 콘솔 및 피드백
                if res["stdout"]:
                    lbl_stdout = tk.Label(pad_frame, text=f"▶ 실행 출력:\n{res['stdout']}", font=("Consolas", 9), fg="#2d3748", bg=card_bg, justify="left", anchor="w")
                    lbl_stdout.pack(anchor="w", pady=(0, 5))
                    
                lbl_fb = tk.Label(pad_frame, text=f"💡 채점 피드백: {res['applied_feedback']}", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=card_bg, wraplength=780, justify="left")
                lbl_fb.pack(anchor="w")
                
        # 목록 맨 밑에 메인메뉴로 돌아가는 버튼 배치
        footer_btn = create_flat_button(sf, "🏠 메인 메뉴로 돌아가기", COLOR_DARK, "#ffffff", "#4a5568", 
                                       self.show_main_menu, font=("Malgun Gothic", 11, "bold"))
        footer_btn.pack(pady=(20, 40), ipadx=30, ipady=6)
        scroll_container.bind_children_to_mousewheel()

    # ------------------------------------------
    # 4-4. 기록실(Library) 및 다시 풀기 기능 구현
    # ------------------------------------------
    
    def show_library(self):
        """기록실: 저장된 파일 목록 리스트 및 요약 정보 제공"""
        self.init_container()
        self.navigation_bar.update_info("기록실 - 풀이 기록 보관")
        
        header = tk.Frame(self.main_container, bg="#f9fafb")
        header.pack(fill="x", padx=0, pady=0)
        
        header_content = tk.Frame(header, bg="#f9fafb", padx=30, pady=20)
        header_content.pack(fill="x")
        
        tk.Label(header_content, text="🗂️ 기록실", font=("Malgun Gothic", 18, "bold"), 
                fg=COLOR_DARK, bg="#f9fafb").pack(anchor="w")
        tk.Label(header_content, text="이전에 풀었던 모든 세션의 기록을 확인합니다", font=("Malgun Gothic", 11), 
                fg=COLOR_TEXT_MUTED, bg="#f9fafb").pack(anchor="w", pady=(3, 0))
        
        # 구분선
        sep = tk.Frame(header, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x")
        
        # 바디 구성 (좌측: 파일 리스트, 우측: 선택 기록 상세 요약 및 제어 버튼)
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=30, pady=20)
        
        # 좌측 영역
        left_frame = tk.Frame(body, bg=COLOR_BG)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 15))
        
        tk.Label(left_frame, text="풀이 기록 목록 (최신순)", font=("Malgun Gothic", 11, "bold"), fg=COLOR_DARK, bg=COLOR_BG).pack(anchor="w", pady=(0, 8))
        
        listbox_frame = tk.Frame(left_frame, bg=COLOR_CARD)
        listbox_frame.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side="right", fill="y")
        
        listbox = tk.Listbox(listbox_frame, font=("Malgun Gothic", 10), yscrollcommand=scrollbar.set, 
                            relief="flat", bg=COLOR_BUTTON_BG, fg=COLOR_DARK, highlightthickness=0)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        # 우측 상세 정보 프레임
        right_frame = tk.Frame(body, width=350, bg=COLOR_CARD, highlightthickness=0)
        right_frame.pack(side="right", fill="both", padx=(15, 0))
        right_frame.pack_propagate(False)
        
        # 패딩 설정
        right_pad = tk.Frame(right_frame, bg=COLOR_CARD, padx=20, pady=20)
        right_pad.pack(fill="both", expand=True)
        
        tk.Label(right_pad, text="📊 기록 상세", font=("Malgun Gothic", 12, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 12))
        
        # 메타데이터 표기 위젯들
        lbl_m_mode = tk.Label(right_pad, text="학습 모드: -", font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        lbl_m_mode.pack(anchor="w", pady=4)
        
        lbl_m_date = tk.Label(right_pad, text="일시: -", font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        lbl_m_date.pack(anchor="w", pady=4)
        
        lbl_m_score = tk.Label(right_pad, text="성적: -", font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        lbl_m_score.pack(anchor="w", pady=4)
        
        # 제어용 컨트롤 패널
        ctrl_frame = tk.Frame(right_pad, bg=COLOR_CARD)
        ctrl_frame.pack(fill="x", side="bottom", pady=10)
        
        btn_view = create_flat_button(ctrl_frame, "👁️ 상세보기", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                     None, font=("Malgun Gothic", 10, "bold"))
        btn_view.pack(fill="x", pady=3)
        btn_view.config(state="disabled")
        
        btn_resolve = create_flat_button(ctrl_frame, "🔄 이 문제 세트 다시 풀기", COLOR_SUCCESS, "#ffffff", "#38a169", 
                                        None, font=("Malgun Gothic", 10, "bold"))
        btn_resolve.pack(fill="x", pady=5)
        btn_resolve.config(state="disabled")
        
        # 파일 목록 불러오기
        json_files = []
        try:
            files = os.listdir(LIBRARY_DIR)
            json_files = [f for f in files if f.endswith('.json')]
            json_files.sort(reverse=True) # 최신순
        except Exception as e:
            messagebox.showerror("오류", f"기록 목록을 읽을 수 없습니다.\n{e}")
            
        if not json_files:
            listbox.insert(tk.END, "저장된 풀이 기록이 없습니다.")
        else:
            for f in json_files:
                # 가독성 높은 이름으로 변환
                # 예: 20260607_180000_시험모드.json
                # => [시험모드] 2026년 06월 07일 18:00:00
                parts = f.replace(".json", "").split("_")
                if len(parts) >= 3:
                    date_str, time_str, mode_name = parts[0], parts[1], parts[2]
                    formatted = f"[{mode_name}] {date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
                else:
                    formatted = f.replace(".json", "")
                listbox.insert(tk.END, formatted)
                
        # 리스트 박스 클릭 바인딩
        def on_listbox_select(event):
            selection = listbox.curselection()
            if not selection:
                return
            idx = selection[0]
            if not json_files:
                return
                
            selected_file = json_files[idx]
            filepath = os.path.join(LIBRARY_DIR, selected_file)
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                info = data.get("session_info", {})
                mode = info.get("mode", "알 수 없음")
                date_time = info.get("date_time", "알 수 없음")
                score = info.get("score", "-")
                
                # 라벨 업데이트
                mode_kr = {"concept": "개념 모드", "learning": "학습 모드", "test": "시험 모드"}.get(mode, mode)
                lbl_m_mode.config(text=f"학습 모드: {mode_kr}")
                
                # 날짜 형식 정리
                if "_" in date_time:
                    d, t = date_time.split("_")
                    formatted_dt = f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}:{t[4:]}"
                else:
                    formatted_dt = date_time
                lbl_m_date.config(text=f"일시: {formatted_dt}")
                
                total = info.get("total_questions", 0)
                lbl_m_score.config(text=f"성적: {score} (총 {total}문항)")
                
                # 버튼 명령어 바인딩 및 활성화
                btn_view.config(state="normal", command=lambda: self.view_past_session_results(selected_file))
                btn_resolve.config(state="normal", command=lambda: self.resolve_past_session(selected_file))
                
            except Exception as e:
                messagebox.showerror("오류", f"기록 상세 요약을 불러오지 못했습니다.\n{e}")
                
        listbox.bind("<<ListboxSelect>>", on_listbox_select)
        
        # 하단 전체 네비게이션
        footer = tk.Frame(self.main_container, bg=COLOR_BG)
        footer.pack(fill="x", side="bottom", pady=15, padx=30)
        
        create_flat_button(footer, "⬅ 메인 메뉴로", COLOR_DARK, "#ffffff", "#4a5568", 
                           self.show_main_menu, font=("Malgun Gothic", 10, "bold")).pack(side="left", ipadx=15, ipady=4)

    def view_past_session_results(self, filename):
        """기록실: 특정 기록의 풀이 전체 보기 (읽기 전용 리포트)"""
        self.init_container()
        
        # 파일 열기
        filepath = os.path.join(LIBRARY_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("오류", f"파일을 불러오는 도중 에러가 발생했습니다: {e}")
            self.show_library()
            return
            
        info = data.get("session_info", {})
        mode = info.get("mode", "concept")
        score = info.get("score", "-")
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        mode_kr = {"concept": "개념 모드", "learning": "학습 모드", "test": "시험 모드"}.get(mode, mode)
        tk.Label(header, text=f"🗂️ 풀이 기록 상세: {mode_kr} (성적: {score})", font=("Malgun Gothic", 15, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 스크롤 가능 컨테이너
        scroll_container = ScrollableFrame(self.main_container)
        scroll_container.pack(expand=True, fill="both")
        
        sf = scroll_container.scrollable_frame
        
        # 문제 및 기록 복합 렌더링
        quiz_set = data.get("quiz_set", [])
        user_results = data.get("user_results", [])
        
        # 만약 quiz_set이 비어있으면 (구버전 또는 학습모드처럼 quiz_set이 누락된 세션의 경우)
        # user_results를 직접 풀어서 렌더링
        if not quiz_set:
            for idx, res in enumerate(user_results):
                is_correct = res.get("is_correct", False)
                q_type = res.get("type", "objective")
                
                bg_color = COLOR_SUCCESS_LIGHT if is_correct else COLOR_ERROR_LIGHT
                border_color = COLOR_SUCCESS if is_correct else COLOR_ERROR
                
                card = tk.Frame(sf, bg=bg_color, bd=1, relief="solid", highlightthickness=0, highlightbackground=border_color)
                card.pack(fill="x", padx=30, pady=8)
                
                pad = tk.Frame(card, bg=bg_color, padx=20, pady=15)
                pad.pack(fill="x")
                
                status_text = "정답 ✓" if is_correct else "오답 ✗"
                tk.Label(pad, text=f"문제 {idx + 1}. ({'객관식' if q_type == 'objective' else '주관식'}) - {status_text}", 
                         font=("Malgun Gothic", 11, "bold"), fg=COLOR_SUCCESS if is_correct else COLOR_ERROR, bg=bg_color).pack(anchor="w", pady=(0, 5))
                
                tk.Label(pad, text=res.get("question", "질문 내역이 없는 구버전 기록입니다."), font=("Malgun Gothic", 11, "bold"), fg=COLOR_DARK, bg=bg_color, justify="left", anchor="w", wraplength=780).pack(anchor="w", fill="x", pady=(0, 10))
                
                if q_type == "objective":
                    user_ans = res.get("user_answer")
                    tk.Label(pad, text=f"내가 쓴 답안 번호: {user_ans}번", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=bg_color).pack(anchor="w")
                    tk.Label(pad, text=f"💡 채점 피드백: {res.get('applied_feedback', '기록이 없습니다.')}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=bg_color, wraplength=780, justify="left").pack(anchor="w", pady=(5, 0))
                else:
                    tk.Label(pad, text="제출한 소스코드:", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=bg_color).pack(anchor="w")
                    code_text = tk.Text(pad, height=4, font=("Consolas", 9), bg="#2d3748", fg="#f7fafc", padx=5, pady=5, relief="flat")
                    code_text.pack(fill="x", pady=(2, 5))
                    code_text.insert(tk.END, res.get("user_code", ""))
                    code_text.config(state="disabled")
                    tk.Label(pad, text=f"💡 채점 피드백: {res.get('applied_feedback', '기록이 없습니다.')}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=bg_color, wraplength=780, justify="left").pack(anchor="w", pady=(5, 0))
        else:
            # 신버전 매핑 구조 렌더링
            for idx, quiz in enumerate(quiz_set):
                res = user_results[idx]
                is_correct = res["is_correct"]
                q_type = quiz["type"]
                
                bg_color = COLOR_SUCCESS_LIGHT if is_correct else COLOR_ERROR_LIGHT
                border_color = COLOR_SUCCESS if is_correct else COLOR_ERROR
                
                card = tk.Frame(sf, bg=bg_color, bd=1, relief="solid", highlightthickness=0, highlightbackground=border_color)
                card.pack(fill="x", padx=30, pady=8)
                
                pad = tk.Frame(card, bg=bg_color, padx=20, pady=15)
                pad.pack(fill="x")
                
                status_text = "정답 ✓" if is_correct else "오답 ✗"
                tk.Label(pad, text=f"문제 {idx + 1}. ({'객관식' if q_type == 'objective' else '주관식'}) - {status_text}", 
                         font=("Malgun Gothic", 11, "bold"), fg=COLOR_SUCCESS if is_correct else COLOR_ERROR, bg=bg_color).pack(anchor="w", pady=(0, 5))
                
                tk.Label(pad, text=quiz["question"], font=("Malgun Gothic", 11, "bold"), fg=COLOR_DARK, bg=bg_color, justify="left", anchor="w", wraplength=780).pack(anchor="w", fill="x", pady=(0, 10))
                
                if q_type == "objective":
                    user_ans = res.get("user_input", res.get("user_answer"))
                    options = quiz.get("options", [])
                    correct_key = quiz.get("key")
                    
                    ans_text = "없음"
                    if user_ans is not None and 1 <= user_ans <= len(options):
                        ans_text = f"[{user_ans}번] {options[user_ans - 1]}"
                    correct_text = f"[{correct_key}번] {options[correct_key - 1]}"
                    
                    tk.Label(pad, text=f"내가 선택한 답안: {ans_text}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=bg_color).pack(anchor="w")
                    tk.Label(pad, text=f"정답 선지: {correct_text}", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=bg_color).pack(anchor="w", pady=(0, 5))
                    tk.Label(pad, text=f"💡 채점 피드백: {res['applied_feedback']}", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=bg_color, wraplength=780, justify="left").pack(anchor="w")
                else:
                    tk.Label(pad, text="제출한 소스코드:", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=bg_color).pack(anchor="w")
                    code_text = tk.Text(pad, height=4, font=("Consolas", 9), bg="#2d3748", fg="#f7fafc", padx=5, pady=5, relief="flat")
                    code_text.pack(fill="x", pady=(2, 5))
                    code_text.insert(tk.END, res.get("user_input", res.get("user_code", "")))
                    code_text.config(state="disabled")
                    
                    if res.get("stdout"):
                        tk.Label(pad, text=f"▶ 실행 출력:\n{res['stdout']}", font=("Consolas", 9), fg="#2d3748", bg=bg_color, justify="left", anchor="w").pack(anchor="w", pady=(0, 5))
                    tk.Label(pad, text=f"💡 채점 피드백: {res['applied_feedback']}", font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=bg_color, wraplength=780, justify="left").pack(anchor="w")
                    
        # 뒤로 가기
        btn_back = create_flat_button(sf, "⬅ 기록소 목록으로 돌아가기", COLOR_DARK, "#ffffff", "#4a5568", 
                                      self.show_library, font=("Malgun Gothic", 10, "bold"))
        btn_back.pack(pady=(20, 40), ipadx=25, ipady=5)
        scroll_container.bind_children_to_mousewheel()

    def resolve_past_session(self, filename):
        """기록실: 특정 기록에 사용되었던 동일한 문제 풀을 불러와 다시 풀이 시작"""
        filepath = os.path.join(LIBRARY_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("오류", f"기록을 읽어올 수 없습니다: {e}")
            return
            
        info = data.get("session_info", {})
        mode = info.get("mode", "test")
        quiz_set = data.get("quiz_set", [])
        
        # 구버전 등 quiz_set이 온전히 없으면 재수행 불가 처리
        if not quiz_set:
            # 구버전 user_results를 역 파싱해서 문제들을 추출해봄
            user_results = data.get("user_results", [])
            quiz_set = []
            for r in user_results:
                if "question" in r:
                    quiz_set.append({
                        "id": r.get("quiz_id", random.randint(100, 999)),
                        "type": r.get("type", "objective"),
                        "question": r.get("question"),
                        "options": r.get("options", ["1", "2", "3", "4", "5"]), # Mock fallback
                        "key": r.get("key", 1),
                        "wrong_feedbacks": r.get("wrong_feedbacks", []),
                        "hint": r.get("hint", ""),
                        "evaluation_criteria": r.get("evaluation_criteria", "")
                    })
            
            if not quiz_set:
                messagebox.showwarning("주의", "이 기록 파일은 예전 규격으로 저장되어 문제 세트를 구성할 수 없습니다.")
                return
                
        # 문제 세션 셋업
        self.current_session_quizzes = quiz_set
        self.current_q_index = 0
        self.session_results = []
        self.current_mode = mode
        
        # 다시 풀기 알림
        mode_kr = {"concept": "개념 모드", "learning": "학습 모드", "test": "시험 모드"}.get(mode, mode)
        messagebox.showinfo("다시 풀기 시작", f"[{mode_kr}] 과거에 풀었던 {len(quiz_set)}문제로 세션을 시작합니다.")
        
        if mode == "concept":
            self.show_concept_quiz_question()
        elif mode == "learning":
            self.show_learning_question()
        else:
            # 시험 모드용 임시 저장 데이터 초기화
            self.test_temp_answers = {}
            self.test_answer_widgets = {}
            for q in self.current_session_quizzes:
                self.test_temp_answers[q["id"]] = {
                    "objective_ans": None,
                    "subjective_code": "",
                    "saved": False
                }
            self.show_test_paper()

    # ------------------------------------------
    # 4-5. 학습/개념 모드 완료 화면
    # ------------------------------------------
    
    def show_session_end(self):
        """학습/개념 모드가 정상 종료되었을 때 결과를 기록실에 저장하고 보여주는 화면"""
        self.init_container()
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="🎉 학습을 마쳤습니다!", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=40, pady=30)
        
        card = tk.Frame(body, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card.pack(fill="both", expand=True, padx=30, pady=10)
        
        pad = tk.Frame(card, bg=COLOR_CARD, padx=30, pady=30)
        pad.pack(fill="both", expand=True)
        
        correct_count = sum(1 for r in self.session_results if r.get("is_correct", False))
        total = len(self.current_session_quizzes)
        accuracy = int((correct_count / total) * 100) if total > 0 else 0
        
        # 성적 출력
        tk.Label(pad, text="📊 학습 결과 리포트", font=("Malgun Gothic", 15, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w")
        
        score_frame = tk.Frame(pad, bg=COLOR_CARD)
        score_frame.pack(fill="x", pady=15)
        tk.Label(score_frame, text=f"맞춘 문제 수: {correct_count} / {total}", font=("Malgun Gothic", 11), fg=COLOR_DARK, bg=COLOR_CARD).pack(side="left")
        tk.Label(score_frame, text=f"정답률: {accuracy}%", font=("Malgun Gothic", 12, "bold"), fg=COLOR_SUCCESS if accuracy >= 60 else COLOR_ERROR, bg=COLOR_CARD).pack(side="right")
        
        # 파일 저장
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_name_kr = {"concept": "개념모드", "learning": "학습모드"}.get(self.current_mode, "학습결과")
        filename = f"{now_str}_{mode_name_kr}.json"
        filepath = os.path.join(LIBRARY_DIR, filename)
        
        user_results_list = []
        for idx, (q, r) in enumerate(zip(self.current_session_quizzes, self.session_results)):
            item = {
                "type": r.get("type", q.get("type", "objective")),
                "is_correct": r.get("is_correct", False),
                "applied_feedback": r.get("applied_feedback", "")
            }
            if item["type"] == "objective":
                item["user_answer"] = r.get("user_answer")
            else:
                item["user_code"] = r.get("user_code", "")
                item["stdout"] = r.get("stdout", "")
            user_results_list.append(item)

        save_data = {
            "session_info": {
                "mode": self.current_mode,
                "date_time": now_str,
                "total_questions": total,
                "score": f"{correct_count}/{total}",
                "score_percentage": accuracy
            },
            # 복구를 위해 퀴즈 및 풀이 결과를 저장함
            "quiz_set": [
                {
                    "id": q.get("id", idx),
                    "type": q.get("type", "objective"),
                    "question": q.get("question"),
                    "options": q.get("options", []),
                    "key": q.get("key", None),
                    "wrong_feedbacks": q.get("wrong_feedbacks", []),
                    "hint": q.get("hint", ""),
                    "evaluation_criteria": q.get("evaluation_criteria", "")
                } for idx, q in enumerate(self.current_session_quizzes)
            ],
            "user_results": user_results_list
        }
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            lbl_save = tk.Label(pad, text=f"풀이 기록이 기록실에 안전하게 저장되었습니다.\n(파일명: {filename})", 
                                font=("Malgun Gothic", 10), fg=COLOR_PRIMARY, bg=COLOR_CARD, justify="left")
            lbl_save.pack(anchor="w", pady=(10, 20))
        except Exception as e:
            messagebox.showerror("저장 에러", f"기록실 저장 중 오류가 발생했습니다: {e}")
            
        # 조작 단추
        btn_home = create_flat_button(pad, "🏠 메인 메뉴로 이동", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                     self.show_main_menu, font=("Malgun Gothic", 11, "bold"))
        btn_home.pack(fill="x", ipady=5)

# ==========================================
# 실행 엔트리
# ==========================================
if __name__ == "__main__":
    app = PythonTutorApp()
    app.mainloop()
