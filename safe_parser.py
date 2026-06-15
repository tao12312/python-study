import json
import re

def safe_parse_llm_json(raw_response: str) -> dict:
    """
    [4.1장 핵심] LLM 응답에서 순수 JSON 데이터만 추출하여 파싱하는 무결점 함수
    - raw_response: AI가 반환한 날것의 텍스트 데이터
    """
    try:
        # 1. 혹시 포함되어 있을지 모르는 마크다운 코드 블록(```json) 제거 정규식
        clean_text = re.sub(r'```json\s*|
```', '', raw_response).strip()
        
        # 2. JSON의 시작('{')과 끝('}') 위치를 찾아 그 안의 데이터만 슬라이싱
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx != 0:
            clean_text = clean_text[start_idx:end_idx]
            
        # 3. 규격화된 정형 데이터로 최종 파싱
        return json.loads(clean_text)
        
    except (json.JSONDecodeError, ValueError) as e:
        # 파싱 실패 시 앱이 다운되지 않도록 기본 구조(Fallback) 반환
        print(f"JSON 파싱 예외 발생 처리: {e}")
        return {"error": "데이터 규격 파싱 실패", "questions": []}