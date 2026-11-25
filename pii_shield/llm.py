"""Send text to Claude without sending the PII in it.

The flow is the one PathReview's architecture describes but never wires up:

    user text --scrub(typed)--> "[PHONE_1]" text --> LLM --> reply --restore--> user

The model sees placeholders, never the real values. Because the placeholders are typed
and numbered, the model can still write "call [PHONE_1]" and the restored reply reads
naturally. If ``ANTHROPIC_API_KEY`` is not set, ``guarded_complete`` can run as a dry
run that returns exactly the prompt that would have been sent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pii_shield.scrubber import PLACEHOLDER, Shield

DEFAULT_MODEL = os.environ.get("PII_SHIELD_MODEL", "claude-haiku-5-5")

PROMPT_TEMPLATE = """{instruction}

<document>
{document}
</document>

Personal details in the document were replaced with placeholders such as [PHONE_1] or
[EMAIL_1] before it reached you. If you refer to one of them, copy the placeholder exactly
as written; do not guess or invent the real value."""


@dataclass
class GuardedResult:
    prompt: str  # exactly what the model saw (or would see, in a dry run)
    detections: list[dict]
    mapping: dict[str, str]
    model_reply: str | None = None  # the model's reply, still containing placeholders
    reply: str | None = None  # the reply with real values restored
    dry_run: bool = False
    unknown_placeholders: list[str] = field(default_factory=list)


def build_prompt(text: str, instruction: str, shield: Shield | None = None):
    shield = shield or Shield()
    scrubbed = shield.scrub(text, mode="typed")
    prompt = PROMPT_TEMPLATE.format(instruction=instruction.strip(), document=scrubbed.text)
    return prompt, scrubbed


def guarded_complete(
    text: str,
    instruction: str,
    *,
    client=None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 800,
    dry_run: bool | None = None,
    shield: Shield | None = None,
) -> GuardedResult:
    """Scrub ``text``, ask the model, and restore PII in its reply.

    ``client`` is anything with ``messages.create(...)`` shaped like the Anthropic SDK,
    which keeps this testable without a network call. With no client and no API key the
    call becomes a dry run unless ``dry_run=False`` is passed explicitly.
    """
    shield = shield or Shield()
    prompt, scrubbed = build_prompt(text, instruction, shield)
    result = GuardedResult(prompt=prompt, detections=scrubbed.detections, mapping=scrubbed.mapping)

    if dry_run is None:
        dry_run = client is None and not os.environ.get("ANTHROPIC_API_KEY")
    if dry_run:
        result.dry_run = True
        return result

    if client is None:
        import anthropic  # imported lazily so the scrubber itself has no dependencies

        client = anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    model_reply = "".join(
        getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"
    )
    result.model_reply = model_reply
    result.reply = shield.restore(model_reply, scrubbed.mapping)
    result.unknown_placeholders = sorted(
        {m.group(0) for m in PLACEHOLDER.finditer(model_reply) if m.group(0) not in scrubbed.mapping}
    )
    return result
