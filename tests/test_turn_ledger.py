from local_qq_agent.server.turn_ledger import TurnLedger


def test_turn_ledger_blocks_same_turn_while_queued_inflight_and_completed():
    ledger = TurnLedger(ttl_seconds=3600)
    turn_id = "sender|hello"

    ledger.observe(
        turn_id=turn_id,
        sender="sender",
        clean_text="hello",
        raw_text="hello",
        fingerprint="fp-1",
        references_bot=False,
    )
    assert ledger.can_enqueue(turn_id, "fp-1")

    ledger.mark_queued(turn_id)
    assert not ledger.can_enqueue(turn_id, "fp-coordinate-shift")

    ledger.mark_inflight(turn_id)
    assert not ledger.can_enqueue(turn_id, "fp-refresh")

    ledger.mark_completed(turn_id)
    assert not ledger.can_enqueue(turn_id, "fp-after-send")


def test_turn_ledger_adds_alias_without_reopening_completed_turn():
    ledger = TurnLedger(ttl_seconds=3600)
    turn_id = "sender|nanato revive"
    ledger.observe(
        turn_id=turn_id,
        sender="sender",
        clean_text="nanato revive",
        raw_text="nanato revive",
        fingerprint="fp-original",
        references_bot=False,
    )
    ledger.mark_completed(turn_id)

    ledger.observe(
        turn_id=turn_id,
        sender="sender",
        clean_text="nanato revive",
        raw_text="old bot quote\nnanato revive",
        fingerprint="fp-quote-merge",
        references_bot=True,
    )

    assert not ledger.can_enqueue(turn_id, "fp-quote-merge")
    assert ledger.record_for(turn_id).state == "completed"


def test_turn_ledger_allows_different_clean_turn():
    ledger = TurnLedger(ttl_seconds=3600)
    first = "sender|hello"
    second = "sender|different"
    ledger.observe(
        turn_id=first,
        sender="sender",
        clean_text="hello",
        raw_text="hello",
        fingerprint="fp-1",
        references_bot=False,
    )
    ledger.mark_completed(first)
    ledger.observe(
        turn_id=second,
        sender="sender",
        clean_text="different",
        raw_text="different",
        fingerprint="fp-2",
        references_bot=False,
    )

    assert ledger.can_enqueue(second, "fp-2")


def test_turn_ledger_tracks_wait_and_answer_outputs_once():
    ledger = TurnLedger(ttl_seconds=3600)
    turn_id = "sender|hello"
    ledger.observe(
        turn_id=turn_id,
        sender="sender",
        clean_text="hello",
        raw_text="hello",
        fingerprint="fp-1",
        references_bot=False,
    )

    assert ledger.can_send_wait(turn_id, "fp-1")
    ledger.mark_wait_attempted(turn_id, text="one moment")
    assert not ledger.can_send_wait(turn_id, "fp-1")
    ledger.mark_wait_result(turn_id, sent=True, result={"sent": True, "reason": "sent"})

    assert ledger.can_send_answer(turn_id, "fp-1")
    ledger.mark_answer_result(turn_id, sent=True, result={"sent": True, "reason": "sent"}, text="final")
    assert not ledger.can_send_answer(turn_id, "fp-1")

    summary = ledger.summary()
    assert summary["response_counts"] == {
        "wait_attempted": 1,
        "wait_sent": 1,
        "answer_attempted": 1,
        "answer_sent": 1,
    }
