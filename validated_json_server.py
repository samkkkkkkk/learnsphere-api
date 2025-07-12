import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import time

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
app = FastAPI(title="React Validated JSON Learning Server", version="1.0.0")
LESSONS_DIR = "validated_lessons_json"

# --- 2. CORS 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. 캐시 및 상태 관리 ---
_cache = {}
_last_cache_update = 0
CACHE_DURATION = 300  # 5분

def get_cache_key(endpoint: str, params: dict = None) -> str:
    """캐시 키를 생성합니다."""
    key = endpoint
    if params:
        key += "_" + "_".join([f"{k}={v}" for k, v in sorted(params.items())])
    return key

def is_cache_valid() -> bool:
    """캐시가 유효한지 확인합니다."""
    return time.time() - _last_cache_update < CACHE_DURATION

def update_cache():
    """캐시를 업데이트합니다."""
    global _last_cache_update
    _last_cache_update = time.time()

def clear_cache():
    """캐시를 초기화합니다."""
    global _cache
    _cache.clear()
    update_cache()

# --- 4. 파일 유효성 검사 ---
def validate_file_exists(filepath: str) -> bool:
    """파일이 존재하는지 확인합니다."""
    return os.path.exists(filepath) and os.path.isfile(filepath)

def load_json_safely(filepath: str) -> dict:
    """안전하게 JSON 파일을 로드합니다."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"파일 로드 오류 {filepath}: {e}")
        raise HTTPException(status_code=500, detail=f"파일 로드 실패: {str(e)}")

# --- 5. API 엔드포인트 ---
@app.get("/api/lessons/{level}")
def get_lessons_by_level(level: str):
    """
    특정 레벨의 검증된 학습 자료 목록을 반환합니다.
    """
    cache_key = get_cache_key("lessons", {"level": level})
    
    # 캐시 확인
    if is_cache_valid() and cache_key in _cache:
        return _cache[cache_key]
    
    try:
        index_filepath = os.path.join(LESSONS_DIR, 'index.json')
        
        if not validate_file_exists(index_filepath):
            raise HTTPException(
                status_code=404, 
                detail="검증된 학습 자료 인덱스 파일을 찾을 수 없습니다. 먼저 json_lesson_validator.py를 실행해주세요."
            )
        
        index_data = load_json_safely(index_filepath)
        
        if level not in index_data:
            raise HTTPException(
                status_code=404, 
                detail=f"'{level}' 레벨의 검증된 학습 자료가 없습니다."
            )
        
        lessons = []
        for lesson in index_data[level]:
            lessons.append({
                "title": lesson['title'],
                "filename": lesson['filename'],
                "number": lesson['number']
            })
        
        result = {"lessons": lessons}
        
        # 캐시에 저장
        _cache[cache_key] = result
        update_cache()
        
        print(f"--- '{level}' 레벨의 검증된 학습 자료 {len(lessons)}개 반환 ---")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/api/lesson/{filename}")
def get_lesson_content(filename: str):
    """
    특정 검증된 학습 자료의 JSON 내용을 반환합니다.
    """
    cache_key = get_cache_key("lesson", {"filename": filename})
    
    # 캐시 확인
    if is_cache_valid() and cache_key in _cache:
        return _cache[cache_key]
    
    try:
        filepath = os.path.join(LESSONS_DIR, filename)
        
        if not validate_file_exists(filepath):
            raise HTTPException(
                status_code=404, 
                detail=f"검증된 파일 '{filename}'을 찾을 수 없습니다."
            )
        
        lesson_data = load_json_safely(filepath)
        
        # 캐시에 저장
        _cache[cache_key] = lesson_data
        update_cache()
        
        return lesson_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/api/available-levels")
def get_available_levels():
    """
    사용 가능한 레벨 목록을 반환합니다.
    """
    cache_key = get_cache_key("levels")
    
    # 캐시 확인
    if is_cache_valid() and cache_key in _cache:
        return _cache[cache_key]
    
    try:
        index_filepath = os.path.join(LESSONS_DIR, 'index.json')
        
        if not validate_file_exists(index_filepath):
            return {"levels": []}
        
        index_data = load_json_safely(index_filepath)
        levels = list(index_data.keys())
        
        result = {"levels": levels}
        
        # 캐시에 저장
        _cache[cache_key] = result
        update_cache()
        
        return result
        
    except Exception as e:
        print(f"서버 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="서버 내부 오류가 발생했습니다.")

@app.get("/api/status")
def get_server_status():
    """
    서버 상태를 반환합니다.
    """
    try:
        index_filepath = os.path.join(LESSONS_DIR, 'index.json')
        
        if validate_file_exists(index_filepath):
            index_data = load_json_safely(index_filepath)
            total_lessons = sum(len(lessons) for lessons in index_data.values())
            
            return {
                "status": "running",
                "validated_files_count": total_lessons,
                "available_levels": list(index_data.keys()),
                "cache_status": {
                    "cache_size": len(_cache),
                    "last_update": _last_cache_update,
                    "is_valid": is_cache_valid()
                }
            }
        else:
            return {
                "status": "no_validated_files",
                "message": "검증된 파일이 없습니다. json_lesson_validator.py를 실행해주세요."
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.post("/api/cache/clear")
def clear_server_cache():
    """
    서버 캐시를 초기화합니다.
    """
    clear_cache()
    return {"message": "캐시가 초기화되었습니다."}

@app.get("/")
def read_root():
    return {
        "message": "React 검증된 JSON 학습 자료 서버가 실행 중입니다.",
        "version": "1.0.0",
        "endpoints": {
            "lessons": "/api/lessons/{level}",
            "lesson": "/api/lesson/{filename}",
            "levels": "/api/available-levels",
            "status": "/api/status",
            "clear_cache": "/api/cache/clear"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("=== React 검증된 JSON 학습 자료 서버 시작 ===")
    print(f"--- 검증된 파일 디렉토리: {LESSONS_DIR} ---")
    print("--- 포트 8001 사용 (기존 서버와 충돌 방지) ---")
    uvicorn.run(app, host="0.0.0.0", port=8001)  # 다른 포트 사용 