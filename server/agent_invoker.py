"""
SetuHaul — AgentCore Runtime Invoker

Invokes the agent deployed on AWS Bedrock AgentCore Runtime.
Called by server.py to send driver messages to the agent and get responses.

Supports:
- AgentCore Runtime (production) via boto3 invoke_agent_runtime
- Direct HTTP endpoint (fallback/local) via httpx

The mode is determined by AGENT_ARN env var:
- If AGENT_ARN is set → uses boto3 AgentCore Runtime invocation
- If AGENT_ENDPOINT is set → uses direct HTTP POST (for local dev)
"""

import os
import sys
import json
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Path setup
_server_dir = str(Path(__file__).resolve().parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

# Load .env
for _candidate in (Path(_server_dir) / ".env", Path(_server_dir).parent / ".env"):
    if _candidate.exists():
        load_dotenv(dotenv_path=_candidate)
        break

logger = logging.getLogger("sethaul.agent_invoker")

# Configuration
AGENT_ARN = os.environ.get("AGENT_ARN", "")
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT", "http://localhost:8080/invocations")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy-init boto3 client (only created when needed)
_agentcore_client = None


def _get_agentcore_client():
    """Get or create the AgentCore boto3 client."""
    global _agentcore_client
    if _agentcore_client is None:
        import boto3
        _agentcore_client = boto3.client(
            "bedrock-agentcore",
            region_name=AWS_REGION,
        )
    return _agentcore_client


# ---------------------------------------------------------------------------
# AgentCore Runtime Invocation (Production)
# ---------------------------------------------------------------------------

def _invoke_via_agentcore(prompt: str, session_id: str) -> dict:
    """
    Invoke the agent via AWS Bedrock AgentCore Runtime using boto3.

    Args:
        prompt: The enriched prompt (driver message + context).
        session_id: Session ID for conversation continuity.

    Returns:
        {"result": "agent response text", "session_id": "..."}
    """
    client = _get_agentcore_client()

    payload = {"prompt": prompt, "session_id": session_id}

    logger.info(f"[agentcore] Invoking ARN={AGENT_ARN[:60]}..., session={session_id[:20]}")

    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_ARN,
        payload=json.dumps(payload).encode("utf-8"),
        runtimeSessionId=session_id,
    )

    status = response.get("statusCode")
    if status != 200:
        error_msg = f"AgentCore invocation failed with status {status}"
        logger.error(f"[agentcore] {error_msg}")
        return {"error": error_msg, "session_id": session_id}

    # Read chunked response body
    content_parts = []
    for chunk in response.get("response", []):
        if isinstance(chunk, bytes):
            content_parts.append(chunk.decode("utf-8"))
        else:
            content_parts.append(str(chunk))

    if not content_parts:
        return {"error": "Empty response from AgentCore Runtime", "session_id": session_id}

    raw_content = "".join(content_parts)

    try:
        content_json = json.loads(raw_content)
    except json.JSONDecodeError:
        # If response is plain text (not JSON), treat it as the result
        return {"result": raw_content, "session_id": session_id}

    # Handle error in response
    if "error" in content_json and "result" not in content_json:
        return {"error": content_json["error"], "session_id": session_id}

    result = content_json.get("result", "")
    result_text = result if isinstance(result, str) else str(result)

    return {"result": result_text, "session_id": content_json.get("session_id", session_id)}


# ---------------------------------------------------------------------------
# Direct HTTP Invocation (Local Development)
# ---------------------------------------------------------------------------

async def _invoke_via_http(prompt: str, session_id: str) -> dict:
    """
    Invoke the agent via direct HTTP POST to AGENT_ENDPOINT.
    Used for local development when running handler.py on port 8080.
    """
    import httpx

    payload = {"prompt": prompt, "session_id": session_id}

    logger.info(f"[http] Invoking {AGENT_ENDPOINT}, session={session_id[:20]}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(AGENT_ENDPOINT, json=payload)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

async def invoke_agent(prompt: str, session_id: str) -> dict:
    """
    Invoke the agent — auto-selects between AgentCore Runtime and direct HTTP.

    If AGENT_ARN is set → uses boto3 AgentCore Runtime (production).
    Otherwise → uses direct HTTP to AGENT_ENDPOINT (local dev).

    Args:
        prompt: The enriched prompt (driver message + context).
        session_id: Session ID for conversation continuity.

    Returns:
        {"result": "agent response text", "session_id": "..."}
        or {"error": "error message", "session_id": "..."}
    """
    try:
        if AGENT_ARN:
            # Production: invoke via AgentCore Runtime (blocking call in thread)
            result = await asyncio.to_thread(_invoke_via_agentcore, prompt, session_id)
        else:
            # Local dev: invoke via HTTP
            result = await _invoke_via_http(prompt, session_id)

        return result

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[invoke_agent] FAILED: {error_msg}")
        return {"error": error_msg, "session_id": session_id}
