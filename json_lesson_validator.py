import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional
import time

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LESSONS_DIR = "generated_lessons_json"
VALIDATED_LESSONS_DIR = "validated_lessons_json"

# API 키 유효성 검사
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어야 합니다.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# 출력 디렉토리 생성
os.makedirs(VALIDATED_LESSONS_DIR, exist_ok=True)

# --- 2. 검증 모델들 ---
VALIDATION_MODELS = [
    "gpt-4o-mini",      # 빠르고 효율적인 검증
    "gpt-4o",           # 고품질 검증
    "gpt-3.5-turbo"     # 백업 검증
]

# --- 3. JSON 구조 검증 함수 ---
def validate_json_structure(lesson_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    JSON 구조의 기본적인 유효성을 검증하고 수정합니다.
    """
    validated_data = {
        "title": lesson_data.get("title", "Unknown Title"),
        "level": lesson_data.get("level", "초급"),
        "core_concepts": lesson_data.get("core_concepts", ""),
        "code_examples": [],
        "quizzes": []
    }
    
    # code_examples 검증 및 수정
    code_examples = lesson_data.get("code_examples", [])
    if isinstance(code_examples, str):
        # 문자열인 경우 배열로 변환
        validated_data["code_examples"] = [
            {
                "description": "코드 예시",
                "code": code_examples
            }
        ]
    elif isinstance(code_examples, list):
        # 배열인 경우 각 항목 검증
        for example in code_examples:
            if isinstance(example, dict):
                validated_example = {
                    "description": example.get("description", "코드 예시"),
                    "code": example.get("code", "```javascript\n// 코드 예시\n```")
                }
                validated_data["code_examples"].append(validated_example)
            else:
                # 객체가 아닌 경우 문자열로 변환
                validated_data["code_examples"].append({
                    "description": "코드 예시",
                    "code": f"```javascript\n{str(example)}\n```"
                })
    else:
        # 기본값 설정
        validated_data["code_examples"] = [
            {
                "description": "코드 예시",
                "code": "```javascript\n// 코드 예시\nfunction Example() {\n  return <div>Hello World</div>;\n}\n```"
            }
        ]
    
    # quizzes 검증 및 수정
    quizzes = lesson_data.get("quizzes", [])
    if isinstance(quizzes, list):
        for quiz in quizzes:
            if isinstance(quiz, dict):
                validated_quiz = {
                    "question": quiz.get("question", "기본 문제"),
                    "answer": quiz.get("answer", "기본 정답")
                }
                validated_data["quizzes"].append(validated_quiz)
    else:
        # 기본 퀴즈 추가
        validated_data["quizzes"] = [
            {
                "question": "기본 문제",
                "answer": "기본 정답"
            }
        ]
    
    return validated_data

# --- 4. OpenAI 모델을 통한 검증 ---
def validate_with_openai_model(lesson_data: Dict[str, Any], model: str) -> Dict[str, Any]:
    """
    특정 OpenAI 모델을 사용하여 학습 자료를 검증하고 개선합니다.
    """
    system_prompt = f"""
    You are a professional React instructor and content validator. Your task is to validate and improve the provided learning material.
    
    The material should be in Korean and follow this structure:
    {{
        "title": "제목",
        "level": "레벨 (초급/중급/고급)",
        "core_concepts": "핵심 개념 설명 (한국어)",
        "code_examples": [
            {{
                "description": "코드 예시 설명 (한국어)",
                "code": "```javascript\\n실제 JavaScript/JSX 코드\\n```"
            }}
        ],
        "quizzes": [
            {{
                "question": "퀴즈 문제 (한국어)",
                "answer": "퀴즈 정답과 설명 (한국어)"
            }}
        ]
    }}
    
    Validation criteria:
    1. All content must be in Korean
    2. Code examples must be valid JavaScript/JSX with proper syntax
    3. Core concepts should be clear and educational
    4. Quizzes should be relevant and have detailed answers
    5. Return only valid JSON
    """
    
    user_prompt = f"""
    Please validate and improve the following React learning material:
    
    {json.dumps(lesson_data, ensure_ascii=False, indent=2)}
    
    If there are any issues, fix them and return the improved version.
    If the material is already good, return it as is.
    """
    
    try:
        print(f"--- {model}로 검증 중: {lesson_data.get('title', 'Unknown')} ---")
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # 일관성 있는 결과를 위해 낮은 temperature
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        
        if content:
            # JSON 추출 및 파싱
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    validated_data = json.loads(json_match.group())
                    print(f"--- {model} 검증 완료 ---")
                    return validated_data
                except json.JSONDecodeError:
                    print(f"--- {model} JSON 파싱 실패, 원본 데이터 사용 ---")
                    return lesson_data
            else:
                print(f"--- {model} JSON 추출 실패, 원본 데이터 사용 ---")
                return lesson_data
        else:
            print(f"--- {model} 응답 없음, 원본 데이터 사용 ---")
            return lesson_data
            
    except Exception as e:
        print(f"--- {model} 검증 중 오류 발생: {e} ---")
        return lesson_data

# --- 5. 다중 모델 검증 ---
def validate_with_multiple_models(lesson_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    여러 OpenAI 모델을 순차적으로 사용하여 학습 자료를 검증합니다.
    """
    # 기본 구조 검증
    validated_data = validate_json_structure(lesson_data)
    
    # 각 모델로 순차 검증
    for model in VALIDATION_MODELS:
        try:
            validated_data = validate_with_openai_model(validated_data, model)
            time.sleep(1)  # API 호출 간격 조절
        except Exception as e:
            print(f"--- {model} 검증 실패: {e} ---")
            continue
    
    return validated_data

# --- 6. 파일 처리 함수들 ---
def load_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    JSON 파일을 로드합니다.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"파일 로드 실패 {filepath}: {e}")
        return None

