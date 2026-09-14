"""
Bedrock implementation of ModelProvider, via the Converse API (provider-
agnostic across Bedrock's model catalogue, unlike raw InvokeModel with an
Anthropic-specific request body). Used for the M11 AWS deployment, where the
deployment target keeps model traffic in-account (Section 7).

boto3 is synchronous; calls are pushed to a thread so the mediator's async
request path never blocks on it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import boto3

from mediator.providers.base import ModelResponse, ToolCall
from mediator.providers.model_map import resolve_bedrock_model_id


def _to_converse_content(content: Any) -> list[dict[str, Any]]:
    """Anthropic-Messages-shaped content -> Bedrock Converse content blocks."""
    if isinstance(content, str):
        return [{"text": content}]
    blocks: list[dict[str, Any]] = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            blocks.append({"text": block["text"]})
        elif btype == "tool_use":
            blocks.append({"toolUse": {"toolUseId": block["id"], "name": block["name"], "input": block["input"]}})
        elif btype == "tool_result":
            result_content: Any = block.get("content", "")
            blocks.append({
                "toolResult": {
                    "toolUseId": block["tool_use_id"],
                    "content": [{"text": result_content if isinstance(result_content, str) else str(result_content)}],
                    "status": "error" if block.get("is_error") else "success",
                }
            })
    return blocks


def _to_converse_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "toolSpec": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": {"json": tool.get("input_schema", {"type": "object"})},
        }
    }


def _from_converse_content(blocks: list[dict[str, Any]]) -> tuple[str | None, list[ToolCall]]:
    text: str | None = None
    tool_calls: list[ToolCall] = []
    for block in blocks:
        if "text" in block:
            text = (text or "") + block["text"]
        elif "toolUse" in block:
            tu = block["toolUse"]
            tool_calls.append(ToolCall(id=tu["toolUseId"], name=tu["name"], input=tu.get("input", {})))
    return text, tool_calls


class BedrockProvider:
    def __init__(self, *, region: str, region_prefix: str = "us", client: Any = None) -> None:
        self._client = client or boto3.client("bedrock-runtime", region_name=region)
        self._region_prefix = region_prefix

    async def create_message(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> ModelResponse:
        model_id = resolve_bedrock_model_id(model, region_prefix=self._region_prefix)
        kwargs: dict[str, Any] = {
            "modelId": model_id,
            "messages": [
                {"role": m["role"], "content": _to_converse_content(m["content"])}
                for m in messages
                if m["role"] != "system"
            ],
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        if tools:
            kwargs["toolConfig"] = {"tools": [_to_converse_tool(t) for t in tools]}

        resp = await asyncio.to_thread(self._client.converse, **kwargs)

        output_message = resp["output"]["message"]
        text, tool_calls = _from_converse_content(output_message["content"])
        usage = resp.get("usage", {})

        return ModelResponse(
            stop_reason=resp.get("stopReason", "end_turn"),
            text=text,
            tool_calls=tool_calls,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )
