import os
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # OpenAI API 키 로드
COLLECTION_NAME = "react-docs-complete"
MODEL_NAME = 'distiluse-base-multilingual-cased-v1'

# API 키 유효성 검사
if not all([QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY]):
    raise ValueError("필수 환경 변수(QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY)가 .env 파일에 모두 설정되어야 합니다.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# --- 2. 모델 및 클라이언트 초기화 ---
app = FastAPI()

@app.on_event("startup")
def startup_event():
    print("임베딩 모델 로딩 중...")
    app.state.model = SentenceTransformer(MODEL_NAME)
    print("Qdrant Cloud에 연결 중...")
    app.state.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    print("초기화 완료. 서버가 준비되었습니다.")

# --- 3. CORS 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. 요청/응답 모델 정의 ---
class QueryRequest(BaseModel):
    level: str
    query: str

# 새로운 엔드포인트를 위한 모델
class LevelRequest(BaseModel):
    level: str # 초급, 중급, 고급

# --- 5. LLM 호출 (OpenAI API 연동) ---
def generate_lesson_with_llm(level: str, query: str, context: str) -> str:
    """
    검색된 컨텍스트와 사용자의 질문을 바탕으로 OpenAI API를 호출하여 학습 자료를 생성합니다.
    """
    system_prompt = """
    You are a professional instructor who teaches React. Your role is to create learning materials based on the reference documents provided. The output must be in Korean and strictly follow the Markdown format.
    """
    
    user_prompt = f"""
    Based on the "Reference Documents" below, create learning materials that match the following request.

    **Request Details:**
    - Learning Level: {level}
    - Topic: {query}
    - Additional Request: Please include core concepts, code examples, and three simple review quizzes with their answers (정답) and explanations related to the topic.

    ---
    **Reference Documents:**
    {context}
    ---

    **Output Example (Please follow this format):**
    ## 🚀 {query} 마스터하기 ({level})

    ### 📘 Core Concepts
    (Write a clear and easy-to-understand explanation of the concepts here)

    ### 💻 Code Examples
    ```javascript
    // (Write relevant code examples here)
    ```

    ### 📝 Quiz
    1. **문제**: (Quiz Question 1)
       **정답**: (Answer 1 with explanation)
    2. **문제**: (Quiz Question 2)
       **정답**: (Answer 2 with explanation)
    3. **문제**: (Quiz Question 3)
       **정답**: (Answer 3 with explanation)
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
        return content if content else f"### ❌ '{query}' 학습 자료 생성 실패\n응답 내용이 비어있습니다."
    except Exception as e:
        print(f"OpenAI API 호출 중 오류 발생: {e}")
        return f"### ❌ '{query}' 학습 자료 생성 실패\nAPI 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."


# --- 6. API 엔드포인트 ---

# 기존: 특정 질문에 대한 학습 자료 생성
@app.post("/api/generate-lesson")
def generate_lesson_endpoint(request: QueryRequest):
    try:
        query_vector = app.state.model.encode(request.query).tolist()
        search_results = app.state.qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=5,
            with_payload=True,
        )
        context = "\n\n---\n\n".join([hit.payload['text'] for hit in search_results])
        final_lesson = generate_lesson_with_llm(request.level, request.query, context)
        return {"lesson": final_lesson}
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

# 신규: 특정 레벨의 모든 주제에 대한 학습 자료 일괄 생성
@app.post("/api/generate-topic-lessons")
def generate_topic_lessons_endpoint(request: LevelRequest):
    # 1. 레벨과 서브 카테고리 매핑
    level_mapping = {
        "초급": ["1단계: 사전 준비 ⚙️", "2단계: 메인 학습 코스 (초급) 入门"],
        "중급": ["3단계: 메인 학습 코스 (중급) 🚀"],
        "고급": ["4단계: 심화 탐구 🧠"]
    }
    target_sub_categories = level_mapping.get(request.level)
    if not target_sub_categories:
        raise HTTPException(status_code=400, detail=f"'{request.level}'은 유효하지 않은 레벨입니다.")

    try:
        # 2. 모든 문서를 조회한 후 서버 측에서 필터링
        print(f"--- Qdrant에서 '{request.level}' 레벨 문서 스크롤 시작 ---")
        scrolled_points, _ = app.state.qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000, # 최대 1000개 문서 조회
            with_payload=True
        )
        print(f"--- 총 {len(scrolled_points)}개의 문서 조각을 찾았습니다 ---")

        # 디버깅: 실제 sub_category 값들을 확인
        actual_sub_categories = set()
        for point in scrolled_points:
            sub_category = point.payload.get('sub_category')
            if sub_category:
                actual_sub_categories.add(sub_category)
        
        print(f"--- 실제 데이터베이스의 sub_category 목록 ---")
        for sub_cat in sorted(actual_sub_categories):
            print(f"  - {sub_cat}")
        
        print(f"--- 찾고 있는 target_sub_categories ---")
        for target_cat in target_sub_categories:
            print(f"  - {target_cat}")

        # 3. 서버 측에서 sub_category로 필터링하고 title 별로 그룹화
        lessons_by_title = {}
        ordered_titles = []
        filtered_count = 0
        
        for point in scrolled_points:
            payload = point.payload
            sub_category = payload.get('sub_category')
            title = payload.get('title')
            
            # sub_category가 target_sub_categories에 포함되는지 확인
            if not sub_category or not title or sub_category not in target_sub_categories:
                continue
            
            filtered_count += 1
            if title not in lessons_by_title:
                lessons_by_title[title] = []
                ordered_titles.append(title)
            lessons_by_title[title].append(payload.get('text', ''))

        print(f"--- 필터링된 문서 수: {filtered_count}개 ---")
        print(f"--- 찾은 고유 제목 수: {len(ordered_titles)}개 ---")

        if not ordered_titles:
            return {"lessons": [], "message": f"'{request.level}' 레벨에 해당하는 학습 자료를 찾을 수 없습니다. sub_category 매핑을 확인해주세요."}

        # 4. 각 title 별로 학습 자료 생성
        all_generated_lessons = []
        for title in ordered_titles:
            context = "\n\n---\n\n".join(lessons_by_title[title])
            generated_lesson = generate_lesson_with_llm(
                level=request.level,
                query=title, # 질문 대신 주제(title)를 전달
                context=context
            )
            all_generated_lessons.append({"title": title, "content": generated_lesson})

        return {"lessons": all_generated_lessons}

    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/")
def read_root():
    return {"message": "React 학습 자료 생성 API 서버가 실행 중입니다."}
