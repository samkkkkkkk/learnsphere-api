import json
import uuid
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 1. 설정 (환경 변수에서 Qdrant 정보 가져오기) ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# 파이프라인(app/services/qdrant_service.py)이 읽는 컬렉션과 동일해야 합니다.
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "react-docs-complete")
MODEL_NAME = 'distiluse-base-multilingual-cased-v1'

# Qdrant URL 또는 API 키가 설정되지 않은 경우 오류를 발생시킵니다.
if not QDRANT_URL or not QDRANT_API_KEY:
    raise ValueError("QDRANT_URL과 QDRANT_API_KEY가 .env 파일에 설정되어야 합니다.")


# --- 2. 데이터 로드 및 청킹 ---
print("새로운 React 학습 데이터 로딩 중...")
try:
    # 가공 파이프라인 산출물(라벨 포함)을 읽는다. raw(react_docs_data.json)이 아님.
    with open('react_complete_learning_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print("오류: react_complete_learning_data.json 파일을 찾을 수 없습니다. 먼저 'uv run python -m app.scripts.enrich_learning_data'로 생성하세요.")
    exit()

chunks = []
for doc in data:
    # YAML frontmatter가 존재하면 제거합니다.
    content_parts = doc['content'].split('---', 2)
    actual_content = content_parts[2].strip() if len(content_parts) > 2 else doc['content'].strip()

    # 마크다운 소제목('## ')을 기준으로 내용을 분할합니다.
    sections = actual_content.split('\n## ')
    for i, section in enumerate(sections):
        section_text = section.strip()
        if section_text:
            # 첫 번째가 아닌 섹션에는 '##'를 다시 붙여줍니다.
            if i > 0:
                section_text = f"## {section_text}"

            # 검색 정확도를 높이기 위해 메타데이터를 텍스트에 포함시킵니다.
            full_text_for_embedding = (
                f"카테고리: {doc.get('main_category', '')} > {doc.get('sub_category', '')}\n"
                f"제목: {doc.get('title', '')}\n\n"
                f"{section_text}"
            )
            
            # Qdrant에 저장할 payload 객체를 생성합니다.
            payload = {
                "text": full_text_for_embedding, # 임베딩 및 검색에 사용될 전체 텍스트
                "source": doc.get('source_path', ''),
                "main_category": doc.get('main_category', ''),
                "sub_category": doc.get('sub_category', ''),
                "title": doc.get('title', '')
            }
            chunks.append(payload)

print(f"총 {len(chunks)}개의 데이터 조각 생성 완료.")


# --- 3. 임베딩 모델 로드 ---
print("임베딩 모델 로딩 중... (시간이 걸릴 수 있습니다)")
model = SentenceTransformer(MODEL_NAME)


# --- 4. Qdrant 클라이언트 초기화 및 컬렉션 생성 ---
print(f"Qdrant Cloud에 연결 중: {QDRANT_URL}")
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

print(f"Qdrant 컬렉션 '{COLLECTION_NAME}' 생성(또는 재생성) 중...")
client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=models.VectorParams(
        size=model.get_sentence_embedding_dimension(),
        distance=models.Distance.COSINE
    ),
)

# Qdrant Cloud는 payload 필드 필터링(scroll)에 keyword 인덱스가 필요하다.
# (in-memory 모드는 인덱스 없이도 동작하므로 dry-run에서는 드러나지 않음)
client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="sub_category",
    field_schema=models.PayloadSchemaType.KEYWORD,
)


# --- 5. 데이터 벡터화 및 Qdrant에 저장 (Upsert) ---
print("데이터 벡터화 및 Qdrant에 저장 시작...")
client.upload_points(
    collection_name=COLLECTION_NAME,
    points=[
        models.PointStruct(
            id=str(uuid.uuid4()), # 각 데이터 조각에 고유 ID 부여
            vector=model.encode(chunk['text']).tolist(),
            payload=chunk
        ) for chunk in chunks
    ],
    wait=True, # 모든 데이터가 인덱싱될 때까지 대기
)

print("데이터 인덱싱 완료!")
