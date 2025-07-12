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
    - Question: {query}
    - Additional Request: Please include core concepts, code examples, and three simple review quizzes related to the question.

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
    1. (Quiz Question 1)
    2. (Quiz Question 2)
    3. (Quiz Question 3)
    """
    
    try:
        print("--- OpenAI API에 프롬프트 전송 중 ---")
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # OpenAI의 최신 고효율 모델 사용
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        print("--- OpenAI API로부터 응답 수신 완료 ---")
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API 호출 중 오류 발생: {e}")
        return "학습 자료를 생성하는 데 실패했습니다. API 키 또는 네트워크 상태를 확인해주세요."


# --- 6. API 엔드포인트 ---
@app.post("/api/generate-lesson")
def generate_lesson_endpoint(request: QueryRequest):
    try:
        # 1. 사용자 질문을 벡터로 변환
        query_vector = app.state.model.encode(request.query).tolist()

        # 2. Qdrant에서 관련 문서 검색
        search_results = app.state.qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=5,
            with_payload=True,
        )

        # 3. 검색된 문서 내용을 하나의 컨텍스트 문자열로 결합
        context = "\n\n---\n\n".join(
            [hit.payload['text'] for hit in search_results]
        )

        # 4. OpenAI API를 호출하여 최종 답변 생성
        final_lesson = generate_lesson_with_llm(request.level, request.query, context)

        return {"lesson": final_lesson}

    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/")
def read_root():
    return {"message": "React 학습 자료 생성 API 서버가 실행 중입니다."}
