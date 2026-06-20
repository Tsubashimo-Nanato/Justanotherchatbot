import json

from local_qq_agent.agent import PersonaGuard
from local_qq_agent.agent.style_learning import StyleAnchorDistiller, export_style_distillation_bundle
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


def test_project_persona_config_keeps_auto_distill_manual():
    persona = PersonaConfig.load()

    assert persona.style_learning_auto_distill is False


def test_style_anchor_distiller_reads_all_run_logs_by_default(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    run_log_dir = tmp_path / "run_logs"
    run_log_dir.mkdir()
    for index in range(7):
        (run_log_dir / f"run_log_{index}.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "kind": "group_message",
                            "sender": "Tsubashimo Nanato",
                            "text": f"sample {index}",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    output = tmp_path / "generated_style_anchor.md"
    result = StyleAnchorDistiller(store).distill(
        target_user="Tsubashimo Nanato",
        output_path=output,
        run_log_dir=run_log_dir,
    )

    text = output.read_text(encoding="utf-8")
    assert result.ok
    assert result.sample_count == 7
    assert "sample 0" in text
    assert "sample 6" in text


def test_style_distillation_bundle_filters_runtime_noise(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    store.append_event(
        source="Tsubashimo Nanato",
        kind="group_message",
        content="我今天吃了拉面",
        metadata={
            "sender_name": "Tsubashimo Nanato",
            "clean_text": "我今天吃了拉面 .detail",
            "window_title": "QQ noisy title",
            "prompt_tokens": 999,
        },
    )
    store.append_event(
        source="agent",
        kind="behavior_feedback",
        content="别把话聊死",
        metadata={
            "score_value": 0.25,
            "score_note": "别把话聊死",
            "raw_prompt": "hidden",
            "provider_trace": {"secret": "skip"},
        },
    )
    run_log_dir = tmp_path / "run_logs"
    run_log_dir.mkdir()
    (run_log_dir / "run_log_1.json").write_text(
        json.dumps(
            {
                "events": [
                    {
                        "kind": "group_message",
                        "sender": "Tsubashimo Nanato",
                        "text": "所以到底是什么面？？",
                        "window_title": "QQ",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "bundle.json"
    instruction = tmp_path / "style_distillation_handoff.md"

    result = export_style_distillation_bundle(
        store,
        target_user="Tsubashimo Nanato",
        output_path=output,
        instruction_path=instruction,
        run_log_dir=run_log_dir,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    raw_text = output.read_text(encoding="utf-8")

    assert result.ok
    assert result.event_count == 3
    assert payload["instruction_path"] == str(instruction)
    assert "我今天吃了拉面" in raw_text
    assert ".detail" not in raw_text
    assert "所以到底是什么面？？" in raw_text
    assert "window_title" not in raw_text
    assert "raw_prompt" not in raw_text
    assert "provider_trace" not in raw_text
