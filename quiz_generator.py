def generate_learning_quiz(mode: str, type_desc: str = None) -> dict:
    """
    [2장 핵심 함수] 개념 집중 학습(concept) 및 유형별 선택 학습(learning) 문제 생성
    - mode: 'concept' (5문항 객관식) 또는 'learning' (10문항 객관식/주관식 결합)
    - type_desc: 학습자가 선택한 파이썬 문법 유형 (예: '반복문', '조건문')
    """
    # 1. prompts.json 파일이나 딕셔너리에서 베이스 프롬프트 템플릿 로드
    base_prompt = load_prompt_template(mode)
    
    # 2. 파라미터 동적 매칭 (Context Scope Isolation 적용)
    if mode == "learning" and type_desc:
        # 사용자가 선택한 특정 문법 유형으로 프롬프트를 좁혀 환각 현상 방지
        final_prompt = base_prompt.format(type_description=type_desc)
    else:
        final_prompt = base_prompt

    # 3. 인공지능(LLM)에 통신을 요청하고 정형 JSON 데이터 반환 받기
    # 규격화 장치를 통해 런타임 에러 없이 무결점으로 데이터를 파싱함
    quiz_data = call_llm_and_parse_json(final_prompt)
    
    return quiz_data