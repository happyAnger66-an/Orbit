"""Mock LLM server with an OpenAI-compatible REST API.

This module provides a minimal FastAPI application that exposes:

  POST /v1/chat/completions

The schema is intentionally compatible with OpenAI's Chat Completions API,
but the implementation is fully local and always returns a successful
mock response. This is useful for testing MW4Agent's LLM integration
without calling real external services.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


class _ChatMessage(BaseModel):
    role: str
    content: str


class _ChatCompletionRequest(BaseModel):
    model: str
    messages: List[_ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    n: Optional[int] = Field(default=1, ge=1)


class _ChatCompletionChoice(BaseModel):
    index: int
    message: _ChatMessage
    finish_reason: str = "stop"


class _ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class _ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[_ChatCompletionChoice]
    usage: _ChatCompletionUsage


def create_app() -> FastAPI:
    """Create a FastAPI app that mocks OpenAI Chat Completions."""

    app = FastAPI(title="MW4Agent Mock LLM Server", version="0.1.0")

    @app.post("/v1/chat/completions", response_model=_ChatCompletionResponse)
    async def chat_completions(body: _ChatCompletionRequest) -> Dict[str, Any]:
        # Build a simple mock reply based on the last user message.
        last_content = ""
        for msg in reversed(body.messages):
            if msg.role == "user":
                last_content = msg.content
                break

        reply_text = f"[mock-llm:{body.model}] Echo: {last_content}"

        choice = _ChatCompletionChoice(
            index=0,
            message=_ChatMessage(role="assistant", content=reply_text),
        )

        usage = _ChatCompletionUsage(
            prompt_tokens=len(last_content.split()),
            completion_tokens=len(reply_text.split()),
            total_tokens=len(last_content.split()) + len(reply_text.split()),
        )

        resp = _ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=body.model,
            choices=[choice],
            usage=usage,
        )
        # Pydantic model is JSON-serializable; FastAPI will handle conversion.
        return resp.dict()

    return app


if __name__ == "__main__":
    # Simple dev entrypoint:
    #   python -m mw4agent.llm.mock_server
    # Then call http://127.0.0.1:8088/v1/chat/completions
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8088)

"""Mock LLM server with an OpenAI-compatible REST API.

This module provides a minimal FastAPI application that exposes:

  POST /v1/chat/completions

The schema is intentionally compatible with OpenAI's Chat Completions API,
but the implementation is fully local and always returns a successful
mock response. This is useful for testing MW4Agent's LLM integration
without calling real external services.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


class _ChatMessage(BaseModel):
    role: str
    content: str


class _ChatCompletionRequest(BaseModel):
    model: str
    messages: List[_ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    n: Optional[int] = Field(default=1, ge=1)


class _ChatCompletionChoice(BaseModel):
    index: int
    message: _ChatMessage
    finish_reason: str = "stop"


class _ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class _ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[_ChatCompletionChoice]
    usage: _ChatCompletionUsage


def create_app() -> FastAPI:
    """Create a FastAPI app that mocks OpenAI Chat Completions."""

    app = FastAPI(title="MW4Agent Mock LLM Server", version="0.1.0")

    @app.post("/v1/chat/completions", response_model=_ChatCompletionResponse)
    async def chat_completions(body: _ChatCompletionRequest) -> Dict[str, Any]:
        # Build a simple mock reply based on the last user message.
        last_content = ""
        for msg in reversed(body.messages):
            if msg.role == "user":
                last_content = msg.content
                break

        reply_text = f"[mock-llm:{body.model}] Echo: {last_content}"

        choice = _ChatCompletionChoice(
            index=0,
            message=_ChatMessage(role="assistant", content=reply_text),
        )

        usage = _ChatCompletionUsage(
            prompt_tokens=len(last_content.split()),
            completion_tokens=len(reply_text.split()),
            total_tokens=len(last_content.split()) + len(reply_text.split()),
        )

        resp = _ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=body.model,
            choices=[choice],
            usage=usage,
        )
        # Pydantic model is JSON-serializable; FastAPI will handle conversion.
        return resp.dict()

    return app


if __name__ == "__main__":
    # Simple dev entrypoint:
    #   python -m mw4agent.llm.mock_server
    # Then call http://127.0.0.1:8088/v1/chat/completions
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8088)

"""Mock LLM server with an OpenAI-compatible Chat Completions API.

This is intended for local testing of MW4Agent's LLM integration without
calling the real OpenAI service.

Endpoint:
  POST /v1/chat/completions

Behavior:
  - Accepts a subset of OpenAI's chat.completions request body.
  - Always returns HTTP 200 with a synthetic completion.
  - Echoes back the last user message and model name in the response.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


def _build_mock_response(body: ChatCompletionRequest) -> Dict[str, Any]:
    created = int(time.time())
    last_user = ""
    for msg in reversed(body.messages):
        if msg.role == "user":
            last_user = msg.content
            break

    reply = f"[mock:{body.model}] Echo: {last_user}"

    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": reply,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def create_app() -> FastAPI:
    """Create a FastAPI app that mocks the OpenAI chat completions API."""
    app = FastAPI(title="MW4Agent Mock LLM Server", version="0.1.0")

    @app.post("/v1/chat/completions")
    async def chat_completions(body: ChatCompletionRequest) -> Dict[str, Any]:
        return _build_mock_response(body)

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"ok": True, "ts": int(time.time() * 1000)}

    return app

