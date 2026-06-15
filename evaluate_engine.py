import sys
import io

def evaluate_subjective_answer(user_code: str, expected_output: str) -> dict:
    """
    [3장 핵심 함수] 주관식 코딩 문항에 대한 로컬 런타임 인터프리터 자동 채점 루프
    - user_code: 학습자가 GUI 입력창에 타이핑한 파이썬 소스코드
    - expected_output: 문제 출제 시 지정된 정확한 표준 출력(stdout) 정답 정제 텍스트
    """
    # 1단계: 표준 출력을 가로채기 위한 가상 버퍼 설정
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    
    result = {"is_correct": False, "error_message": "", "feedback": ""}
    
    try:
        # 2단계: 학습자가 제출한 코드를 로컬 런타임 환경에서 실제 실행 (Compile & Run)
        # exec() 환경을 안전한 격리 공간(로컬 샌드박스 내부)으로 실행 유도
        exec(user_code, {}, {})
        
        # 실제 실행되어 출력된 텍스트값 추출
        actual_output = redirected_output.getvalue().strip()
        
        # 3단계: 표준 출력값 100% 매칭 검사 (AI의 채점 오심/환각 원천 차단)
        if actual_output == expected_output.strip():
            result["is_correct"] = True
        else:
            result["error_message"] = f"출력값 불일치 (기대값: {expected_output}, 실제값: {actual_output})"
            
    except Exception as e:
        # 구문 에러(SyntaxError)나 실행 에러 발생 시 에러 로그 포착
        result["is_correct"] = False
        result["error_message"] = f"런타임 에러 발생: {str(e)}"
        
    finally:
        # 가로챘던 표준 출력을 원래대로 복구
        sys.stdout = old_stdout
        
    return result