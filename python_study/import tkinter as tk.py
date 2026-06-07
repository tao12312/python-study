import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import datetime
import subprocess
import sys
import random
import tempfile

# ==========================================
# 1. 환경 설정 및 상수 정의
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CONCEPTS_DIR = os.path.join(BASE_DIR, "concepts")
MOCK_FILE = os.path.join(BASE_DIR, "mock_quiz.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# 테마 컬러 정의 (Modern Light Slate Theme)
COLOR_BG = "#edf2f7"          # 전체 배경색 (연한 회색)
COLOR_CARD = "#ffffff"        # 카드/컨테이너 배경색 (흰색)
COLOR_PRIMARY = "#3182ce"     # 주조색 (블루)
COLOR_PRIMARY_HOVER = "#2b6cb0" # 블루 호버
COLOR_DARK = "#2d3748"        # 어두운 색 (텍스트 및 헤더)
COLOR_TEXT_MUTED = "#718096"  # 연한 텍스트 (그레이)
COLOR_SUCCESS = "#48bb78"     # 성공/정답 (그린)
COLOR_SUCCESS_LIGHT = "#f0fff4"# 연한 그린 (배경용)
COLOR_ERROR = "#f56565"       # 실패/오답 (레드)
COLOR_ERROR_LIGHT = "#fff5f5"  # 연한 레드 (배경용)
COLOR_BORDER = "#e2e8f0"      # 보더/구분선

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
# 3. 메인 애플리케이션 클래스
# ==========================================
class PythonTutorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Python Tutor - Prototype v0.1")
        self.geometry("900x700")
        self.configure(bg=COLOR_BG)
        
        # 상태 변수 (State)
        self.quiz_data = []          # 전체 문제 뱅크
        self.current_session_quizzes = [] # 현재 세션에서 풀 문제 리스트 (최대 10개)
        self.current_q_index = 0     # 현재 문제 인덱스 (개념, 학습모드용)
        self.session_results = []    # 풀이 결과 리스트
        self.current_mode = ""       # "concept", "learning", "test"
        
        # 시험 모드용 임시 저장 변수
        # 구조: { quiz_id: { "objective_ans": int, "subjective_code": str, "saved": bool } }
        self.test_temp_answers = {}
        
        # UI 프레임 참조 변수
        self.main_container = None
        
        # 초기화 및 메뉴 렌더링
        ensure_environment()
        self.load_quiz_data()
        self.show_main_menu()

    def load_quiz_data(self):
        """mock_quiz.json에서 문제를 읽어 메모리에 저장합니다."""
        try:
            if os.path.exists(MOCK_FILE):
                with open(MOCK_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.quiz_data = data.get("quiz_set", [])
            else:
                self.quiz_data = []
        except Exception as e:
            messagebox.showerror("오류", f"문제 파일을 읽을 수 없습니다.\n{e}")
            self.quiz_data = []

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

    def init_container(self):
        """메인 윈도우 내부의 컨테이너를 새로 만듭니다."""
        if self.main_container:
            self.main_container.destroy()
        
        self.main_container = tk.Frame(self, bg=COLOR_BG)
        self.main_container.pack(fill="both", expand=True)

    # ==========================================
    # 4. 화면 구현 (Views)
    # ==========================================
    
    def show_main_menu(self):
        """메인 메뉴 화면 (4개의 모드 카드 제공)"""
        self.init_container()
        
        # 타이틀 영역
        header_frame = tk.Frame(self.main_container, bg=COLOR_DARK)
        header_frame.pack(fill="x", pady=(20, 0))
        
        lbl_title = tk.Label(header_frame, text="🐍 Python Learning Program", font=("Malgun Gothic", 20, "bold"), fg="#ffffff", bg=COLOR_DARK)
        lbl_title.pack(pady=10)
        lbl_subtitle = tk.Label(header_frame, text="AI 튜터 기반의 개인화된 파이썬 학습 환경", font=("Malgun Gothic", 11), fg="#a0aec0", bg=COLOR_DARK)
        lbl_subtitle.pack()
        
        # 카드 프레임 레이아웃
        cards_frame = tk.Frame(self.main_container, bg=COLOR_BG)
        cards_frame.pack(expand=True, fill="both", padx=50, pady=40)
        
        # 2x2 그리드 설정
        cards_frame.grid_columnconfigure(0, weight=1, uniform="group1")
        cards_frame.grid_columnconfigure(1, weight=1, uniform="group1")
        cards_frame.grid_rowconfigure(0, weight=1, uniform="group2")
        cards_frame.grid_rowconfigure(1, weight=1, uniform="group2")
        
        # 각 카드 내용 선언
        modes = [
            {
                "title": "📚 개념 모드",
                "desc": "단원별 개념 정리 노트를 읽고\n이해도를 검증하는 객관식 10문항을 풉니다.",
                "color": "#3182ce", "hover": "#2b6cb0",
                "cmd": self.show_concept_selection
            },
            {
                "title": "⚡ 학습 모드",
                "desc": "객관식 또는 주관식 유형을 직접 선택하여\n1문제씩 즉시 피드백을 받으며 정밀 학습합니다.",
                "color": "#319795", "hover": "#2c7a7b",
                "cmd": self.show_learning_selection
            },
            {
                "title": "📝 시험 모드",
                "desc": "혼합 구성된 10문항을 스크롤식 시험지로 풀고,\n답안 임시 저장 후 최종 제출하여 종합 평가를 받습니다.",
                "color": "#805ad5", "hover": "#6b46c1",
                "cmd": self.start_test_mode
            },
            {
                "title": "🗂️ 기록실 (Library)",
                "desc": "이전에 풀었던 모든 모드의 세션 기록과 채점 결과를\n불러와 다시 확인하거나 같은 문제로 다시 도전합니다.",
                "color": "#4a5568", "hover": "#343a40",
                "cmd": self.show_library
            }
        ]
        
        for idx, mode in enumerate(modes):
            r = idx // 2
            c = idx % 2
            
            # 카드 프레임
            card = tk.Frame(cards_frame, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
            card.grid(row=r, column=c, padx=15, pady=15, sticky="nsew")
            
            # 패딩 프레임
            padding_frame = tk.Frame(card, bg=COLOR_CARD, padx=25, pady=25)
            padding_frame.pack(fill="both", expand=True)
            
            lbl_m_title = tk.Label(padding_frame, text=mode["title"], font=("Malgun Gothic", 14, "bold"), fg=COLOR_DARK, bg=COLOR_CARD)
            lbl_m_title.pack(anchor="w", pady=(0, 10))
            
            lbl_m_desc = tk.Label(padding_frame, text=mode["desc"], font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left")
            lbl_m_desc.pack(anchor="w", pady=(0, 20))
            
            # 진입 버튼
            btn = create_flat_button(padding_frame, "입장하기 ➔", mode["color"], "#ffffff", mode["hover"], mode["cmd"], font=("Malgun Gothic", 10, "bold"))
            btn.pack(fill="x", side="bottom")

    # ------------------------------------------
    # 4-1. 개념 모드 관련 화면
    # ------------------------------------------
    
    def show_concept_selection(self):
        """개념 모드: 개념지 목록 선택 화면"""
        self.init_container()
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="📚 개념 모드 - 단원 선택", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=50, pady=30)
        
        # 가이드 텍스트
        tk.Label(body, text="공부하고 싶은 단원을 선택하세요. 개념지를 읽은 후, 관련 테스트 10문제가 출제됩니다.", 
                 font=("Malgun Gothic", 11), fg=COLOR_DARK, bg=COLOR_BG).pack(pady=(0, 20))
        
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
        
        # 해당 개념(filename)에 해당하는 객관식 문제 추출
        matched = [q for q in self.quiz_data if q.get("type") == "objective" and q.get("concept") == filename]
        
        # 만약 해당 개념의 문제가 10개 미만이면, 다른 객관식 문제들을 채워서 10문제를 만듦
        if len(matched) < 10:
            other_obj = [q for q in self.quiz_data if q.get("type") == "objective" and q.get("concept") != filename]
            # 랜덤 패딩
            random.shuffle(other_obj)
            matched.extend(other_obj[:10 - len(matched)])
            
        # 세션 문제 확정 (최대 10개)
        self.current_session_quizzes = matched[:10]
        
        if not self.current_session_quizzes:
            messagebox.showwarning("경고", "문제가 구성되지 않았습니다. mock_quiz.json을 확인해주세요.")
            self.show_concept_selection()
            return
            
        self.show_concept_quiz_question()

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
        lbl_q = tk.Label(content_frame, text=f"Q. {q_data['question']}", font=("Malgun Gothic", 13, "bold"), 
                         fg=COLOR_DARK, bg=COLOR_CARD, justify="left", anchor="w", wraplength=700)
        lbl_q.pack(fill="x", pady=(0, 20))
        
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
        
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="⚡ 학습 모드 - 유형 선택", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=50, pady=40)
        
        tk.Label(body, text="원하는 문항 형태를 선택하세요. 유형별로 1문제씩 풀며 상세한 피드백을 받습니다.", 
                 font=("Malgun Gothic", 11), fg=COLOR_DARK, bg=COLOR_BG).pack(pady=(0, 30))
        
        cards_frame = tk.Frame(body, bg=COLOR_BG)
        cards_frame.pack(fill="x")
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)
        
        # 객관식 카드
        card_obj = tk.Frame(cards_frame, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card_obj.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        card_obj_pad = tk.Frame(card_obj, bg=COLOR_CARD, padx=25, pady=25)
        card_obj_pad.pack(fill="both", expand=True)
        
        tk.Label(card_obj_pad, text="📝 객관식 학습", font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 10))
        tk.Label(card_obj_pad, text="5지선다 객관식 문항만을 선별하여\n풀고, 오답 시 문항별 튜터 분석 피드백을 확인합니다.", 
                 font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left").pack(anchor="w", pady=(0, 20))
        create_flat_button(card_obj_pad, "객관식 시작 ➔", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                           lambda: self.start_learning_session("objective")).pack(fill="x")
        
        # 주관식 카드
        card_sub = tk.Frame(cards_frame, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        card_sub.grid(row=0, column=1, padx=15, pady=10, sticky="nsew")
        card_sub_pad = tk.Frame(card_sub, bg=COLOR_CARD, padx=25, pady=25)
        card_sub_pad.pack(fill="both", expand=True)
        
        tk.Label(card_sub_pad, text="💻 주관식 코딩 학습", font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 10))
        tk.Label(card_sub_pad, text="직접 코드를 작성하고 실시간으로\n로컬 샌드박스에서 실행해 보며 작동 유무와 피드백을 받습니다.", 
                 font=("Malgun Gothic", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, justify="left").pack(anchor="w", pady=(0, 20))
        create_flat_button(card_sub_pad, "주관식 시작 ➔", "#319795", "#ffffff", "#2c7a7b", 
                           lambda: self.start_learning_session("subjective")).pack(fill="x")
        
        btn_back = create_flat_button(body, "⬅ 메인 메뉴로", COLOR_DARK, "#ffffff", "#4a5568", self.show_main_menu)
        btn_back.pack(pady=40, ipadx=20, ipady=5)

    def start_learning_session(self, q_type):
        """학습 모드 세션 필터링 및 시작"""
        self.current_mode = "learning"
        self.current_q_index = 0
        self.session_results = []
        
        # 타입에 맞는 모든 문제 로드
        matched = [q for q in self.quiz_data if q.get("type") == q_type]
        
        if not matched:
            messagebox.showwarning("경고", f"{q_type} 타입에 매칭되는 문제가 없습니다.")
            return
            
        self.current_session_quizzes = matched
        self.show_learning_question()

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
        lbl_q = tk.Label(content_frame, text=f"Q. {q_data['question']}", font=("Malgun Gothic", 13, "bold"), 
                         fg=COLOR_DARK, bg=COLOR_CARD, justify="left", anchor="w", wraplength=700)
        lbl_q.pack(fill="x", pady=(0, 20))
        
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
            code_label = tk.Label(content_frame, text="파이썬 코드를 작성하세요 (결과가 에러 없이 작동해야 정답 판정):", 
                                  font=("Malgun Gothic", 10, "bold"), fg=COLOR_DARK, bg=COLOR_CARD)
            code_label.pack(anchor="w", pady=(0, 5))
            
            # 에디터 프레임
            editor_frame = tk.Frame(content_frame, bg="#2d3748", bd=1, relief="solid")
            editor_frame.pack(fill="both", expand=True, pady=(0, 10))
            
            text_area = tk.Text(editor_frame, height=8, font=("Consolas", 11), bg="#2d3748", fg="#f7fafc", 
                                insertbackground="white", padx=10, pady=10, relief="flat")
            text_area.pack(fill="both", expand=True)
            
            # 기본 템플릿 코드 삽입
            text_area.insert(tk.END, "# 여기에 코드를 입력하세요\n")
            
            # 실행 결과 화면
            console_frame = tk.Frame(content_frame, bg="#1a202c", bd=1, relief="solid")
            console_lbl = tk.Label(console_frame, text="[실행 콘솔 출력 결과]", font=("Consolas", 10), fg="#a0aec0", bg="#1a202c", justify="left", anchor="nw")
            console_lbl.pack(fill="both", expand=True, padx=10, pady=8)
            
            def run_code():
                user_code = text_area.get("1.0", tk.END).strip()
                if not user_code or user_code == "# 여기에 코드를 입력하세요":
                    messagebox.showwarning("경고", "코드를 입력하세요.")
                    return
                
                temp_file = None
                stdout_str = ""
                is_correct = False
                ai_feedback = ""
                run_success = False
                try:
                    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as f:
                        f.write(user_code)
                        temp_file = f.name
                    
                    # 2초 타임아웃
                    result = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=2.0)
                    
                    # 콘솔 프레임 노출
                    console_frame.pack(fill="x", pady=(0, 10))
                    
                    if result.returncode == 0:
                        is_correct = True
                        run_success = True
                        stdout_str = result.stdout.strip()
                        console_lbl.config(text=f"▶ 실행 결과 (성공):\n{stdout_str}", fg="#48bb78")
                        
                        # AI 피드백 시뮬레이션
                        fb_frame.pack(fill="x", pady=10)
                        ai_feedback = "정답입니다. 코드 실행 결과가 정상적으로 도출되었으며 문법 오류가 없습니다."
                        fb_lbl.config(text=f"✓ 채점 완료: {ai_feedback}", fg=COLOR_SUCCESS, font=("Malgun Gothic", 11, "bold"))
                    else:
                        is_correct = False
                        stderr_str = result.stderr.strip()
                        console_lbl.config(text=f"▶ 실행 결과 (에러):\n{stderr_str}", fg="#f56565")
                        
                        fb_frame.pack(fill="x", pady=10)
                        ai_feedback = "문법 오류 또는 런타임 에러가 발생했습니다. 에러 로그를 확인하고 수정해보세요."
                        fb_lbl.config(text=f"✗ 채점 실패: {ai_feedback}", fg=COLOR_ERROR, font=("Malgun Gothic", 11))
                        
                except subprocess.TimeoutExpired:
                    is_correct = False
                    console_frame.pack(fill="x", pady=(0, 10))
                    console_lbl.config(text="▶ 실행 결과: [Timeout] 무한 루프가 발생하여 2초 후 중단되었습니다.", fg="#f56565")
                    fb_frame.pack(fill="x", pady=10)
                    ai_feedback = "실행 시간 제한을 초과했습니다. 무한루프 탈출 조건이 확실한지 점검하세요."
                    fb_lbl.config(text=f"✗ 채점 실패: {ai_feedback}", fg=COLOR_ERROR)
                except Exception as e:
                    is_correct = False
                    console_frame.pack(fill="x", pady=(0, 10))
                    console_lbl.config(text=f"▶ 시스템 에러: {e}", fg="#f56565")
                    ai_feedback = f"에러가 발생했습니다: {e}"
                finally:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                            
                # 상태 기록 저장
                # 동일한 문제를 다시 실행할 때 결과를 덮어씌우기 위해 이전에 저장된 결과를 제거
                if len(self.session_results) > self.current_q_index:
                    self.session_results.pop(self.current_q_index)
                
                self.session_results.insert(self.current_q_index, {
                    "question": q_data.get("question"),
                    "type": "subjective",
                    "user_code": user_code,
                    "stdout": stdout_str if run_success else "",
                    "is_correct": is_correct,
                    "applied_feedback": ai_feedback
                })
                
                # 실행 성공인 경우 비활성화하고 '다음 문제' 잠금 해제
                if is_correct:
                    text_area.config(state="disabled")
                    btn_run.config(state="disabled")
                    btn_next.config(state="normal")
                else:
                    # 실행 실패하더라도 일단 다음으로 넘어가고 싶으면 잠금해제는 안 되며, 코드를 수정하여 정답을 맞추거나
                    # 유저의 선택을 위해 '다음 문제' 버튼을 조건부 활성화시킬 수도 있으나, 여기서는 맞을 때까지 반복하게 하거나
                    # 다음으로 그냥 넘어갈 수 있도록 버튼을 항시 노출하게 구현 (유저 편의성)
                    btn_next.config(state="normal")
            
            btn_run = create_flat_button(content_frame, "💻 코드 실행 및 채점하기", "#4a5568", "#ffffff", "#2d3748", 
                                        run_code, font=("Malgun Gothic", 10, "bold"))
            btn_run.pack(anchor="e", pady=(0, 10))

    def next_learning_question(self):
        self.current_q_index += 1
        self.show_learning_question()

    # ------------------------------------------
    # 4-3. 시험 모드 관련 화면 (스크롤 카드 10문항)
    # ------------------------------------------
    
    def start_test_mode(self):
        """시험 모드 시작: 10문항 구성"""
        self.current_mode = "test"
        self.session_results = []
        self.test_temp_answers = {}
        
        # 10문항 무작위 혼합 구성 (객관식 5개, 주관식 5개)
        obj_pool = [q for q in self.quiz_data if q.get("type") == "objective"]
        sub_pool = [q for q in self.quiz_data if q.get("type") == "subjective"]
        
        random.shuffle(obj_pool)
        random.shuffle(sub_pool)
        
        selected_obj = obj_pool[:5]
        selected_sub = sub_pool[:5]
        
        self.current_session_quizzes = selected_obj + selected_sub
        random.shuffle(self.current_session_quizzes) # 순서 뒤섞기
        
        # 10문제가 부족하면 전체 다 가져오기
        if len(self.current_session_quizzes) < 10:
            self.current_session_quizzes = self.quiz_data[:10]
            
        # 임시 저장용 딕셔너리 초기화
        for q in self.current_session_quizzes:
            self.test_temp_answers[q["id"]] = {
                "objective_ans": None,
                "subjective_code": "",
                "saved": False
            }
            
        self.show_test_paper()

    def show_test_paper(self):
        """시험 모드: 스크롤 형태로 10문제 배치"""
        self.init_container()
        
        # 헤더
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="📝 시험 모드 (총 10문항 혼합)", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 스크롤 가능한 본문 영역 생성
        scroll_container = ScrollableFrame(self.main_container)
        scroll_container.pack(expand=True, fill="both")
        
        sf = scroll_container.scrollable_frame
        
        # 상단 안내 문구
        lbl_info = tk.Label(sf, text="각 문제를 풀고 우측 하단의 [임시 저장] 버튼을 눌러 답안을 저장하세요. 모두 작성 후 하단의 [최종 제출]을 누르면 채점이 시작됩니다.",
                            font=("Malgun Gothic", 10, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG, justify="left", pady=10)
        lbl_info.pack(fill="x", padx=30, pady=(15, 5))
        
        # 문제 카드들 렌더링
        question_cards = {}
        for idx, q_data in enumerate(self.current_session_quizzes):
            q_id = q_data["id"]
            q_type = q_data.get("type")
            
            # 카드 박스
            card = tk.Frame(sf, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
            card.pack(fill="x", padx=30, pady=10)
            
            pad_frame = tk.Frame(card, bg=COLOR_CARD, padx=20, pady=15)
            pad_frame.pack(fill="x")
            
            # 문제 타이틀
            lbl_title = tk.Label(pad_frame, text=f"문제 {idx + 1}. ({'객관식' if q_type == 'objective' else '주관식'})", 
                                 font=("Malgun Gothic", 11, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
            lbl_title.pack(anchor="w", pady=(0, 5))
            
            lbl_question = tk.Label(pad_frame, text=q_data["question"], font=("Malgun Gothic", 12, "bold"), fg=COLOR_DARK, bg=COLOR_CARD, justify="left", anchor="w", wraplength=780)
            lbl_question.pack(anchor="w", fill="x", pady=(0, 10))
            
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
                editor_frame.pack(fill="x", pady=5)
                
                txt_area = tk.Text(editor_frame, height=5, font=("Consolas", 10), bg="#2d3748", fg="#f7fafc", 
                                   insertbackground="white", padx=8, pady=8, relief="flat")
                txt_area.pack(fill="x")
                
                # 기존 임시 저장된 코드 복구
                if self.test_temp_answers[q_id]["subjective_code"]:
                    txt_area.insert(tk.END, self.test_temp_answers[q_id]["subjective_code"])
                    status_lbl.config(text="임시 저장됨 ✓", fg=COLOR_SUCCESS)
                else:
                    txt_area.insert(tk.END, "# 코드를 작성하세요\n")
                    
                # 주관식용 저장 람다
                def make_save_sub(qid=q_id, ta=txt_area, sl=status_lbl):
                    code = ta.get("1.0", tk.END).strip()
                    if not code or code == "# 코드를 작성하세요":
                        messagebox.showwarning("주의", "코드를 작성한 후 저장해주세요.")
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

    def submit_test_paper(self):
        """시험 최종 제출 처리 및 로딩 오버레이 채점 진행바 구동"""
        # 저장되지 않은 문항 체크
        unsaved = [i+1 for i, q in enumerate(self.current_session_quizzes) if not self.test_temp_answers[q["id"]]["saved"]]
        if unsaved:
            msg = f"아직 임시 저장하지 않은 문항이 있습니다: {unsaved}번\n그래도 최종 제출하시겠습니까?"
            if not messagebox.askyesno("미저장 문항 존재", msg):
                return
        else:
            if not messagebox.askyesno("최종 제출", "정말로 최종 제출하시겠습니까?\n제출 후에는 답안을 수정할 수 없습니다."):
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
                        with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as f:
                            f.write(user_code)
                            temp_file = f.name
                        # 2초 제한
                        res = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=2.0)
                        stdout = res.stdout.strip()
                        if res.returncode == 0:
                            is_correct = True
                            applied_feedback = "정답입니다! 코드가 문법 에러 없이 정상적으로 수행되었습니다."
                        else:
                            is_correct = False
                            applied_feedback = f"실행 오류:\n{res.stderr.strip()}"
                    except subprocess.TimeoutExpired:
                        is_correct = False
                        applied_feedback = "시간 초과: 무한 루프 가능성 감지"
                    except Exception as e:
                        is_correct = False
                        applied_feedback = f"시스템 에러: {e}"
                    finally:
                        if temp_file and os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                            except:
                                pass
                else:
                    is_correct = False
                    applied_feedback = "제출된 코드가 없습니다."
            
            results.append({
                "id": q_id,
                "type": q_type,
                "question": q_data["question"],
                "options": q_data.get("options", []),
                "key": q_data.get("key", None),
                "wrong_feedbacks": q_data.get("wrong_feedbacks", []),
                "hint": q_data.get("hint", ""),
                "user_input": user_input,
                "is_correct": is_correct,
                "stdout": stdout,
                "applied_feedback": applied_feedback
            })
            
            # 다음 문항 채점 실행 (시각적 채점 바 체감을 위해 200ms 지연)
            self.after(200, lambda: grade_step(idx + 1))
            
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
                    "hint": r["hint"]
                } for r in results
            ],
            "user_results": [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "user_input": r["user_input"],
                    "is_correct": r["is_correct"],
                    "stdout": r["stdout"],
                    "applied_feedback": r["applied_feedback"]
                } for r in results
            ]
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
            lbl_question = tk.Label(pad_frame, text=res["question"], font=("Malgun Gothic", 11, "bold"), fg=COLOR_DARK, bg=card_bg, justify="left", anchor="w", wraplength=780)
            lbl_question.pack(anchor="w", fill="x", pady=(0, 10))
            
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
        
        header = tk.Frame(self.main_container, bg=COLOR_DARK)
        header.pack(fill="x")
        tk.Label(header, text="🗂️ 기록실 - 풀이 기록 보관소", font=("Malgun Gothic", 16, "bold"), fg="#ffffff", bg=COLOR_DARK).pack()
        
        # 바디 구성 (좌측: 파일 리스트, 우측: 선택 기록 상세 요약 및 제어 버튼)
        body = tk.Frame(self.main_container, bg=COLOR_BG)
        body.pack(expand=True, fill="both", padx=30, pady=20)
        
        # 좌측 영역
        left_frame = tk.Frame(body, bg=COLOR_BG)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 15))
        
        tk.Label(left_frame, text="풀이 기록 목록 (최신순)", font=("Malgun Gothic", 11, "bold"), fg=COLOR_DARK, bg=COLOR_BG).pack(anchor="w", pady=(0, 5))
        
        listbox_frame = tk.Frame(left_frame, bg=COLOR_CARD, bd=1, relief="solid")
        listbox_frame.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side="right", fill="y")
        
        listbox = tk.Listbox(listbox_frame, font=("Malgun Gothic", 10), yscrollcommand=scrollbar.set, relief="flat")
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        # 우측 상세 정보 프레임
        right_frame = tk.Frame(body, width=350, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0, highlightbackground=COLOR_BORDER)
        right_frame.pack(side="right", fill="both", padx=(15, 0))
        right_frame.pack_propagate(False)
        
        # 패딩 설정
        right_pad = tk.Frame(right_frame, bg=COLOR_CARD, padx=20, pady=20)
        right_pad.pack(fill="both", expand=True)
        
        tk.Label(right_pad, text="🔎 기록 상세 요약", font=("Malgun Gothic", 13, "bold"), fg=COLOR_DARK, bg=COLOR_CARD).pack(anchor="w", pady=(0, 15))
        
        # 메타데이터 표기 위젯들
        lbl_m_mode = tk.Label(right_pad, text="학습 모드: -", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=COLOR_CARD)
        lbl_m_mode.pack(anchor="w", pady=4)
        
        lbl_m_date = tk.Label(right_pad, text="일시: -", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=COLOR_CARD)
        lbl_m_date.pack(anchor="w", pady=4)
        
        lbl_m_score = tk.Label(right_pad, text="성적: -", font=("Malgun Gothic", 10), fg=COLOR_DARK, bg=COLOR_CARD)
        lbl_m_score.pack(anchor="w", pady=4)
        
        # 제어용 컨트롤 패널
        ctrl_frame = tk.Frame(right_pad, bg=COLOR_CARD)
        ctrl_frame.pack(fill="x", side="bottom", pady=10)
        
        btn_view = create_flat_button(ctrl_frame, "👁️ 기록 상세보기", COLOR_PRIMARY, "#ffffff", COLOR_PRIMARY_HOVER, 
                                     None, font=("Malgun Gothic", 10, "bold"))
        btn_view.pack(fill="x", pady=5)
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
                    user_ans = res["user_input"]
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
                    code_text.insert(tk.END, res["user_input"])
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
                        "hint": r.get("hint", "")
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
                    "hint": q.get("hint", "")
                } for idx, q in enumerate(self.current_session_quizzes)
            ],
            "user_results": [
                {
                    "id": q.get("id", idx),
                    "type": r.get("type", "objective"),
                    "user_input": r.get("user_answer") if r.get("type") == "objective" else r.get("user_code", ""),
                    "is_correct": r.get("is_correct", False),
                    "stdout": r.get("stdout", ""),
                    "applied_feedback": r.get("applied_feedback", "")
                } for idx, (q, r) in enumerate(zip(self.current_session_quizzes, self.session_results))
            ]
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
