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


def test_interaction_policy_classifies_bot_correction_as_repair():
    plan = InteractionPolicy().plan(
        message="你刚才@错了",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "followup"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=True,
    )

    assert plan.message_kind == "correction"
    assert plan.mode == "repair_context"
    assert plan.reply_shape == "repair_with_context"
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


def test_interaction_policy_classifies_plain_chinese_meta_feedback_as_correction():
    plan = InteractionPolicy().plan(
        message="\u4e0d\u8981\u592a\u50cf\u5ba2\u670d\uff0c\u8bf4\u4eba\u8bdd",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    assert plan.message_kind == "correction"
    assert plan.reply_shape == "repair_with_context"


def test_quality_gate_rewrites_plain_chinese_ack_when_hook_is_expected():
    plan = InteractionPolicy().plan(
        message="\u90a3\u4f60\u73b0\u5728\u522b\u53ea\u56de\u4e00\u53e5\uff0c\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    review = QualityGate().review_rules(
        message="\u90a3\u4f60\u73b0\u5728\u522b\u53ea\u56de\u4e00\u53e5\uff0c\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
        reply="\u55ef\uff0c\u77e5\u9053\u4e86\u3002",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "dead_end_without_hook" in review.rule_hits


def test_quality_gate_rewrites_future_promise_for_plain_style_repair():
    plan = InteractionPolicy().plan(
        message="\u90a3\u4f60\u73b0\u5728\u522b\u53ea\u56de\u4e00\u53e5\uff0c\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "direct"},
        dialogue_state=None,
        direct_address=True,
        reply_to_bot=False,
    )

    review = QualityGate().review_rules(
        message="\u90a3\u4f60\u73b0\u5728\u522b\u53ea\u56de\u4e00\u53e5\uff0c\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
        reply="\u77e5\u9053\u4e86\uff0c\u4e0b\u6b21\u4e0d\u53ea\u56de\u4e00\u53e5\u3002",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unrepaired_correction" in review.rule_hits

    second = QualityGate().review_rules(
        message="\u90a3\u4f60\u73b0\u5728\u522b\u53ea\u56de\u4e00\u53e5\uff0c\u63a5\u4e00\u53e5\u81ea\u7136\u7684",
        reply="\u77e5\u9053\u4e86\uff0c\u4e0b\u56de\u4e0d\u53ea\u56de\u4e00\u4e2a\u5b57\u3002",
        interaction_plan=plan,
    )

    assert second.send_allowed
    assert second.rewrite_needed
    assert "unrepaired_correction" in second.rule_hits


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


def test_quality_gate_rewrites_correction_that_gets_dodged():
    plan = InteractionPolicy().plan(
        message="你刚才@错了",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "followup"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=True,
    )

    review = QualityGate().review_rules(
        message="你刚才@错了",
        reply="？？？你刚才@错了，还活着呢。",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unrepaired_correction" in review.rule_hits


def test_quality_gate_accepts_concrete_correction_repair():
    plan = InteractionPolicy().plan(
        message="你刚才@错了",
        social_snapshot={"affinity": 1.0},
        gate_metadata={"attention": "followup"},
        dialogue_state=None,
        direct_address=False,
        reply_to_bot=True,
    )

    review = QualityGate().review_rules(
        message="你刚才@错了",
        reply="嗯，刚才引用接错了，不该把那句算到你头上。",
        interaction_plan=plan,
    )

    assert review.send_allowed
    assert not review.rewrite_needed


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


def test_quality_gate_rewrites_parenthetical_stage_direction():
    review = QualityGate().review_rules(
        message="what were those two colors",
        reply="red is 1919810, blue is 114514. (looks at the screen)",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "stage_direction" in review.rule_hits


def test_quality_gate_rewrites_offscreen_self_claim():
    review = QualityGate().review_rules(
        message="what should I eat today?",
        reply="I should go eat ramen too.",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "offscreen_self_claim" in review.rule_hits


def test_quality_gate_rewrites_overconfident_retention():
    review = QualityGate().review_rules(
        message="\u8981\u662f\u4e09\u5929\u540e\u6211\u8fd8\u95ee\u5462",
        reply="\u4e09\u5929\u540e\u4f60\u95ee\uff0c\u6211\u8fd8\u8bb0\u5f97\u3002",
        interaction_plan=None,
    )

    assert review.rewrite_needed
    assert "overconfident_retention" in review.rule_hits


def test_quality_gate_rewrites_unrelated_memory_attachment():
    review = QualityGate().review_rules(
        message="\u6211\u521a\u5403\u4e86\u62c9\u9762\uff0c\u80c3\u6709\u70b9\u9876",
        reply="\u62c9\u9762\u80c3\u9876\u4e86\u8fd8\u8bb0\u84dd\u8272\u662f114514\uff0c\u7ea2\u8272\u662f1919810\uff0c\u4f60\u8fd9\u8bb0\u6cd5\u633a\u6709\u4eea\u5f0f\u611f\u3002",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unrelated_memory_attachment" in review.rule_hits


def test_quality_gate_allows_relevant_memory_answer():
    review = QualityGate().review_rules(
        message="\u90a3\u84dd\u8272\u662f\u591a\u5c11",
        reply="\u84dd\u8272\u662f114514\u3002",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert not review.rewrite_needed
    assert "unrelated_memory_attachment" not in review.rule_hits


def test_interaction_policy_treats_style_controls_as_corrections():
    policy = InteractionPolicy()

    messages = [
        "\u4f46\u4f60\u4e0d\u8981\u5ffd\u7136\u5f00\u59cb\u8bb2\u65e7\u4e66\u5c01\u9762",
        "\u4f60\u8bf4\u8bdd\u80fd\u4e0d\u80fd\u522b\u8001\u50cf\u5728\u5199\u56de\u590d\u6a21\u677f",
        "\u8fd9\u4e2a\u4e0a\u4e0b\u6587\u8bb0\u4f4f\u4e09\u5929\u5dee\u4e0d\u591a\u5c31\u884c",
    ]

    for message in messages:
        assert policy._message_kind(message) == "correction"


def test_quality_gate_rewrites_unprovided_scene_detail():
    review = QualityGate().review_rules(
        message="say one more human sentence",
        reply="The convenience store downstairs still has its light on.",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unprovided_scene_detail" in review.rule_hits


def test_quality_gate_rewrites_invented_yesterday_food_scene():
    review = QualityGate().review_rules(
        message="\u4e0b\u5348\u8fd8\u5f97\u53bb\u5b66\u6821\uff0c\u60f3\u9003",
        reply="\u4e0b\u5348\u8fd8\u5f97\u53bb\u5b66\u6821\uff0c\u60f3\u9003\u3002\u6211\u4e00\u6478\u53e3\u888b\uff0c\u53d1\u73b0\u94b1\u5305\u91cc\u53ea\u5269\u534a\u5757\u997c\u5e72\uff0c\u8fd8\u662f\u6628\u5929\u7684\u3002",
        interaction_plan=None,
    )

    assert review.send_allowed
    assert review.rewrite_needed
    assert "unprovided_scene_detail" in review.rule_hits


def test_quality_gate_can_strip_parenthetical_aside():
    cleaned = QualityGate().strip_parenthetical_asides("red is 1919810. (looks at the screen)")

    assert cleaned == "red is 1919810."


def test_quality_gate_can_strip_unprovided_scene_detail():
    reply = "\u4e0b\u5348\u8fd8\u5f97\u53bb\u5b66\u6821\uff0c\u60f3\u9003\n\u90a3\u6211\u731c\u4f60\u4e66\u5305\u91cc\u8fd8\u8eba\u7740\u6628\u5929\u6ca1\u5199\u7684\u4f5c\u4e1a\uff1f"

    cleaned = QualityGate().strip_unprovided_scene_details(reply)

    assert cleaned == "\u4e0b\u5348\u8fd8\u5f97\u53bb\u5b66\u6821\uff0c\u60f3\u9003"


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
