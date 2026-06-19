from local_qq_agent.agent.memory_capture import MemoryCapturePolicy


def test_memory_capture_detects_preference():
    captures = MemoryCapturePolicy().capture("I love eating pasta")

    assert len(captures) == 1
    assert captures[0].kind == "preference"
    assert captures[0].summary == "likes: eating pasta"
    assert captures[0].scope == "long_term"


def test_memory_capture_detects_dated_plan():
    captures = MemoryCapturePolicy().capture("I am going to the doctors today")

    assert len(captures) == 1
    assert captures[0].kind == "plan"
    assert captures[0].scope == "episodic"
    assert "doctors today" in captures[0].summary


def test_memory_capture_detects_short_term_meal_context():
    captures = MemoryCapturePolicy().capture("I had curry for dinner")

    assert len(captures) == 1
    assert captures[0].kind == "working_context"
    assert captures[0].scope == "short_term"
    assert captures[0].summary == "recent personal context: curry for dinner"


def test_memory_capture_keeps_explicit_memory_requests():
    captures = MemoryCapturePolicy().capture("remember blue means 114514")

    assert len(captures) == 1
    assert captures[0].kind == "fact"
    assert captures[0].summary == "blue means 114514"
