# backend/app/services/content_pipeline_service.py

import json
import os
import re
from . import qdrant_service, openai_service

# --- 설정 ---
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_content_generation_for_level(level: str):
    """
    특정 레벨에 대한 콘텐츠 생성 파이프라인을 실행합니다.
    """
    print(f"✅ [Pipeline-START] '{level}' 레벨의 콘텐츠 생성을 시작합니다.")
    
    try:
        topics_with_contexts = qdrant_service.get_contexts_by_level(level)
        
        if not topics_with_contexts:
            print(f"⚠️ [Pipeline-WARN] '{level}' 레벨에 해당하는 토픽이 없습니다.")
            return

        total_topics = len(topics_with_contexts)
        for i, (topic, context) in enumerate(topics_with_contexts.items(), 1):
            print(f"\n--- [Processing {i}/{total_topics}] '{topic}' 레슨 생성 중 ---")
            
            final_lesson = openai_service.generate_lesson_with_llm(level, topic, context)
            
            safe_title = re.sub(r'[^\w\s-]', '', topic).strip()
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            filename = f"{level}_{i:02d}_{safe_title}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(final_lesson, f, ensure_ascii=False, indent=2)
            
            print(f"--- [Saved] '{filename}' 파일 저장 완료 ---")
            
        print(f"✅ [Pipeline-END] '{level}' 레벨의 콘텐츠 생성이 성공적으로 완료되었습니다.")

    except Exception as e:
        print(f"❌ [Pipeline-ERROR] '{level}' 레벨 파이프라인 실행 중 오류가 발생했습니다: {e}")


def run_full_content_generation():
    """
    [관리자용] 모든 레벨(초급, 중급, 고급)에 대한 전체 콘텐츠 생성 파이프라인을 실행합니다.
    """
    print("🚀 [ADMIN-TASK] 전체 학습 콘텐츠 생성을 시작합니다.")
    levels = ["초급", "중급", "고급"]
    for level in levels:
        run_content_generation_for_level(level)
    
    # 모든 작업 완료 후 최종 인덱스 파일 생성
    create_index_file()
    print("✅ [ADMIN-TASK] 전체 학습 콘텐츠 생성이 완료되었습니다.")


def create_index_file():
    """
    생성된 모든 레슨 파일의 목록을 담은 index.json 파일을 생성/업데이트합니다.
    """
    print("\n--- [Indexing] 인덱스 파일 생성 중 ---")
    index_data = {}
    
    if not os.path.exists(OUTPUT_DIR):
        return

    for filename in sorted(os.listdir(OUTPUT_DIR)):
        if filename.endswith('.json') and filename != 'index.json':
            try:
                parts = filename.replace('.json', '').split('_', 2)
                if len(parts) >= 3:
                    level, number, title_part = parts
                    title = title_part.replace('-', ' ')
                    
                    if level not in index_data:
                        index_data[level] = []
                    
                    index_data[level].append({
                        'filename': filename,
                        'title': title,
                        'number': int(number)
                    })
            except (ValueError, IndexError) as e:
                print(f"--- [Indexing] 경고: 파일명 '{filename}'의 형식이 올바르지 않습니다. ({e})")

    index_filepath = os.path.join(OUTPUT_DIR, 'index.json')
    with open(index_filepath, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"--- [Indexing] 인덱스 파일 생성 완료: {index_filepath} ---")