def save_json_file(data: Dict[str, Any], filepath: str):
    """
    JSON 파일을 저장합니다.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"--- 파일 저장 완료: {filepath} ---")
    except Exception as e:
        print(f"파일 저장 실패 {filepath}: {e}")

def process_all_lessons():
    """
    모든 학습 자료를 검증하고 개선합니다.
    """
    print("=== 학습 자료 검증 및 개선 시작 ===")
    
    if not os.path.exists(LESSONS_DIR):
        print(f"--- {LESSONS_DIR} 디렉토리가 존재하지 않습니다. ---")
        return
    
    # 기존 검증된 파일들 삭제
    if os.path.exists(VALIDATED_LESSONS_DIR):
        for filename in os.listdir(VALIDATED_LESSONS_DIR):
            file_path = os.path.join(VALIDATED_LESSONS_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"--- 기존 파일 삭제: {filename} ---")
    
    # 모든 JSON 파일 처리
    json_files = [f for f in os.listdir(LESSONS_DIR) if f.endswith('.json')]
    total_files = len(json_files)
    
    print(f"--- 총 {total_files}개의 파일을 검증합니다 ---")
    
    for i, filename in enumerate(json_files, 1):
        print(f"\n--- {i}/{total_files}: {filename} 처리 중 ---")
        
        # 원본 파일 로드
        original_filepath = os.path.join(LESSONS_DIR, filename)
        lesson_data = load_json_file(original_filepath)
        
        if lesson_data:
            # 다중 모델 검증
            validated_data = validate_with_multiple_models(lesson_data)
            
            # 검증된 파일 저장
            validated_filepath = os.path.join(VALIDATED_LESSONS_DIR, filename)
            save_json_file(validated_data, validated_filepath)
        else:
            print(f"--- {filename} 로드 실패, 건너뜀 ---")
    
    # 검증된 파일들의 인덱스 생성
    create_validated_index()
    
    print("\n=== 학습 자료 검증 및 개선 완료 ===")

def create_validated_index():
    """
    검증된 파일들의 인덱스를 생성합니다.
    """
    print("--- 검증된 파일 인덱스 생성 중 ---")
    
    index_data = {}
    
    for filename in os.listdir(VALIDATED_LESSONS_DIR):
        if filename.endswith('.json') and filename != 'index.json':
            filepath = os.path.join(VALIDATED_LESSONS_DIR, filename)
            lesson_data = load_json_file(filepath)
            
            if lesson_data:
                level = lesson_data.get('level', '초급')
                title = lesson_data.get('title', 'Unknown')
                
                if level not in index_data:
                    index_data[level] = []
                
                # 파일 번호 추출 (예: 초급_01_Your-First-Component.json -> 1)
                number_match = re.search(r'_(\d+)_', filename)
                number = int(number_match.group(1)) if number_match else len(index_data[level]) + 1
                
                index_data[level].append({
                    "title": title,
                    "filename": filename,
                    "number": number
                })
    
    # 각 레벨별로 번호 순 정렬
    for level in index_data:
        index_data[level].sort(key=lambda x: x['number'])
    
    # 인덱스 파일 저장
    index_filepath = os.path.join(VALIDATED_LESSONS_DIR, 'index.json')
    save_json_file(index_data, index_filepath)
    
    print("--- 검증된 파일 인덱스 생성 완료 ---")

# --- 7. 메인 실행 함수 ---
if __name__ == "__main__":
    process_all_lessons() 