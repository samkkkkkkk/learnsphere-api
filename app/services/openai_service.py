# backend/app/services/openai_service.py

import os
import json
import re
from openai import OpenAI
from typing import Dict

# --- 설정 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- OpenAI 클라이언트 초기화 ---
client = OpenAI(api_key=OPENAI_API_KEY)

def generate_lesson_with_llm(level: str, topic: str, context: str) -> Dict:
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
                "code": "```javascript\\n실제 JavaScript/JSX 코드\\n```"
            }
        ],
        "quizzes": [
            {
                "question": "문제",
                "answer": "정답"
            }
        ]
    }
    IMPORTANT: All content should be in Korean. Return only valid JSON.
    """
    
    user_prompt = f"""
    Based on the "Reference Documents" below, create learning materials that match the following request.

    **Request Details:**
    - Learning Level: {level}
    - Topic: {topic}
    - Additional Request: Please include core concepts, code examples with actual JavaScript/JSX code, and three simple review quizzes with their answers and explanations related to the topic.

    ---
    **Reference Documents:**
    {context}
    ---

    **Output Format (JSON only):**
    """
    
    try:
        print(f"  > [OpenAI] '{topic}' 주제 프롬프트 전송 시작...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        print(f"  > [OpenAI] '{topic}' 주제 응답 수신 완료.")
        content = response.choices[0].message.content
        
        if content:
            # LLM 응답에서 JSON 부분만 정확히 파싱
            lesson_data = json.loads(content)
            # TODO: 필요 시, 응답받은 JSON의 구조를 검증하거나 기본값을 채우는 로직 추가
            return lesson_data
        else:
            raise ValueError("OpenAI 응답 내용이 비어있습니다.")
            
    except Exception as e:
        print(f"  > [OpenAI] API 호출 중 오류 발생: {e}")
        # 오류 발생 시, 프론트엔드에 전달할 에러 메시지가 포함된 기본 JSON 구조 반환
        return {
            "title": topic,
            "level": level,
            "core_concepts": f"'{topic}' 학습 자료 생성 중 오류가 발생했습니다: {e}",
            "code_examples": [],
            "quizzes": []
        }
