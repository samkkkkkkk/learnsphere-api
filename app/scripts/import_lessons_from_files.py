# app/scripts/import_lessons_from_files.py
"""generated_content/ 폴더의 레슨 JSON을 DB(lessons/lesson_versions)로 일회성 이관.

사용법:
    uv run python -m app.scripts.import_lessons_from_files --content-dir "C:\\WorkSpace\\generated_content"

- 파일명 규칙 `{레벨}_{번호}_{슬러그}.json`을 파싱해 (level, position, slug)를 얻는다.
- 본문은 LessonContentSchema로 검증하며, 한 파일이라도 실패하면 아무것도 쓰지 않는다 (all-or-nothing).
- lessons 테이블이 비어있지 않으면 --force 없이는 중단한다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from ..core.database import SessionLocal
from ..crud import crud_lessons
from ..models.models import Lesson
from ..schemas.schemas import LessonContentSchema

VALID_LEVELS = ("초급", "중급", "고급")
FILENAME_RE = re.compile(r'^(?P<level>[^_]+)_(?P<number>\d+)_(?P<slug>.+)\.json$')


class ImportAbort(Exception):
    """이관을 중단해야 하는 상황 (검증 실패, 비어있지 않은 테이블 등)."""


def run_import(db, content_dir: Path, created_by: str = "import", force: bool = False) -> int:
    """검증 → 세대 생성 → 적재 → finalize. 성공 시 이관한 레슨 수를 반환."""
    if not content_dir.is_dir():
        raise ImportAbort(f"디렉토리가 아닙니다: {content_dir}")

    if db.query(Lesson).count() > 0 and not force:
        raise ImportAbort("lessons 테이블이 비어있지 않습니다. 재이관하려면 --force를 지정하세요.")

    files = sorted(p for p in content_dir.glob("*.json") if p.name != "index.json")
    if not files:
        raise ImportAbort(f"이관할 레슨 JSON이 없습니다: {content_dir}")

    parsed, errors = [], []
    for path in files:
        match = FILENAME_RE.match(path.name)
        if not match:
            errors.append(f"{path.name}: 파일명 형식 불일치 (레벨_번호_슬러그.json)")
            continue
        level = match.group("level")
        if level not in VALID_LEVELS:
            errors.append(f"{path.name}: 알 수 없는 레벨 '{level}'")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            content = LessonContentSchema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        parsed.append((level, int(match.group("number")), match.group("slug").lower(), content))

    if errors:
        detail = "\n".join(f"  - {err}" for err in errors)
        raise ImportAbort(f"검증 실패 {len(errors)}건 — 아무것도 쓰지 않고 중단합니다:\n{detail}")

    generation = crud_lessons.create_generation(db, source="import", created_by=created_by)
    try:
        for level, number, slug, content in parsed:
            lesson = crud_lessons.upsert_lesson(db, level, slug, topic=content.title)
            # exclude_none: explanation 없는 퀴즈를 원본 그대로 {question, answer}로 저장
            crud_lessons.insert_version(
                db, lesson, generation.id, content.model_dump(exclude_none=True), position=number)
        db.commit()
        crud_lessons.finalize_generation(db, generation.id)
    except Exception as exc:
        db.rollback()
        crud_lessons.fail_generation(db, generation.id, error=str(exc))
        raise
    return len(parsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="레슨 JSON 파일 → DB 일회성 이관")
    parser.add_argument("--content-dir", required=True, help="레슨 JSON이 있는 폴더 (예: C:\\WorkSpace\\generated_content)")
    parser.add_argument("--created-by", default="import", help="lesson_generations.created_by 값")
    parser.add_argument("--force", action="store_true", help="lessons 테이블이 비어있지 않아도 진행")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        count = run_import(db, Path(args.content_dir), created_by=args.created_by, force=args.force)
    except ImportAbort as exc:
        print(f"[ABORT] {exc}")
        sys.exit(1)
    finally:
        db.close()
    print(f"[OK] 레슨 {count}개 이관 완료")


if __name__ == "__main__":
    main()
