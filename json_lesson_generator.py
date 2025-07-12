import os
import json
from openai import OpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import re

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COLLECTION_NAME = "react-docs-complete"
MODEL_NAME = 'distiluse-base-multilingual-cased-v1'
OUTPUT_DIR = "generated_lessons_json"

# API 키 유효성 검사
if not all([QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY]):
    raise ValueError("필수 환경 변수(QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY)가 .env 파일에 모두 설정되어야 합니다.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# 출력 디렉토리 생성
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 2. 모델 및 클라이언트 초기화 ---
print("임베딩 모델 로딩 중...")
model = SentenceTransformer(MODEL_NAME)
print("Qdrant Cloud에 연결 중...")
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
print("초기화 완료.")

# --- 3. LLM 호출 (OpenAI API 연동) ---
def generate_lesson_with_llm(level: str, query: str, context: str) -> dict:
    """
    검색된 컨텍스트와 사용자의 질문을 바탕으로 OpenAI API를 호출하여 학습 자료를 생성합니다.
    """
    system_prompt = """
    You are a professional instructor who teaches React. Your role is to create learning materials based on the reference documents provided. 
    The output must be in Korean and structured as JSON with the following format:
    {
        "title": "제목",
        "level": "레벨",
        "core_concepts": "핵심 개념 설명",
        "code_examples": [
            {
                "description": "코드 예시 설명",
                "code": "```javascript\n실제 JavaScript/JSX 코드\n```"
            }
        ],
        "quizzes": [
            {
                "question": "문제",
                "answer": "정답"
            }
        ]
    }
    
    IMPORTANT: 
    - code_examples must be an array of objects with description and code properties
    - Each code example should include actual JavaScript/JSX code with proper syntax highlighting
    - Each quiz should have a clear question and detailed answer
    - All content should be in Korean
    """
    
    user_prompt = f"""
    Based on the "Reference Documents" below, create learning materials that match the following request.

    **Request Details:**
    - Learning Level: {level}
    - Topic: {query}
    - Additional Request: Please include core concepts, code examples with actual JavaScript/JSX code, and three simple review quizzes with their answers and explanations related to the topic.

    ---
    **Reference Documents:**
    {context}
    ---

    **Output Format (JSON):**
    {{
        "title": "{query}",
        "level": "{level}",
        "core_concepts": "핵심 개념에 대한 명확하고 이해하기 쉬운 설명",
        "code_examples": [
            {{
                "description": "첫 번째 코드 예시 설명",
                "code": "```javascript\n실제 JavaScript/JSX 코드\n```"
            }},
            {{
                "description": "두 번째 코드 예시 설명",
                "code": "```javascript\n실제 JavaScript/JSX 코드\n```"
            }}
        ],
        "quizzes": [
            {{
                "question": "첫 번째 퀴즈 문제",
                "answer": "첫 번째 퀴즈 정답과 설명"
            }},
            {{
                "question": "두 번째 퀴즈 문제", 
                "answer": "두 번째 퀴즈 정답과 설명"
            }},
            {{
                "question": "세 번째 퀴즈 문제",
                "answer": "세 번째 퀴즈 정답과 설명"
            }}
        ]
    }}
    
    IMPORTANT: 
    - code_examples must be an array of objects with description and code properties
    - Each code example should include actual JavaScript/JSX code with proper syntax highlighting
    - All text should be in Korean
    - Return only valid JSON
    """
    
    try:
        print(f"--- OpenAI API에 '{query}' 주제 프롬프트 전송 중 ---")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        print(f"--- '{query}' 주제 응답 수신 완료 ---")
        content = response.choices[0].message.content
        
        if content:
            # JSON 파싱 시도
            try:
                # JSON 부분만 추출
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    lesson_data = json.loads(json_match.group())
                    
                    # 코드 예시가 비어있거나 올바르지 않은 경우 기본값 설정
                    if not lesson_data.get('code_examples'):
                        lesson_data['code_examples'] = [
                            {
                                "description": f"{query} 관련 코드 예시",
                                "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                            }
                        ]
                    elif isinstance(lesson_data['code_examples'], str):
                        # 문자열인 경우 배열로 변환
                        lesson_data['code_examples'] = [
                            {
                                "description": f"{query} 관련 코드 예시",
                                "code": lesson_data['code_examples']
                            }
                        ]
                    elif isinstance(lesson_data['code_examples'], dict):
                        # 객체인 경우 배열로 변환
                        code_examples = []
                        for key, value in lesson_data['code_examples'].items():
                            title = key.replace('_', ' ').title()
                            
                            if isinstance(value, str):
                                code_content = value
                            elif isinstance(value, list):
                                code_content = '\n'.join(value)
                            elif isinstance(value, dict):
                                # 중첩된 객체 처리
                                if 'code' in value and isinstance(value['code'], list):
                                    code_content = '\n'.join(value['code'])
                                    if 'explanation' in value:
                                        code_content = f"{value['explanation']}\n\n{code_content}"
                                elif 'explanation' in value:
                                    code_content = value['explanation']
                                    if 'code' in value and isinstance(value['code'], list):
                                        code_content += f"\n\n{chr(10).join(value['code'])}"
                                else:
                                    code_content = str(value)
                            else:
                                code_content = str(value)
                            
                            code_examples.append({
                                "description": title,
                                "code": f"```javascript\n{code_content}\n```"
                            })
                        lesson_data['code_examples'] = code_examples
                    elif not isinstance(lesson_data['code_examples'], list):
                        # 배열이 아닌 경우 기본값 설정
                        lesson_data['code_examples'] = [
                            {
                                "description": f"{query} 관련 코드 예시",
                                "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                            }
                        ]
                    
                    # 퀴즈가 비어있는 경우 기본 퀴즈 추가
                    if not lesson_data.get('quizzes') or len(lesson_data['quizzes']) == 0:
                        lesson_data['quizzes'] = [
                            {
                                "question": f"{query}에 대한 기본 문제",
                                "answer": f"{query}에 대한 기본 정답"
                            }
                        ]
                    
                    return lesson_data
                else:
                    # JSON이 아닌 경우 기본 구조로 변환
                    return {
                        "title": query,
                        "level": level,
                        "core_concepts": content,
                        "code_examples": [
                            {
                                "description": f"{query} 관련 코드 예시",
                                "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                            }
                        ],
                        "quizzes": [
                            {
                                "question": f"{query}에 대한 기본 문제",
                                "answer": f"{query}에 대한 기본 정답"
                            }
                        ]
                    }
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 기본 구조로 변환
                return {
                    "title": query,
                    "level": level,
                    "core_concepts": content,
                    "code_examples": [
                        {
                            "description": f"{query} 관련 코드 예시",
                            "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                        }
                    ],
                    "quizzes": [
                        {
                            "question": f"{query}에 대한 기본 문제",
                            "answer": f"{query}에 대한 기본 정답"
                        }
                    ]
                }
        else:
            return {
                "title": query,
                "level": level,
                "core_concepts": f"'{query}' 학습 자료 생성 실패\n응답 내용이 비어있습니다.",
                "code_examples": [
                    {
                        "description": f"{query} 관련 코드 예시",
                        "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                    }
                ],
                "quizzes": [
                    {
                        "question": f"{query}에 대한 기본 문제",
                        "answer": f"{query}에 대한 기본 정답"
                    }
                ]
            }
    except Exception as e:
        print(f"OpenAI API 호출 중 오류 발생: {e}")
        return {
            "title": query,
            "level": level,
            "core_concepts": f"'{query}' 학습 자료 생성 실패\nAPI 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "code_examples": [
                {
                    "description": f"{query} 관련 코드 예시",
                    "code": f"```javascript\n// {query} 관련 코드 예시\nfunction Example() {{\n  return (\n    <div>\n      <h1>예시 컴포넌트</h1>\n    </div>\n  );\n}}\n```"
                }
            ],
            "quizzes": [
                {
                    "question": f"{query}에 대한 기본 문제",
                    "answer": f"{query}에 대한 기본 정답"
                }
            ]
        }

# --- 4. 메인 생성 함수 ---
def generate_all_lessons():
    """
    모든 레벨의 학습 자료를 JSON 형태로 생성합니다.
    """
    # 기존 파일들 삭제
    print("--- 기존 파일들 삭제 중 ---")
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"--- {filename} 삭제 완료 ---")
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("--- 기존 파일 삭제 완료 ---")
    
    level_mapping = {
        "초급": ["1단계: 사전 준비 ⚙️", "2단계: 메인 학습 코스 (초급) 入门"],
        "중급": ["3단계: 메인 학습 코스 (중급) 🚀"],
        "고급": ["4단계: 심화 탐구 🧠"]
    }
    
    # 모든 문서를 조회
    print("--- Qdrant에서 모든 문서 조회 중 ---")
    scrolled_points, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        limit=1000,
        with_payload=True
    )
    print(f"--- 총 {len(scrolled_points)}개의 문서 조각을 찾았습니다 ---")
    
    # 레벨별로 처리
    for level, target_sub_categories in level_mapping.items():
        print(f"\n=== {level} 레벨 학습 자료 생성 시작 ===")
        
        # 해당 레벨의 문서 필터링
        lessons_by_title = {}
        for point in scrolled_points:
            payload = point.payload
            sub_category = payload.get('sub_category')
            title = payload.get('title')
            
            if sub_category in target_sub_categories and title:
                if title not in lessons_by_title:
                    lessons_by_title[title] = []
                lessons_by_title[title].append(payload.get('text', ''))
        
        print(f"--- {level} 레벨에서 {len(lessons_by_title)}개의 토픽 발견 ---")
        
        # 각 토픽별로 학습 자료 생성
        for i, (title, texts) in enumerate(lessons_by_title.items(), 1):
            print(f"--- {i}/{len(lessons_by_title)}: {title} 생성 중 ---")
            
            context = "\n\n---\n\n".join(texts)
            lesson_data = generate_lesson_with_llm(level, title, context)
            
            # 파일명 생성 (안전한 파일명으로 변환)
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            filename = f"{level}_{i:02d}_{safe_title}.json"
            
            # JSON 파일 저장
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(lesson_data, f, ensure_ascii=False, indent=2)
            
            print(f"--- {filename} 저장 완료 ---")
        
        print(f"=== {level} 레벨 학습 자료 생성 완료 ===\n")
    
    # 인덱스 파일 생성
    create_index_file()
    print("�� 모든 학습 자료 생성 완료!")

def create_index_file():
    """
    생성된 파일들의 인덱스를 생성합니다.
    """
    index_data = {}
    
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith('.json'):
            # 파일명에서 레벨과 제목 추출
            parts = filename.replace('.json', '').split('_', 2)
            if len(parts) >= 3:
                level = parts[0]
                number = parts[1]
                title = parts[2].replace('-', ' ')
                
                if level not in index_data:
                    index_data[level] = []
                
                index_data[level].append({
                    'filename': filename,
                    'title': title,
                    'number': int(number)
                })
    
    # 번호순으로 정렬
    for level in index_data:
        index_data[level].sort(key=lambda x: x['number'])
    
    # JSON 파일로 저장
    index_filepath = os.path.join(OUTPUT_DIR, 'index.json')
    with open(index_filepath, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"--- 인덱스 파일 생성 완료: {index_filepath} ---")

if __name__ == "__main__":
    generate_all_lessons() 