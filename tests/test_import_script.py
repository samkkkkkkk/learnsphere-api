# tests/test_import_script.py
"""파일 → DB 일회성 import 스크립트 테스트."""
import json

import pytest

from app.crud import crud_lessons as crud
from app.models.models import Lesson, LessonGeneration
from app.scripts.import_lessons_from_files import ImportAbort, run_import


def write_lesson(directory, filename, title="테스트 레슨", level="초급"):
    data = {
        "title": title,
        "level": level,
        "core_concepts": "핵심 개념",
        "code_examples": [{"description": "예시", "code": "code"}],
        "quizzes": [{"question": "q", "answer": "a"}],
    }
    (directory / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_import_success(db_session, tmp_path):
    write_lesson(tmp_path, "초급_01_First-Lesson.json", "첫 레슨")
    write_lesson(tmp_path, "고급_01_Deep-Dive.json", "심화", level="고급")
    (tmp_path / "index.json").write_text("{}", encoding="utf-8")  # 제외 대상

    count = run_import(db_session, tmp_path)

    assert count == 2
    index = crud.get_lesson_index(db_session)
    assert [l["title"] for l in index["초급"]] == ["첫 레슨"]
    assert [l["title"] for l in index["고급"]] == ["심화"]
    # slug는 파일명에서 lowercase로 정규화
    assert db_session.query(Lesson).filter(Lesson.slug == "first-lesson").count() == 1
    generation = db_session.query(LessonGeneration).one()
    assert generation.source == "import"
    assert generation.status == "completed"
    assert generation.succeeded == 2


def test_import_invalid_content_writes_nothing(db_session, tmp_path):
    write_lesson(tmp_path, "초급_01_Good.json")
    (tmp_path / "초급_02_Broken.json").write_text(
        json.dumps({"title": "빈 본문", "level": "초급", "core_concepts": "",
                    "code_examples": [], "quizzes": []}, ensure_ascii=False),
        encoding="utf-8")

    with pytest.raises(ImportAbort):
        run_import(db_session, tmp_path)
    # all-or-nothing: 유효한 파일도 쓰이지 않음
    assert db_session.query(Lesson).count() == 0
    assert db_session.query(LessonGeneration).count() == 0


def test_import_preserves_quiz_explanation(db_session, tmp_path):
    data = {
        "title": "설명 포함", "level": "초급", "core_concepts": "개념",
        "code_examples": [{"description": "예시", "code": "code"}],
        "quizzes": [
            {"question": "q1", "answer": "a1", "explanation": "해설"},
            {"question": "q2", "answer": "a2"},
        ],
    }
    (tmp_path / "초급_01_With-Explanation.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")

    run_import(db_session, tmp_path)

    lesson = db_session.query(Lesson).one()
    detail = crud.get_lesson_detail(db_session, lesson.id)
    # explanation은 보존되고, 없는 퀴즈에는 키 자체가 생기지 않아야 함 (원본 충실)
    assert detail["quizzes"] == data["quizzes"]


def test_import_bad_filename_aborts(db_session, tmp_path):
    write_lesson(tmp_path, "이상한파일명.json")
    with pytest.raises(ImportAbort):
        run_import(db_session, tmp_path)
    assert db_session.query(Lesson).count() == 0


def test_import_unknown_level_aborts(db_session, tmp_path):
    write_lesson(tmp_path, "중수_01_X.json", level="중수")
    with pytest.raises(ImportAbort):
        run_import(db_session, tmp_path)


def test_import_nonempty_requires_force(db_session, tmp_path):
    write_lesson(tmp_path, "초급_01_A.json", "A")
    run_import(db_session, tmp_path)

    write_lesson(tmp_path, "초급_02_B.json", "B")
    with pytest.raises(ImportAbort):
        run_import(db_session, tmp_path)

    count = run_import(db_session, tmp_path, force=True)
    assert count == 2
    index = crud.get_lesson_index(db_session)
    assert [l["title"] for l in index["초급"]] == ["A", "B"]
