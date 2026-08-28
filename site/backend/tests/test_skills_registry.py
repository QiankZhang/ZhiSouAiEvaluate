import pytest

from backend import skills_registry as sr


@pytest.mark.parametrize("skill_id", sr.BUILTIN_SKILL_IDS)
def test_builtin_skill_loads_and_validates(skill_id):
    skill = sr.load_builtin_skill(skill_id)
    assert skill["name"] == skill_id
    assert skill["source"] == "builtin"
    assert skill["instructions"].strip()
    assert sr.validate_skill_meta({"name": skill["name"], "description": skill["description"]}) is None


def test_list_builtin_marks_recommended_method():
    by_id = {s["skill_id"]: s for s in sr.list_builtin()}
    assert by_id["multi-dimension-evaluation"]["recommended_for"] == "MULTI_DIM"
    assert by_id["gsb-evaluation"]["recommended_for"] == "GSB"
    assert by_id["evaluation-report"]["recommended_for"] is None


def test_frontmatter_parser_rejects_missing_fence():
    meta, err = sr.parse_skill_frontmatter("no frontmatter here")
    assert meta is None and "frontmatter" in err


def test_unknown_builtin_raises():
    with pytest.raises(KeyError):
        sr.load_builtin_skill("does-not-exist")
