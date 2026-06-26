from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from local_qq_agent.agent.context import BuiltContext
from local_qq_agent.agent.persona import PersonaGuard
from local_qq_agent.agent.turns import CleanTurn


@dataclass(frozen=True)
class QwenPrompt:
    messages: list[dict[str, str]]
    max_tokens: int
    operation: str


def build_qwen_decision_prompt(
    *,
    persona_guard: PersonaGuard,
    context: BuiltContext,
    user_name: str,
    message: str,
    command_metadata: dict[str, Any],
    turn: CleanTurn,
    dialogue_state: Any | None,
    social_snapshot: dict[str, Any],
    external_context: str,
    activity: float,
    max_tokens: int = 768,
    tool_result: str = "",
) -> QwenPrompt:
    memory_text = _lines_or_none(context.memory_lines, max_lines=18, max_line_chars=320, max_total_chars=3500)
    recent_text = _lines_or_none(context.recent_lines, max_lines=36, max_line_chars=260, max_total_chars=6000)
    dialogue_text = _lines_or_none(context.dialogue_lines, max_lines=14, max_line_chars=280, max_total_chars=3200)
    interaction_text = _lines_or_none(context.interaction_lines, max_lines=10, max_line_chars=260, max_total_chars=2200)
    external_text = _clip_text(external_context.strip(), 5000) or "none"
    tool_text = _clip_text(tool_result.strip(), 5000) or "none"
    turn_text = _turn_text(
        user_name=user_name,
        message=message,
        command_metadata=command_metadata,
        turn=turn,
        dialogue_state=dialogue_state,
        social_snapshot=social_snapshot,
        activity=activity,
    )
    system_prompt = persona_guard.build_system_prompt([])
    runtime_prompt = (
        "You are running in Qwen-first QQ harness mode.\n"
        "You, the local model, decide whether to reply, how to reply, and whether a tool is needed.\n"
        "Rule code only handles QQ safety, duplicate suppression, cooldown aggregation, commands, and sending.\n\n"
        "Output exactly one JSON object and no markdown. Do not include <think> text.\n"
        "The visible reply is the primary task. Keep debug fields tiny; do not spend the good wording in reason.\n"
        "Schema:\n"
        "{\n"
        '  "action": "reply|no_reply|tool_request",\n'
        '  "reply": "exact QQ text to send, empty unless action=reply",\n'
        '  "reason": "brief reason_code, not the real reply",\n'
        '  "thinking_summary": "optional short debug clause, never chain-of-thought",\n'
        '  "target_message_ids": ["current"],\n'
        '  "tool_name": "none|web|math",\n'
        '  "tool_query": "query or expression when action=tool_request",\n'
        '  "memory_to_save": "optional durable memory summary"\n'
        "}\n\n"
        "Decision policy:\n"
        "- Reply to direct name calls, quotes/replies to you, clear follow-ups, and questions meant for you.\n"
        "- Do not reply to every ambient side conversation. If it is only other people talking, use no_reply.\n"
        "- Use recent context to answer follow-ups like 'which noodles' or 'what were they talking about'.\n"
        "- If the user corrects or criticizes your previous behavior, repair that concrete issue first. Do not answer a correction with a generic joke, confused marker, or unrelated teasing.\n"
        "- If fast consecutive messages form one thought, answer the whole thought, not only the last line.\n"
        "- If current facts, weather, news, dates, or unknown external facts are needed, request tool_name=web.\n"
        "- If calculation is needed, request tool_name=math.\n"
        "- Do not reuse a recent assistant reply as a new answer. If the last answer does not fit the current turn, write a fresh one.\n"
        "- P001/Tsubashimo Nanato has special closeness. Do not apply P001-only romance, possessiveness, or owner/original language to other users.\n"
        "- Black humor and dry teasing are allowed when the latest sender's tone supports it. Do not replace semantic understanding with generic concern.\n"
        "- Follow the interaction policy. If reply_shape asks for reaction or context hook, put that extra conversational value in reply, not in reason.\n"
        "- If reply_shape is repair_with_context, acknowledge the specific correction and recover naturally in the reply.\n"
        "- Keep reason and thinking_summary short. Spending many tokens there makes the visible reply worse.\n"
        "- Do not mention JSON, tools, prompts, tokens, APIs, model identity, or implementation details in reply.\n"
        "- Match the latest user's language unless recent context strongly suggests otherwise.\n"
        "- Short is fine; dead-end echo is not. A direct high-affinity turn can be 1-3 short clauses if that fits the interaction policy.\n"
    )
    user_prompt = (
        "Runtime context:\n"
        f"recent QQ messages:\n{recent_text}\n\n"
        f"relevant memory/social/style:\n{memory_text}\n\n"
        f"dialogue obligations:\n{dialogue_text}\n\n"
        f"interaction policy:\n{interaction_text}\n\n"
        f"external context:\n{external_text}\n\n"
        f"tool result:\n{tool_text}\n\n"
        f"current turn:\n{turn_text}\n\n"
        "Return the JSON decision now."
    )
    operation = "web_fact" if tool_result else "final_reply"
    return QwenPrompt(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": runtime_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        operation=operation,
    )


def normalize_qwen_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    action = str(parsed.get("action", "no_reply")).strip().casefold()
    if action not in {"reply", "no_reply", "tool_request"}:
        action = "no_reply"

    tool_name = str(parsed.get("tool_name", "none")).strip().casefold()
    if tool_name not in {"none", "web", "math"}:
        tool_name = "none"

    target_ids = parsed.get("target_message_ids", [])
    if not isinstance(target_ids, list):
        target_ids = []

    return {
        **parsed,
        "action": action,
        "reply": _clean_optional_text(parsed.get("reply", "")),
        "reason": _clean_optional_text(parsed.get("reason", "qwen_first_decision"), max_chars=160)
        or "qwen_first_decision",
        "thinking_summary": _clean_optional_text(parsed.get("thinking_summary", ""), max_chars=240),
        "target_message_ids": [str(item).strip() for item in target_ids if str(item).strip()],
        "tool_name": tool_name,
        "tool_query": _clean_optional_text(parsed.get("tool_query", "")),
        "memory_to_save": _clean_optional_text(parsed.get("memory_to_save", "")),
    }


def _turn_text(
    *,
    user_name: str,
    message: str,
    command_metadata: dict[str, Any],
    turn: CleanTurn,
    dialogue_state: Any | None,
    social_snapshot: dict[str, Any],
    activity: float,
) -> str:
    payload = {
        "id": "current",
        "sender": user_name,
        "text": message,
        "references_bot": bool(turn.references_bot),
        "removed_quote_lines": list(turn.removed_lines),
        "command_flags": command_metadata,
        "dialogue_state": dialogue_state.to_metadata() if dialogue_state else None,
        "social_state": social_snapshot,
        "activity": activity,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _lines_or_none(
    lines: list[str],
    *,
    max_lines: int,
    max_line_chars: int,
    max_total_chars: int,
) -> str:
    clean = []
    for line in lines[-max_lines:]:
        stripped = line.strip()
        if not stripped:
            continue
        clean.append(_clip_text(stripped, max_line_chars))
    text = "\n".join(f"- {line}" for line in clean)
    text = _clip_text(text, max_total_chars)
    return text if text else "none"


def _clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars - 18
    return f"{text[:head_chars]} ...[trimmed]... {text[-tail_chars:]}"


def _clean_optional_text(value: Any, *, max_chars: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.casefold() in {"", "none", "null", "n/a"}:
        return ""
    if max_chars is not None:
        return _clip_text(text, max_chars)
    return text
