from depscout.analyst import (
    _parse_response,
    _build_prompt,
    _filter_factual_errors,
)


def test_parse_response_strips_code_fences():
    raw = '```json\n[{"package": "foo", "title": "t", "body": "b", "category": "outdated"}]\n```'
    assert len(_parse_response(raw)) == 1


def test_parse_response_strips_think_tags():
    raw = '<think>reasoning</think>\n[{"package": "foo", "title": "t", "body": "b", "category": "outdated"}]'
    assert len(_parse_response(raw)) == 1


def test_parse_response_degrades_gracefully_on_bad_output():
    assert _parse_response("sorry I cannot help with that") == []


def test_filter_blocks_false_positive_outdated():
    deps = {"foo": {"current": "1.0.0", "latest": "1.0.0"}}
    insights = [{"package": "foo", "title": "t", "body": "b", "category": "outdated"}]
    assert _filter_factual_errors(insights, deps) == []


def test_prompt_shows_version_gap():
    deps = {"django": {"current": "3.2.0", "latest": "5.0.0"}}
    assert "3.2.0 → 5.0.0" in _build_prompt(deps)
