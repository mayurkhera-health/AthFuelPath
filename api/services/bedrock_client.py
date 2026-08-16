"""AWS Bedrock Converse API client for AthFuelPath AI calls."""
import base64
import json
import os
import re

import boto3
from botocore.config import Config

DEFAULT_BEDROCK_MODEL = "mistral.ministral-3-8b-instruct"
DEFAULT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"


def _region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def model_id() -> str:
    return os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL)


def embed_model_id() -> str:
    return os.getenv("BEDROCK_EMBED_MODEL_ID", DEFAULT_EMBED_MODEL)


def _bedrock_config() -> Config:
    # max_attempts is TOTAL attempts in "standard" mode → 2 means one retry.
    # Standard mode retries only transient errors (throttling, 5xx, timeouts).
    return Config(
        read_timeout=30,
        connect_timeout=10,
        retries={"max_attempts": 2, "mode": "standard"},
    )


def _client():
    return boto3.client(
        "bedrock-runtime",
        region_name=_region(),
        config=_bedrock_config(),
    )


def is_configured() -> bool:
    """True when default AWS credential chain is likely available."""
    return bool(
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
        or os.getenv("AWS_ROLE_ARN")
    )


def extract_json(text: str) -> str:
    raw = text.strip()
    if raw.startswith("{") or raw.startswith("["):
        return raw
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        return raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        return match.group(1).strip()
    return raw


def _sanitize_json_string_literals(json_str: str) -> str:
    """Escape raw newlines/tabs/control chars inside JSON string literals."""
    result: list[str] = []
    in_string = False
    escaped = False

    for ch in json_str:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == "\\":
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            if ord(ch) < 32:
                continue
        result.append(ch)

    return "".join(result)


def parse_json_from_llm(text: str):
    """Parse JSON from an LLM response, repairing common formatting mistakes."""
    raw = extract_json(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_sanitize_json_string_literals(raw))


def _extract_text(response: dict) -> str:
    content = response.get("output", {}).get("message", {}).get("content") or []
    text = "".join(block.get("text", "") for block in content if "text" in block).strip()
    if not text:
        raise RuntimeError("Bedrock returned empty response")
    return text


def _anthropic_converse(
    *,
    user: str,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Fallback: Anthropic Claude when AWS Bedrock credentials are absent."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs: dict = {
        "model": os.getenv("ANTHROPIC_COACH_MODEL", "claude-haiku-4-5-20251001"),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    return msg.content[0].text


def converse_text(
    *,
    user: str,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    model: str | None = None,
) -> str:
    if not is_configured():
        return _anthropic_converse(user=user, system=system, max_tokens=max_tokens, temperature=temperature)
    kwargs: dict = {
        "modelId": model or model_id(),
        "messages": [{"role": "user", "content": [{"text": user}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    return _extract_text(_client().converse(**kwargs))


def _anthropic_converse_multi_turn(
    *,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Fallback: Anthropic Claude for multi-turn conversations when AWS Bedrock is absent."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs: dict = {
        "model": os.getenv("ANTHROPIC_COACH_MODEL", "claude-haiku-4-5-20251001"),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
    }
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    return msg.content[0].text


def converse_multi_turn(
    *,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    model: str | None = None,
) -> str:
    """Send a multi-turn conversation. Each message: {"role": "user"|"assistant", "content": "..."}."""
    if not is_configured():
        return _anthropic_converse_multi_turn(
            messages=messages, system=system, max_tokens=max_tokens, temperature=temperature
        )
    bedrock_messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in messages
    ]
    kwargs: dict = {
        "modelId": model or model_id(),
        "messages": bedrock_messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    try:
        return _extract_text(_client().converse(**kwargs))
    except Exception:
        return _anthropic_converse_multi_turn(
            messages=messages, system=system, max_tokens=max_tokens, temperature=temperature
        )


def converse_vision(
    *,
    prompt: str,
    image_base64: str,
    media_type: str = "image/jpeg",
    max_tokens: int = 1024,
    temperature: float = 0.2,
    model: str | None = None,
) -> str:
    fmt = "png" if media_type == "image/png" else "jpeg"
    response = _client().converse(
        modelId=model or model_id(),
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {
                        "image": {
                            "format": fmt,
                            "source": {"bytes": base64.b64decode(image_base64)},
                        }
                    },
                ],
            }
        ],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    return _extract_text(response)


def embed_text(text: str, *, model: str | None = None) -> list[float]:
    """Return a dense embedding vector for semantic retrieval."""
    trimmed = (text or "").strip()
    if not trimmed:
        raise ValueError("Cannot embed empty text")

    response = _client().invoke_model(
        modelId=model or embed_model_id(),
        body=json.dumps({"inputText": trimmed[:8000]}),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    vector = payload.get("embedding")
    if not vector:
        raise RuntimeError("Bedrock embedding response missing 'embedding'")
    return vector
