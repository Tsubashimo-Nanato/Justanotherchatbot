from local_qq_agent.agent import PersonaGuard
from local_qq_agent.agent.style_learning import StyleAnchorDistiller
from local_qq_agent.config import PersonaConfig
from local_qq_agent.memory import SQLiteMemoryStore


def test_style_anchor_distiller_writes_generated_anchor(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="Tsubashimo Nanato",
        kind="group_message",
        content="所以到底是什么面？？？？",
        metadata={"sender_name": "Tsubashimo Nanato", "clean_text": "所以到底是什么面？？？？"},
    )
    store.append_event(
        source="Tsubashimo Nanato",
        kind="group_message",
        content="不是啊……问了就回答我",
        metadata={"sender_name": "Tsubashimo Nanato", "clean_text": "不是啊……问了就回答我"},
    )
    output = tmp_path / "generated_style_anchor.md"

    result = StyleAnchorDistiller(store).distill(
        target_user="Tsubashimo Nanato",
        output_path=output,
    )

    text = output.read_text(encoding="utf-8")
    assert result.ok
    assert result.sample_count == 2
    assert "# Generated Style Anchor" in text
    assert "所以到底是什么面？？？？" in text
    assert "punctuation patterns" in text
    assert "grammar pressure" in text


def test_persona_guard_loads_generated_style_anchor_as_profile_document(tmp_path):
    generated = tmp_path / "generated_style_anchor.md"
    generated.write_text("# Generated Style Anchor\n- use messy punctuation????", encoding="utf-8")
    persona = PersonaConfig(
        name="demo",
        language="zh-CN",
        summary="neutral test persona",
        style_rules=("stay concise",),
        ooc_triggers=(),
        fallback_reply="blocked",
        profile_documents=(generated,),
        style_learning_enabled=True,
        style_learning_target_user="Tsubashimo Nanato",
        style_learning_auto_distill=True,
        style_learning_generated_anchor_path=generated,
    )

    guard = PersonaGuard(persona)
    status = guard.profile_status()

    assert "use messy punctuation????" in guard.profile_text
    assert status["profile_document_count"] == 1
    assert status["style_learning"]["generated_anchor_path"] == str(generated)
