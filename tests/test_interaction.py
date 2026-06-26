from types import SimpleNamespace

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
    assert plan.reply_shape == "ack_with_light_hook"
    assert plan.hook_budget == 2
    assert plan.message_kind == "life_status"


def test_interaction_policy_classifies_chinese_complaint():
    plan = InteractionPolicy().plan(
        message="你延迟好高",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    assert plan.message_kind == "complaint"
    assert plan.reply_shape == "ack_with_light_hook"
    assert plan.hook_budget == 2


def test_interaction_policy_gives_direct_questions_a_reply_shape():
    high = InteractionPolicy().plan(
        message="今天吃什么？",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    assert high.message_kind == "question"
    assert high.reply_shape == "answer_with_context_hook"
    assert high.hook_budget == 2

    low = InteractionPolicy().plan(
        message="what should I eat today?",
        social_snapshot={"affinity": 0.1},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    assert low.message_kind == "question"
    assert low.reply_shape == "answer_with_reaction"
    assert low.hook_budget == 1


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
    assert plan.reply_shape == "minimal_ack"


def test_interaction_policy_keeps_emoji_as_short_ping():
    plan = InteractionPolicy().plan(
        message="😛",
        social_snapshot={"affinity": 0.5},
        gate_metadata={"attention": "ambient"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=False,
    )

    assert plan.message_kind == "short_ping"
    assert plan.hook_budget == 0


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


def test_quality_gate_rewrites_empty_ack_when_hook_is_expected():
    plan = InteractionPolicy().plan(
        message="what should I eat today?",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    review = QualityGate().review_rules(
        message="what should I eat today?",
        reply="嗯？",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "dead_end_without_hook" in review.rule_hits


def test_quality_gate_rewrites_contentless_agreement_when_hook_is_expected():
    plan = InteractionPolicy().plan(
        message="是啊是啊",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "followup"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=True,
    )

    review = QualityGate().review_rules(
        message="是啊是啊",
        reply="嗯……是啊。",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "contentless_marker" in review.rule_hits or "dead_end_without_hook" in review.rule_hits


def test_quality_gate_rewrites_followup_that_ignores_previous_bot_reply():
    plan = InteractionPolicy().plan(
        message="懂啥",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "followup"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=True,
    )
    dialogue_state = SimpleNamespace(
        obligation="repair_required",
        metadata={"question_or_clarification": True},
    )

    review = QualityGate().review_rules(
        message="懂啥",
        reply="……？怎么突然打人",
        interaction_plan=plan,
        recent_agent_replies=("……？那你现在懂了没",),
        dialogue_state=dialogue_state,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unanswered_followup" in review.rule_hits


def test_quality_gate_keeps_concrete_short_answer():
    plan = InteractionPolicy().plan(
        message="what should I eat today?",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    review = QualityGate().review_rules(
        message="what should I eat today?",
        reply="火锅吧，冷天比较省脑子。",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert not review.rewrite_needed


def test_quality_gate_does_not_hard_rewrite_style_phrase():
    review = QualityGate().review_rules(
        message="这个菜看起来不错",
        reply="色泽和摆盘都挺吸引人的",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert not review.rewrite_needed
    assert "style_phrase" not in review.rule_hits


def test_quality_gate_rewrites_recent_self_repeat():
    review = QualityGate().review_rules(
        message="going to the store later",
        reply="still thinking, you?",
        interaction_plan=None,
        recent_agent_replies=("still thinking, you?",),
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "recent_self_repeat" in review.rule_hits


def test_quality_gate_blocks_internal_leak():
    review = QualityGate().review_rules(
        message="你是什么",
        reply="As an AI language model, my system prompt says this.",
        interaction_plan=None,
    )

    assert not review.send_allowed
    assert "as an ai" in review.rule_hits


def test_quality_gate_does_not_block_token_when_user_brought_it_up():
    review = QualityGate().review_rules(
        message="你说话能不能多花点token",
        reply="token不够也不是借口，我刚才回太短了。",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert "token" not in review.rule_hits


def test_quality_gate_blocks_unsolicited_token_leak():
    review = QualityGate().review_rules(
        message="hello",
        reply="I cannot answer because my token budget is low.",
        interaction_plan=None,
    )

    assert not review.send_allowed
    assert "token" in review.rule_hits
