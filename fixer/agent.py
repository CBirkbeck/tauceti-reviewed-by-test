"""The model's part: Claude Opus 5.5 works on one review in the fixer's checkout with its tools, and ends with its
result as JSON.

The request: `claude-opus-5-5` (thinking is always on, so `thinking` is left out), effort `high` (its default is
`medium`), streamed, the prompt cached, the result's shape fixed by `output_config.format`, and the API's refusal
fallback on (`fallbacks: "default"`): the result records whichever model answered. The conversation only grows:
each turn's tool calls are run and their results sent back with the turn itself, thinking included. When the
review's budget is nearly spent the run says so, and on the last turn allowed, or once it is spent, tools are
withheld and the result asked for. A refusal, or a last answer that is not the result, gives none.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from answerer.model import FALLBACK_BETA, run_tool

from .tools import TOOLS

#: Dollars per million tokens, Claude Opus 5.5's (cache writes at 1.25 times input, for five minutes).
PRICES = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}

OUTCOMES = ["pr", "no_change", "already_addressed", "mathlib", "gave_up"]
RESULT = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": OUTCOMES},
        "summary": {"type": "string", "description": "One line on what you found and did, for the run's log."},
        "reply": {"type": "string", "description": "Posted on the review's issue, at most 120 words: what the pull "
                  "request changes; why nothing should change; or, for Mathlib, the change a person should propose "
                  "there. Empty for gave_up."},
        "pr_title": {"type": "string", "description": "For pr: the pull request's title, `feat:`, `fix:`, "
                     "`refactor:` or `docs:` and a short phrase, at most 72 characters. Else empty."},
        "pr_body": {"type": "string", "description": "For pr: the description: what changes and why, and what you "
                    "built and checked. No Roadmap line and no footer: the run adds them. Else empty."},
        "roadmap": {"type": "string", "description": "For pr: the roadmap area it chiefly concerns, one of those "
                    "listed, or none."},
        "existing_pr": {"type": "string", "description": "For already_addressed: the pull request that addresses it, "
                        "as owner/repo#N. Else empty."},
    },
    "required": ["outcome", "summary", "reply", "pr_title", "pr_body", "roadmap", "existing_pr"],
    "additionalProperties": False,
}

NEARLY = ("The budget for this review is nearly spent. Stop exploring: if your change builds, check it with "
          "show_diff and give your result; if it does not, give gave_up.")
FINAL = "Give your result now, as the JSON your instructions describe: no more tools."


class Tools(Protocol):
    def run(self, name: str, inp: dict) -> tuple[str, bool]: ...


@dataclass
class Result:
    result: dict | None
    cost: float
    model: str | None
    error: str | None
    turns: int


def price(u: Any) -> float:
    g = lambda k: getattr(u, k, 0) or 0  # noqa: E731
    return (g("input_tokens") * PRICES["input"] + g("output_tokens") * PRICES["output"] +
            g("cache_read_input_tokens") * PRICES["cache_read"] +
            g("cache_creation_input_tokens") * PRICES["cache_write"]) / 1e6


def text_turn(content: Any, text: str) -> list:
    """The pending user turn with `text` added after it (it is the turn about to be sent: no history changes)."""
    return (content if isinstance(content, list) else [{"type": "text", "text": content}]) + [{"type": "text", "text": text}]


def work(client: Any, cfg: Any, system: str, brief_text: str, tools: Tools, log: Any = None, schema: dict = RESULT,
         outcomes: list[str] = OUTCOMES) -> Result:
    """Runs the conversation for one review, or one round of its pull request's review (`schema`, `outcomes`:
    `follow.FOLLOW`); `cfg` has model, effort, max_tokens, max_turns, item_budget."""
    messages: list[dict] = [{"role": "user", "content": brief_text}]
    cost, model, warned = 0.0, None, False
    for turn in range(1, cfg.max_turns + 1):
        last = turn == cfg.max_turns or cost >= cfg.item_budget
        if last and turn > 1:
            messages[-1] = {"role": "user", "content": text_turn(messages[-1]["content"], FINAL)}
        elif not warned and turn > 1 and (cost >= 0.8 * cfg.item_budget or turn >= cfg.max_turns - 5):
            messages[-1] = {"role": "user", "content": text_turn(messages[-1]["content"], NEARLY)}
            warned = True
        kw: dict[str, Any] = dict(model=cfg.model, max_tokens=cfg.max_tokens, system=system, tools=TOOLS,
                                  messages=messages,
                                  output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": schema}},
                                  cache_control={"type": "ephemeral"}, betas=[FALLBACK_BETA], fallbacks="default")
        if last:
            kw["tool_choice"] = {"type": "none"}
        with client.beta.messages.stream(**kw) as stream:
            msg = stream.get_final_message()
        cost += price(msg.usage)
        model = getattr(msg, "model", None) or model
        if msg.stop_reason == "refusal":
            return Result(None, cost, model, "refused", turn)
        if msg.stop_reason in ("tool_use", "pause_turn") and not last:
            messages.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason == "tool_use":
                results = []
                for b in msg.content:
                    if getattr(b, "type", None) == "tool_use":
                        out, err = run_tool(tools, b.name, b.input)
                        if log:
                            log(f"  turn {turn}: {b.name}({brief_input(b.input)}){' failed' if err else ''}, ${cost:.2f} so far")
                        results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, "is_error": err})
                messages.append({"role": "user", "content": results})
            continue
        if msg.stop_reason != "end_turn":
            return Result(None, cost, model, f"stopped: {msg.stop_reason}", turn)
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
        try:
            result = json.loads(text)
        except ValueError:
            return Result(None, cost, model, "the last answer was not the result", turn)
        if not isinstance(result, dict) or result.get("outcome") not in outcomes:
            return Result(None, cost, model, "the last answer was not the result", turn)
        return Result(result, cost, model, None, turn)
    return Result(None, cost, model, "no result within the turns allowed", cfg.max_turns)


def brief_input(inp: Any) -> str:
    """A tool call's input, short, for the log."""
    if not isinstance(inp, dict):
        return ""
    parts = []
    for k, v in inp.items():
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        parts.append(f"{k}={s[:60]}{'…' if len(s) > 60 else ''}")
    return ", ".join(parts)
