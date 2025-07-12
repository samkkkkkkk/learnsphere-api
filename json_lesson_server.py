import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
app = FastAPI()
LESSONS_DIR = "generated_lessons_json"

# --- 2. CORS 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. 요청 모델 정의 ---
class LevelRequest(BaseModel):
    level: str

# --- 4. API 엔드포인트 ---
@app.get("/api/lessons/{level}")
def get_lessons_by_level(level: str):
    """
    특정 레벨의 학습 자료 목록을 반환합니다.
    """
    try:
        index_filepath = os.path.join(LESSONS_DIR, 'index.json')
        
        if not os.path.exists(index_filepath):
            raise HTTPException(
                status_code=404, 
                detail="학습 자료 인덱스 파일을 찾을 수 없습니다. 먼저 json_lesson_generator.py를 실행해주세요."
            )
        
        with open(index_filepath, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        if level not in index_data:
            raise HTTPException(
                status_code=404, 
                detail=f"'{level}' 레벨의 학습 자료가 없습니다."
            )
        
        lessons = []
        for lesson in index_data[level]:
            lessons.append({
                "title": lesson['title'],
                "filename": lesson['filename'],
                "number": lesson['number']
            })
        
        print(f"--- '{level}' 레벨의 학습 자료 {len(lessons)}개 반환 ---")
        return {"lessons": lessons}
        
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/api/lesson/{filename}")
def get_lesson_content(filename: str):
    """
    특정 학습 자료의 JSON 내용을 반환합니다.
    """
    try:
        filepath = os.path.join(LESSONS_DIR, filename)
        
        if not os.path.exists(filepath):
            raise HTTPException(
                status_code=404, 
                detail=f"파일 '{filename}'을 찾을 수 없습니다."
            )
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lesson_data = json.load(f)
        
        return lesson_data
        
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/api/available-levels")
def get_available_levels():
    """
    사용 가능한 레벨 목록을 반환합니다.
    """
    try:
        index_filepath = os.path.join(LESSONS_DIR, 'index.json')
        
        if not os.path.exists(index_filepath):
            return {"levels": []}
        
        with open(index_filepath, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        levels = list(index_data.keys())
        return {"levels": levels}
        
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/")
def read_root():
    return {"message": "React JSON 학습 자료 서버가 실행 중입니다."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 