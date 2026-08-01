# backend/app/services/openai_service.py

import os
import json
import re
from openai import OpenAI
from pydantic import ValidationError
from typing import Dict

from ..schemas.schemas import LessonContentSchema

# --- 설정 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- OpenAI 클라이언트 초기화 ---
client = OpenAI(api_key=OPENAI_API_KEY)


class LessonGenerationError(Exception):
    """레슨 생성 실패. 호출자(파이프라인)가 실패 토픽으로 집계한다.

    과거에는 오류 메시지를 core_concepts에 담은 '에러 레슨'을 정상 반환했지만,
    저장소가 DB로 바뀌면서 에러 텍스트가 정식 버전으로 영구 저장되는 것을 막기 위해
    명시적 예외로 전환했다.
    """

def normalize_lesson(data: Dict, level: str, topic: str) -> Dict:
    """
    LLM 응답이 기대 스키마와 어긋나도 API 응답 모델(LessonContent)과
    호환되도록 필수 키를 보정합니다.
    """
    return {
        "title": str(data.get("title") or topic),
        "level": str(data.get("level") or level),
        "core_concepts": str(data.get("core_concepts") or ""),
        "code_examples": data["code_examples"] if isinstance(data.get("code_examples"), list) else [],
        "quizzes": data["quizzes"] if isinstance(data.get("quizzes"), list) else [],
    }


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
    IMPORTANT: All content should be in Korean. Return only valid JSON.
    """
    
    user_prompt = f"""
    Based on the "Reference Documents" below, create learning materials that match the following request.

    **Request Details:**
    - Learning Level: {level}
    - Topic: {topic}
    - Additional Request: Please include core concepts, code examples with actual JavaScript/JSX code, and three simple review quizzes with their answers and explanations related to the topic.
    - 자세히, 예시, 해설을 충분히 포함해서 학습자가 이해하기 쉽도록 길고 구체적으로 작성해 주세요.
    - 핵심 개념은 3~5문단 이상, 코드 예시는 2~3개, 각 예시마다 설명을 2~3문장 이상, 퀴즈는 3~5개, 각 퀴즈마다 해설을 2문장 이상 포함해 주세요.

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

        if not content:
            raise ValueError("OpenAI 응답 내용이 비어있습니다.")

        lesson_data = json.loads(content)
        normalized = normalize_lesson(lesson_data, level, topic)
        # 저장 전 정본 스키마 검증 — 빈 core_concepts 등 불량 레슨을 여기서 차단
        validated = LessonContentSchema.model_validate(normalized)
        return validated.model_dump(exclude_none=True)

    except ValidationError as e:
        raise LessonGenerationError(
            f"'{topic}' 생성 결과가 레슨 스키마에 맞지 않습니다: {e}") from e
    except Exception as e:
        raise LessonGenerationError(f"'{topic}' 생성 중 오류: {e}") from e
