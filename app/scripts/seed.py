# backend/scripts/seed.py
import json
import os
# import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# FastAPI 앱의 모듈을 임포트하기 위해 경로 추가
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import DATABASE_URL, Base
from app.models.models import Subject, LearningContent

# 데이터 파일 경로 설정
DATA_FILE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'react_complete_learning_data.json'
))

def seed_data():
    engine = create_engine(DATABASE_URL)
    # 모델에 정의된 모든 테이블을 DB에 생성 (이미 있다면 지나감)
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 1. JSON 파일 읽기
        print("Reading data from JSON file...")
        with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2. 'React' 주제 생성 (없을 경우에만)
        react_subject = db.query(Subject).filter(Subject.subject_name == 'React').first()
        if not react_subject:
            print("Creating 'React' subject...")
            react_subject = Subject(subject_name='React', description='React.js 학습 과정 및 API 레퍼런스')
            db.add(react_subject)
            db.commit()
            db.refresh(react_subject)
        else:
            print("'React' subject already exists.")

        # 3. 콘텐츠 데이터 주입
        print(f"Seeding {len(data)} learning contents...")
        content_count = 0
        for item in data:
            exists = db.query(LearningContent).filter(LearningContent.source_path == item['source_path']).first()
            if not exists:
                content = LearningContent(
                    subject_id=react_subject.subject_id,
                    title=item['title'],
                    main_category=item['main_category'],
                    sub_category=item['sub_category'],
                    topic_group=item.get('topic_group'),
                    source_path=item['source_path']
                )
                db.add(content)
                content_count += 1
        
        db.commit()
        print(f"Successfully added {content_count} new contents.")
        print("Data seeding completed!")

    except Exception as e:
        db.rollback()
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()