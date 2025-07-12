import os
import json
from openai import OpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import html
import re

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COLLECTION_NAME = "react-docs-complete"
MODEL_NAME = 'distiluse-base-multilingual-cased-v1'
OUTPUT_DIR = "generated_lessons"

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
def generate_lesson_with_llm(level: str, query: str, context: str) -> str:
    """
    검색된 컨텍스트와 사용자의 질문을 바탕으로 OpenAI API를 호출하여 학습 자료를 생성합니다.
    """
    system_prompt = """
    You are a professional instructor who teaches React. Your role is to create learning materials based on the reference documents provided. 
    The output must be in Korean and strictly follow the Markdown format.
    For quizzes, use the exact format: "1. **문제**: [question]" and "**정답**: [answer]" on separate lines.
    """
    
    user_prompt = f"""
    Based on the "Reference Documents" below, create learning materials that match the following request.

    **Request Details:**
    - Learning Level: {level}
    - Topic: {query}
    - Additional Request: Please include core concepts, code examples, and three simple review quizzes with their answers and explanations related to the topic.

    ---
    **Reference Documents:**
    {context}
    ---

    **Output Example (Please follow this EXACT format):**
    ## 🚀 {query} 마스터하기 ({level})

    ### 📘 Core Concepts
    (Write a clear and easy-to-understand explanation of the concepts here)

    ### 💻 Code Examples
    ```javascript
    // (Write relevant code examples here)
    ```

    ### 📝 Quiz
    1. **문제**: (Write a clear quiz question here)
       **정답**: (Write the answer with explanation here)
    2. **문제**: (Write a clear quiz question here)
       **정답**: (Write the answer with explanation here)
    3. **문제**: (Write a clear quiz question here)
       **정답**: (Write the answer with explanation here)

    **IMPORTANT**: Each quiz must follow the exact format "1. **문제**: [question]" and "**정답**: [answer]" on separate lines.
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

# --- 4. Markdown을 HTML로 변환하는 함수 ---
def markdown_to_html(markdown_content: str) -> str:
    """
    Markdown 콘텐츠를 HTML로 변환합니다.
    """
    # 기본적인 Markdown 변환 (실제로는 더 정교한 라이브러리 사용 권장)
    html_content = markdown_content
    
    # 제목 변환
    html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
    
    # 코드 블록 변환
    html_content = re.sub(r'```(\w+)\n(.*?)\n```', r'<pre><code class="language-\1">\2</code></pre>', html_content, flags=re.DOTALL)
    html_content = re.sub(r'```\n(.*?)\n```', r'<pre><code>\1</code></pre>', html_content, flags=re.DOTALL)
    
    # 인라인 코드 변환
    html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
    
    # 굵은 텍스트 변환
    html_content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html_content)
    
    # 퀴즈 섹션 특별 처리
    quiz_section_match = re.search(r'### 📝 Quiz\n(.*?)(?=\n## |\n### |$)', html_content, re.DOTALL)
    if quiz_section_match:
        quiz_section = quiz_section_match.group(1)
        
        # 퀴즈 문제들을 파싱
        quiz_blocks = quiz_section.split(r'(?=\d+\.\s*\*\*문제\*\*:)')
        quiz_html = '<div class="quiz-section"><h3>📝 Quiz</h3>'
        
        for i, block in enumerate(quiz_blocks[1:], 1):  # 첫 번째는 빈 문자열이므로 제외
            problem_match = re.search(r'(\d+)\.\s*\*\*문제\*\*:\s*(.+?)(?=\n\s*\*\*정답\*\*:)', block, re.DOTALL)
            answer_match = re.search(r'\*\*정답\*\*:\s*(.+)', block, re.DOTALL)
            
            if problem_match and answer_match:
                quiz_number = problem_match.group(1)
                question = problem_match.group(2).strip()
                answer = answer_match.group(1).strip()
                
                quiz_html += f'''
                <div class="quiz-item" data-quiz-id="quiz-{quiz_number}">
                    <div class="quiz-question">
                        <span class="quiz-number">{quiz_number}.</span>
                        <span class="quiz-text">{question}</span>
                        <button class="quiz-toggle-btn" onclick="toggleAnswer('quiz-{quiz_number}')">
                            정답 보기
                        </button>
                    </div>
                    <div class="quiz-answer-content" id="answer-{quiz_number}" style="display: none;">
                        {answer}
                    </div>
                </div>
                '''
        
        quiz_html += '</div>'
        
        # 원본 퀴즈 섹션을 HTML로 교체
        html_content = re.sub(r'### 📝 Quiz\n.*?(?=\n## |\n### |$)', quiz_html, html_content, flags=re.DOTALL)
    
    # 일반 텍스트를 단락으로 변환
    lines = html_content.split('\n')
    html_lines = []
    current_paragraph = []
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_paragraph:
                html_lines.append(f'<p>{" ".join(current_paragraph)}</p>')
                current_paragraph = []
        elif line.startswith('<'):
            if current_paragraph:
                html_lines.append(f'<p>{" ".join(current_paragraph)}</p>')
                current_paragraph = []
            html_lines.append(line)
        else:
            current_paragraph.append(line)
    
    if current_paragraph:
        html_lines.append(f'<p>{" ".join(current_paragraph)}</p>')
    
    return '\n'.join(html_lines)

# --- 5. HTML 템플릿 생성 ---
def create_html_template(title: str, content: str, level: str) -> str:
    """
    완전한 HTML 페이지를 생성합니다.
    """
    html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .lesson-container {{
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }}
        h2, h3 {{
            color: #2d3748;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.5rem;
            margin-top: 2rem;
        }}
        code {{
            background: #f7fafc;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'Fira Code', monospace;
            color: #e53e3e;
        }}
        pre {{
            background: #2d3748;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1.5rem 0;
        }}
        pre code {{
            background: none;
            color: inherit;
            padding: 0;
        }}
        .quiz-section {{
            margin-top: 2rem;
            padding: 1.5rem;
            background: #f7fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        .quiz-item {{
            margin: 1rem 0;
            padding: 1rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: white;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }}
        .quiz-question {{
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 0.5rem;
        }}
        .quiz-number {{
            font-weight: 600;
            color: #667eea;
            min-width: 2rem;
        }}
        .quiz-text {{
            flex: 1;
            line-height: 1.5;
        }}
        .quiz-toggle-btn {{
            padding: 0.4rem 0.8rem;
            background: linear-gradient(135deg, #48bb78, #38a169);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .quiz-toggle-btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(72, 187, 120, 0.3);
        }}
        .quiz-answer-content {{
            margin-top: 0.75rem;
            padding: 0.75rem;
            background: #f0fff4;
            border-left: 3px solid #48bb78;
            border-radius: 4px;
            color: #22543d;
            line-height: 1.5;
        }}
        .level-badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            background: #667eea;
            color: white;
            border-radius: 4px;
            font-size: 0.8rem;
            margin-left: 0.5rem;
        }}
    </style>
</head>
<body>
    <div class="lesson-container">
        {content}
    </div>
    
    <script>
        function toggleAnswer(quizId) {{
            const answerElement = document.getElementById('answer-' + quizId.replace('quiz-', ''));
            const button = event.target;
            
            if (answerElement.style.display === 'none') {{
                answerElement.style.display = 'block';
                button.textContent = '정답 숨기기';
            }} else {{
                answerElement.style.display = 'none';
                button.textContent = '정답 보기';
            }}
        }}
    </script>
</body>
</html>
    """
    return html_content

# --- 6. 메인 생성 함수 ---
def generate_all_lessons():
    """
    모든 레벨의 학습 자료를 생성합니다.
    """
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
            markdown_content = generate_lesson_with_llm(level, title, context)
            
            # HTML로 변환
            html_content = markdown_to_html(markdown_content)
            full_html = create_html_template(title, html_content, level)
            
            # 파일명 생성 (안전한 파일명으로 변환)
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            filename = f"{level}_{i:02d}_{safe_title}.html"
            
            # HTML 파일 저장
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_html)
            
            print(f"--- {filename} 저장 완료 ---")
        
        print(f"=== {level} 레벨 학습 자료 생성 완료 ===\n")
    
    # 인덱스 파일 생성
    create_index_file()
    print("🎉 모든 학습 자료 생성 완료!")

def create_index_file():
    """
    생성된 파일들의 인덱스를 생성합니다.
    """
    index_data = {}
    
    for filename in os.listdir(OUTPUT_DIR):
        if filename.endswith('.html'):
            # 파일명에서 레벨과 제목 추출
            parts = filename.replace('.html', '').split('_', 2)
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