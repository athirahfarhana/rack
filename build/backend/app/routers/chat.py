from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import ollama_client, schemas
from ..database import get_db

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Very small in-memory per-session history so follow-up questions like
# "and where was it before that?" keep some context. Not durable across
# backend restarts - fine for a floor-facing assistant widget.
_SESSION_HISTORY: dict[str, list[dict]] = {}
_MAX_HISTORY_TURNS = 6


@router.post("", response_model=schemas.ChatOut)
async def chat(payload: schemas.ChatIn, db: Session = Depends(get_db)):
    session_id = payload.sessionId or "default"
    history = _SESSION_HISTORY.get(session_id, [])

    result = await ollama_client.chat(db, payload.message, history=history)

    history.append({"role": "user", "content": payload.message})
    history.append({"role": "assistant", "content": result["reply"]})
    _SESSION_HISTORY[session_id] = history[-(_MAX_HISTORY_TURNS * 2) :]

    return schemas.ChatOut(
        reply=result["reply"],
        action=schemas.ChatAction(**result["action"]) if result.get("action") else None,
        usedTools=result.get("usedTools", []),
        modelReachable=result.get("modelReachable", True),
    )
