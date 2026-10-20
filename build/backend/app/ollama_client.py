"""
Thin wrapper around a local Ollama server running qwen3:1.7b, with a
tool-calling loop so the assistant answers using real data from the
database/dashboard instead of making things up.

Small local models (qwen3:1.7b is ~1.7B params) are not reliable at
*choosing* to emit a tool call - plenty of the time they'll just answer
directly from "vibes" instead (this is exactly how we ended up with a
hallucinated "1234 items staged" when the real number was 1). Tool-calling
alone is not a robust grounding strategy for a model this small.

So in addition to giving the model tools it *can* call, every request also
gets a "Current warehouse data" block injected straight into the system
prompt with real numbers pulled fresh from the DB - dashboard stats,
offline gateways, and recent movements - plus a direct, regex-based box
lookup if the message looks like it mentions one. This means the model has
grounded, current numbers sitting right in front of it whether or not it
ever calls a tool, which is what actually fixes the hallucination rather
than just making it less likely.

Flow:
  1. Gather baseline context (always) + a direct box lookup (if the
     message looks like it names one) and inject it into the system prompt.
  2. Send the user message + conversation history + tool schemas to Ollama,
     in case the model wants to look up something more specific (e.g. a
     particular zone) not covered by the baseline context.
  3. If the model returns tool_calls, execute each against the DB and feed
     the results back as `role: tool` messages.
  4. Repeat until the model answers with plain content (or we hit the
     round cap), then return that as the reply.

If Ollama isn't reachable (not installed / not running / model not pulled),
we fail soft with a clear, friendly message rather than crashing the chat.
"""
import json
import logging
import re

import httpx
from sqlalchemy.orm import Session

from . import ai_tools
from .config import settings

logger = logging.getLogger("smart_warehouse.ollama")

SYSTEM_PROMPT = (
    "You are the Warehouse AI assistant embedded in the Smart Warehouse Rack "
    "Management System dashboard. You help warehouse staff find boxes, check "
    "operational stats, and understand device health.\n\n"
    "A 'Current warehouse data' JSON block is provided below with real, "
    "live numbers pulled from the database moments ago. Treat it as the "
    "single source of truth: always use those exact numbers when answering "
    "questions about item counts, offline devices, or recent activity - "
    "never state a different number, and never invent one. If a question "
    "needs something not covered by that block (e.g. details about a "
    "specific zone), use the provided tools to look it up rather than "
    "guessing. If a box isn't in the data and no tool finds it either, say "
    "so plainly instead of making up a location.\n\n"
    "Keep answers short (1-3 sentences) and concrete, in a practical, "
    "warehouse-floor tone. When you locate a specific box, mention its zone "
    "and rack clearly so the UI can offer to jump to it on the live map."
)

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# Heuristic box-id spotter, e.g. BOX-9928, REAL-BOX-1, ZMOD-4491-B7 style
# tokens - a dash-joined run ending in a group with a digit.
_BOX_ID_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")


def _strip_thinking(text: str) -> str:
    return _THINK_TAG_RE.sub("", text or "").strip()


def _build_context_block(db: Session, user_message: str) -> tuple[str, str | None]:
    """Always-fetched grounding data + a best-effort direct box lookup.
    Returns (context_json_text, located_box_id_or_None)."""
    context: dict = {
        "dashboard_stats": ai_tools.get_dashboard_stats(db),
        "offline_gateways": ai_tools.list_offline_devices(db),
        "recent_movements": ai_tools.get_recent_movements(db, limit=5),
    }

    located_box_id: str | None = None
    for candidate in _BOX_ID_RE.findall(user_message):
        result = ai_tools.locate_box(db, candidate)
        if result.get("found"):
            context["located_box_lookup"] = result
            if result.get("zoneId"):
                located_box_id = result.get("boxId")
            break
    else:
        if _BOX_ID_RE.search(user_message):
            # Mentioned something box-id-shaped but nothing matched.
            context["located_box_lookup"] = {"found": False, "note": "no matching box for the id(s) mentioned"}

    return json.dumps(context, default=str, indent=2), located_box_id


async def is_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def chat(db: Session, user_message: str, history: list[dict] | None = None) -> dict:
    """
    Returns: {"reply": str, "action": dict|None, "usedTools": [str], "modelReachable": bool}
    """
    context_json, located_box = _build_context_block(db, user_message)
    system_content = f"{SYSTEM_PROMPT}\n\nCurrent warehouse data (authoritative, fetched just now):\n{context_json}"

    messages = [{"role": "system", "content": system_content}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message})

    used_tools: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT_SEC) as client:
            for _ in range(settings.OLLAMA_MAX_TOOL_ROUNDS):
                resp = await client.post(
                    f"{settings.OLLAMA_HOST}/api/chat",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "messages": messages,
                        "tools": ai_tools.TOOL_SCHEMAS,
                        "stream": False,
                        "think": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                message = data.get("message", {})
                tool_calls = message.get("tool_calls") or []

                if not tool_calls:
                    reply = _strip_thinking(message.get("content", ""))
                    action = {"type": "locate_box", "boxId": located_box} if located_box else None
                    return {
                        "reply": reply or "I couldn't come up with an answer for that - could you rephrase?",
                        "action": action,
                        "usedTools": used_tools,
                        "modelReachable": True,
                    }

                # The model wants to call one or more tools.
                messages.append(message)
                for call in tool_calls:
                    fn = call.get("function", {})
                    name = fn.get("name")
                    args = fn.get("arguments") or {}
                    used_tools.append(name)

                    impl = ai_tools.TOOL_IMPLEMENTATIONS.get(name)
                    if not impl:
                        result = {"error": f"Unknown tool '{name}'"}
                    else:
                        try:
                            result = impl(db, **args)
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Tool '%s' failed", name)
                            result = {"error": str(exc)}

                    if name == "locate_box" and result.get("found") and result.get("zoneId"):
                        located_box = result.get("boxId")

                    messages.append(
                        {"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)}
                    )

            # Ran out of rounds - ask once more for a final answer without new tools.
            reply = "I gathered some data but couldn't finish reasoning about it - please try asking again."
            return {"reply": reply, "action": None, "usedTools": used_tools, "modelReachable": True}

    except (httpx.ConnectError, httpx.ConnectTimeout):
        logger.warning("Ollama unreachable at %s", settings.OLLAMA_HOST)
        return {
            "reply": (
                "The local AI model isn't reachable right now. Make sure Ollama is running "
                f"({settings.OLLAMA_HOST}) and that the model is pulled: `ollama pull {settings.OLLAMA_MODEL}`."
            ),
            "action": None,
            "usedTools": [],
            "modelReachable": False,
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.warning("Ollama model '%s' not pulled", settings.OLLAMA_MODEL)
            return {
                "reply": (
                    f"The AI model '{settings.OLLAMA_MODEL}' isn't pulled yet. Run "
                    f"`ollama pull {settings.OLLAMA_MODEL}` and try again."
                ),
                "action": None,
                "usedTools": used_tools,
                "modelReachable": False,
            }
        logger.exception("Ollama chat call failed")
        return {
            "reply": "Something went wrong talking to the AI model. Please try again in a moment.",
            "action": None,
            "usedTools": used_tools,
            "modelReachable": False,
        }
    except Exception:  # noqa: BLE001
        logger.exception("Ollama chat call failed")
        return {
            "reply": "Something went wrong talking to the AI model. Please try again in a moment.",
            "action": None,
            "usedTools": used_tools,
            "modelReachable": False,
        }
