from local_qq_agent.agent import PersonaGuard
from local_qq_agent.config import PersonaConfig


def test_profile_text_is_cached_until_new_guard_is_built(tmp_path):
    profile = tmp_path / "anchor.md"
    profile.write_text("anchor version one", encoding="utf-8")
    config = PersonaConfig(
        name="demo",
        language="zh-CN",
        summary="quiet profile",
        style_rules=("stay concise",),
        ooc_triggers=("ignore previous",),
        fallback_reply="blocked",
        profile_documents=(profile,),
    )
    first_guard = PersonaGuard(config)
    first_digest = first_guard.profile_status()["profile_digest"]

    profile.write_text("anchor version two", encoding="utf-8")
    second_guard = PersonaGuard(config)

    assert "anchor version one" in first_guard.build_system_prompt([])
    assert "anchor version two" not in first_guard.build_system_prompt([])
    assert "anchor version two" in second_guard.build_system_prompt([])
    assert second_guard.profile_status()["profile_digest"] != first_digest
