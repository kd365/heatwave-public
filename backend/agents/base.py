"""Shared Bedrock invoke_model wrapper for HEATWAVE agents.

Each agent defines its own SYSTEM_PROMPT, TOOLS, and tool handler.
This module handles the conversation loop: send message → Claude responds →
if Claude wants to use a tool, execute it and send result back → repeat
until Claude gives a final text answer.
"""

import json
import logging
import os
import re

import boto3

logger = logging.getLogger(__name__)

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy client — created on first use (Lambda reuses across invocations)
_client = None


def _get_client():
    global _client
    if _client is None:
        from botocore.config import Config
        config = Config(read_timeout=300, connect_timeout=10, retries={"max_attempts": 3})
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION, config=config)
    return _client


def run_agent(
    system_prompt: str,
    tools: list[dict],
    tool_handler: callable,
    user_message: str,
    max_turns: int = 10,
) -> dict:
    """Run an agent conversation loop with tool use.

    Args:
        system_prompt: The agent's identity and instructions.
        tools: Tool definitions in Bedrock's toolSpec format.
        tool_handler: Function that takes (tool_name, tool_input) and returns a result string.
        user_message: The initial task/data to send to the agent.
        max_turns: Max tool-use round trips before forcing a stop.

    Returns:
        {"response": str, "tool_calls": list[dict], "tokens_used": int}
    """
    client = _get_client()
    messages = [{"role": "user", "content": [{"text": user_message}]}]
    all_tool_calls = []
    total_tokens = 0

    for turn in range(max_turns):
        # Call Claude
        request = {
            "modelId": BEDROCK_MODEL_ID,
            "messages": messages,
            "system": [{"text": system_prompt}],
            "inferenceConfig": {
                "maxTokens": 16384,
                "temperature": 0.1,
            },
        }
        if tools:
            request["toolConfig"] = {"tools": tools}

        response = client.converse(**request)

        # Track token usage
        usage = response.get("usage", {})
        total_tokens += usage.get("inputTokens", 0) + usage.get("outputTokens", 0)

        # Check stop reason
        stop_reason = response.get("stopReason", "end_turn")
        assistant_message = response["output"]["message"]
        # Strip trailing whitespace from text blocks (Bedrock rejects it)
        for block in assistant_message.get("content", []):
            if "text" in block:
                block["text"] = block["text"].rstrip()
        messages.append(assistant_message)

        # If Claude is done talking (no tool use), extract final text
        if stop_reason == "end_turn":
            final_text = ""
            for block in assistant_message["content"]:
                if "text" in block:
                    final_text += block["text"]
            # Strip markdown code blocks (```json ... ```) that Claude often wraps responses in
            code_match = re.search(r'```(?:json)?\s*(.*?)\s*```', final_text, re.DOTALL)
            if code_match:
                final_text = code_match.group(1)
            return {
                "response": final_text,
                "tool_calls": all_tool_calls,
                "tokens_used": total_tokens,
            }

        # If Claude wants to use tools, execute them
        if stop_reason == "tool_use":
            tool_results = []
            for block in assistant_message["content"]:
                if "toolUse" in block:
                    tool_use = block["toolUse"]
                    tool_name = tool_use["name"]
                    tool_input = tool_use["input"]
                    tool_use_id = tool_use["toolUseId"]

                    logger.info("Agent calling tool: %s", tool_name)
                    all_tool_calls.append({
                        "tool": tool_name,
                        "input": tool_input,
                    })

                    try:
                        result = tool_handler(tool_name, tool_input)
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [{"text": str(result)}],
                            }
                        })
                    except Exception as e:
                        logger.error("Tool %s failed: %s", tool_name, e)
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [{"text": f"Error: {e}"}],
                                "status": "error",
                            }
                        })

            # Send tool results back to Claude
            messages.append({"role": "user", "content": tool_results})

    # If we exhaust max_turns, return whatever we have
    logger.warning("Agent hit max_turns (%d) without finishing", max_turns)
    return {
        "response": "Agent reached maximum tool-use iterations without a final answer.",
        "tool_calls": all_tool_calls,
        "tokens_used": total_tokens,
    }
