from local_qq_agent.agent.engagement import EngagementPolicy, EngagementSignals


def test_engagement_direct_address_bypasses_activity_sampling():
    policy = EngagementPolicy()

    decision = policy.decide(
        activity=0.0,
        user_affinity=0.2,
        global_affinity=0.5,
        mood_label="neutral",
        mood_intensity=0.0,
        directness="direct_address",
        signals=EngagementSignals(topic_interest=0.2, interruption_risk=0.8),
        turn_key="turn-1",
        model_action="no_reply",
        model_reason="model_was_unsure",
    )

    assert decision.action == "reply"
    assert decision.reply_probability == 1.0
    assert decision.roll is None


def test_engagement_ambient_uses_stable_roll_and_probability():
    policy = EngagementPolicy()

    first = policy.decide(
        activity=0.35,
        user_affinity=0.5,
        global_affinity=0.5,
        mood_label="neutral",
        mood_intensity=0.0,
        directness="ambient",
        signals=EngagementSignals(topic_interest=0.5, interruption_risk=0.35, is_shared_context=True),
        turn_key="same-turn",
        model_action="reply",
        model_reason="ambient_candidate",
    )
    second = policy.decide(
        activity=0.35,
        user_affinity=0.5,
        global_affinity=0.5,
        mood_label="neutral",
        mood_intensity=0.0,
        directness="ambient",
        signals=EngagementSignals(topic_interest=0.5, interruption_risk=0.35, is_shared_context=True),
        turn_key="same-turn",
        model_action="reply",
        model_reason="ambient_candidate",
    )

    assert first.roll == second.roll
    assert first.reply_probability == second.reply_probability


def test_spontaneous_target_is_capped_at_two_per_hour():
    policy = EngagementPolicy()

    target = policy.spontaneous_target_per_hour(
        activity=1.0,
        global_affinity=1.0,
        mood_label="playful",
        mood_intensity=1.0,
        context_interest=1.0,
    )

    assert target == 2.0
