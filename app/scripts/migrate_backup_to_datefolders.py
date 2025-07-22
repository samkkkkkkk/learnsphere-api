import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import re
import shutil
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import DATABASE_URL
from app.models.models import LessonBackup, Base

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content', 'backup'))

# DB 연결
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def extract_date_from_filename(filename):
    # 예: 고급_01_Typescript_20240608_153000.json
    m = re.search(r'_(\d{8})_(\d{6})', filename)
    if m:
        date_str = m.group(1)  # 20240608
        try:
            dt = datetime.strptime(date_str, '%Y%m%d')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return None
    return None

def migrate_files_and_update_db():
    for fname in os.listdir(BACKUP_DIR):
        fpath = os.path.join(BACKUP_DIR, fname)
        if not os.path.isfile(fpath) or not fname.endswith('.json'):
            continue
        date_folder = extract_date_from_filename(fname)
        if not date_folder:
            print(f"날짜 추출 실패: {fname}")
            continue
        # 새 폴더 생성
        new_dir = os.path.join(BACKUP_DIR, date_folder)
        os.makedirs(new_dir, exist_ok=True)
        new_path = os.path.join(new_dir, fname)
        # 파일 이동
        shutil.move(fpath, new_path)
        # DB 업데이트
        rel_path = f"{date_folder}/{fname}"
        backups = db.query(LessonBackup).filter(LessonBackup.backup_filename == fname).all()
        for b in backups:
            b.backup_filename = rel_path
        db.commit()
        print(f"이동 및 DB 업데이트: {fname} -> {rel_path}")

if __name__ == '__main__':
    migrate_files_and_update_db()
    db.close()
    print("모든 파일 이동 및 DB 업데이트 완료.")