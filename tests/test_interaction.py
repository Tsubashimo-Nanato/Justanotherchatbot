from local_qq_agent.agent.interaction import InteractionPolicy
from local_qq_agent.agent.quality import QualityGate


def test_interaction_policy_gives_high_affinity_status_a_hook_budget():
    plan = InteractionPolicy().plan(
        message="我下班了",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    assert plan.mode == "acknowledge_plus_hook"
    assert plan.hook_budget == 2
    assert plan.message_kind == "life_status"


def test_interaction_policy_does_not_force_hook_for_low_affinity_ambient_status():
    plan = InteractionPolicy().plan(
        message="我下班了",
        social_snapshot={"affinity": 0.2},
        gate_metadata={"attention": "ambient"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=False,
    )

    assert plan.hook_budget == 0
    assert plan.mode == "minimal_or_no_extra"


def test_quality_gate_rewrites_dead_end_echo():
    plan = InteractionPolicy().plan(
        message="我下班了",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    review = QualityGate().review_rules(
        message="我下班了",
        reply="下班了啊",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "dead_end_echo" in review.rule_hits

