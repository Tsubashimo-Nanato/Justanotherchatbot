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
    assert captures[0].ttl_seconds == 3 * 24 * 60 * 60


def test_memory_capture_keeps_explicit_memory_requests():
    captures = MemoryCapturePolicy().capture("remember blue means 114514")

    assert len(captures) == 1
    assert captures[0].kind == "fact"
    assert captures[0].summary == "blue means 114514"


def test_memory_capture_splits_chinese_explicit_mappings():
    captures = MemoryCapturePolicy().capture("我先记一下，蓝色代表114514，红色代表1919810。")

    assert [capture.summary for capture in captures] == [
        "蓝色 represents 114514",
        "红色 represents 1919810",
    ]
    assert all(capture.kind == "fact" for capture in captures)


def test_memory_capture_detects_chinese_dated_plan():
    captures = MemoryCapturePolicy().capture("我下午还要去学校，感觉很烦。")

    plan = next(capture for capture in captures if capture.kind == "plan")
    assert plan.scope == "episodic"
    assert plan.summary == "plans or current activity: 去学校"


def test_memory_capture_detects_chinese_short_term_status():
    captures = MemoryCapturePolicy().capture("我今天早上没吃饭，现在有点胃空。")

    assert len(captures) == 1
    assert captures[0].kind == "working_context"
    assert captures[0].scope == "short_term"
    assert "早上没吃饭" in captures[0].summary


def test_memory_capture_does_not_store_question_as_plan():
    captures = MemoryCapturePolicy().capture("我刚才说下午要去哪？")

    assert not any(capture.kind == "plan" for capture in captures)


def test_memory_capture_does_not_store_unpunctuated_chinese_questions():
    policy = MemoryCapturePolicy()

    messages = [
        "我刚才说下午要去哪",
        "如果我说我困死了，你会怎么接",
        "现在接一句像人说的话，不要只回一个字",
        "最后总结一下你刚刚记住了什么",
    ]

    for message in messages:
        captures = policy.capture(message)
        assert captures == []


def test_memory_capture_does_not_store_plain_chinese_meta_feedback():
    captures = MemoryCapturePolicy().capture("\u4e0d\u8981\u592a\u50cf\u5ba2\u670d\uff0c\u8bf4\u4eba\u8bdd")

    assert captures == []


def test_memory_capture_does_not_store_style_corrections_as_context():
    policy = MemoryCapturePolicy()

    messages = [
        "\u4f60\u522b\u5ffd\u7136\u5f00\u59cb\u8bb2\u65e7\u4e66\u5c01\u9762",
        "\u4f60\u8bf4\u8bdd\u80fd\u4e0d\u80fd\u522b\u8001\u50cf\u5728\u5199\u56de\u590d\u6a21\u677f",
        "\u4e0d\u8981\u5b89\u6170\u673a\u5668\u4eba\u90a3\u79cd\u8bed\u6c14",
    ]
    for message in messages:
        assert policy.capture(message) == []


def test_memory_capture_keeps_context_retention_instruction():
    captures = MemoryCapturePolicy().capture("\u8fd9\u4e2a\u4e0a\u4e0b\u6587\u8bb0\u4f4f\u4e09\u5929\u5dee\u4e0d\u591a\u5c31\u884c")

    assert len(captures) == 1
    assert captures[0].kind == "working_context"
    assert captures[0].ttl_seconds == 3 * 24 * 60 * 60


def test_memory_capture_does_not_store_plain_chinese_memory_question():
    captures = MemoryCapturePolicy().capture("\u521a\u521a\u90a3\u4e2a\u989c\u8272\u6570\u5b57\u8fd8\u8bb0\u5f97\u5417")

    assert captures == []
