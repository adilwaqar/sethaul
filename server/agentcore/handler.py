"""
SetuHaul Driver Assistance Agent — HTTP Protocol with Short-Term Memory (STM)

Deployed to Bedrock AgentCore with:
  - protocol: HTTP
  - memory_mode: STM_ONLY

Multi-turn conversational agent that uses MemorySessionManager to maintain
conversation state across invocations within the same session.
"""

import sys
import warnings
import traceback
from typing import List, Dict

from config import config, logger
from memory import _get_memory_manager, _load_conversation_history, _persist_turn

from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# Suppress noisy warnings
sys.stdout = sys.stderr
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=Warning, module="requests")


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are SetuHaul's on-road Driver Assistance Agent. Your primary role is to
receive messages from truck drivers who are currently en route and extract
structured incident data so that the operations administrator can act quickly.

Entities & ID formats you must recognise or ask about:
- shipment_id    -> e.g. SHP1001, SHP1014 (always starts with SHP)
- driver_id      -> e.g. DRV001, DRV014 (always starts with DRV)
- vehicle_id     -> e.g. VEH001, VEH014 (always starts with VEH)
- facility_id    -> e.g. FAC-JAI-01, FAC-GGN-01

Destination facilities:
- FAC-JAI-01 — SetuHaul Jaipur Distribution Centre, Jaipur, Rajasthan
  Open 06:00-22:00 | Check-in grace: 30 min | Default unload: 60 min
- FAC-GGN-01 — SetuHaul Gurugram Cross-Dock, Gurugram, Haryana
  Open 07:00-21:00 | Check-in grace: 20 min | Default unload: 45 min

Dock types at FAC-JAI-01:
- D1-D4 : STANDARD (max 20-25 tonnes)
- D5    : REEFER (temperature-controlled, max 22 tonnes)
- D6    : HEAVY  (max 35 tonnes, 90-min slots)

Dock types at FAC-GGN-01:
- D1-D2 : STANDARD (max 22 tonnes)
- D3    : REEFER (max 20 tonnes)

Known issue categories (exception_type):
DELAY | BREAKDOWN | TRAFFIC | WEATHER | EARLY_ARRIVAL | DOCK_UNAVAILABLE | UNKNOWN

Severity logic:
- CRITICAL — Priority shipments (CRITICAL/HIGH) with delay > 60 min or no feasible slot remaining.
- HIGH — Any delay > 45 min, or reefer/heavy dock constraint conflicts.
- MEDIUM — Delay 15-45 min with a viable alternative slot.
- LOW — Early arrival, informational queries, duplicate messages.

When a driver initiates a chat describing an issue, you must:

1. EXTRACT the following fields from the driver's message:
   - shipment_id, driver_id, vehicle_id
   - issue_type (DELAY, BREAKDOWN, TRAFFIC, WEATHER, EARLY_ARRIVAL, DOCK_UNAVAILABLE, UNKNOWN)
   - issue_description (brief summary)
   - estimated_arrival (ISO-8601 format, e.g. 2026-08-04T11:25:00+05:30)
   - delay_minutes (integer)
   - destination_facility_id (just the facility_id, e.g. FAC-JAI-01)
   - severity (LOW / MEDIUM / HIGH / CRITICAL)
   - constraints (time limits, temperature, dock type — or empty string if none)

2. ASK FOLLOW-UP QUESTIONS if any field is missing or ambiguous.
   Ask ONLY the questions needed. Maximum 3 at a time.

3. ONCE ALL DATA IS AVAILABLE, you MUST call the `record_driver_issue` tool
   with all extracted fields. Pass the session_id that is provided in the
   conversation context. After the tool returns successfully, confirm to the
   driver that their issue has been logged and the operations team will review it.

   If the tool returns a "duplicate" status, inform the driver that their issue
   was already recorded and no new record was created.

   If the tool returns an "error" status, apologise and ask the driver to try
   again or contact dispatch directly.

Rules:
- Be polite, brief, professional.
- Interpret times in Asia/Kolkata timezone (UTC+05:30).
- Always convert partial times like "11:25 AM" to full ISO-8601 with +05:30 offset.
- Do NOT fabricate IDs. If you cannot determine an ID from context, ask.
- Do NOT make scheduling decisions — only extract, summarise, and recommend.
- You MUST call the record_driver_issue tool once all data is collected. Do not
  skip the tool call or just output a JSON summary.
"""


# ---------------------------------------------------------------------------
# Agent Creation
# ---------------------------------------------------------------------------

def _extract_response_text(result) -> str:
    """Extract plain text from a Strands AgentResult object."""
    response_text = ""

    if hasattr(result, "message") and result.message:
        message = result.message
        if isinstance(message, str):
            response_text = message
        elif isinstance(message, dict):
            content = message.get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    response_text += block["text"]
        elif isinstance(message, list):
            for block in message:
                if isinstance(block, dict) and block.get("text"):
                    response_text += block["text"]

    if not response_text and result:
        try:
            response_text = str(result)
        except Exception:
            response_text = "Agent completed but could not extract response text."

    return response_text


def _create_agent(history_messages: List[Dict], session_id: str):
    """Create a Strands Agent with tools and pre-loaded conversation history."""
    from strands import Agent
    from strands.models import BedrockModel
    from strands.types.content import SystemContentBlock
    from tools import record_driver_issue

    model = BedrockModel(**config.model_details)

    # Inject session_id into the system prompt so the agent can pass it to the tool
    session_context = (
        f"\n\nCurrent session_id: {session_id}\n"
        f"Always use this session_id when calling the record_driver_issue tool."
    )
    full_prompt = SYSTEM_PROMPT + session_context
    system_content = [SystemContentBlock(text=full_prompt)]

    agent = Agent(
        name=config.agent_name,
        description=config.agent_description,
        model=model,
        system_prompt=system_content,
        tools=[record_driver_issue],
        messages=history_messages if history_messages else None,
    )

    return agent


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
def agent_invocation(payload, context):
    """
    HTTP protocol entrypoint with short-term memory for multi-turn conversations.

    Expects:
        payload: {"prompt": "driver's message text", "session_id": "..."}
        context: RequestContext with session_id from runtimeSessionId header

    Returns:
        {"result": "agent response text", "session_id": "..."}
    """
    try:
        user_message = payload.get("prompt", "")
        if not isinstance(user_message, str) or not user_message.strip():
            return {"error": "Invalid input: 'prompt' must be a non-empty string"}

        # Extract session_id from AgentCore context or payload
        session_id = None
        if context and hasattr(context, "session_id"):
            session_id = context.session_id
        if not session_id:
            session_id = payload.get("session_id", "default-session")

        logger.info(f"[invocation] session_id={session_id}, prompt={user_message[:150]}")

        # Load conversation history from STM
        history_messages: List[Dict] = []
        memory_mgr = None

        if config.memory_id:
            memory_mgr = _get_memory_manager(config.memory_id)
            history_messages = _load_conversation_history(memory_mgr, session_id)
            logger.info(f"[invocation] MEMORY_ID={config.memory_id}")
        else:
            logger.warning("[invocation] MEMORY_ID not set — running stateless")

        # Create agent and invoke
        agent = _create_agent(history_messages, session_id)
        result = agent(user_message)
        response_text = _extract_response_text(result)

        # Persist turn to STM
        if memory_mgr:
            _persist_turn(memory_mgr, session_id, user_message, response_text)

        logger.info(f"[invocation] response_length={len(response_text)}")
        return {"result": response_text, "session_id": session_id}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[invocation] FAILED: {error_msg}")
        logger.error(traceback.format_exc())
        return {"error": error_msg}


# ---------------------------------------------------------------------------
# Local Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Starting agentcore server on :{config.port}...")
    app.run(port=config.port, host="0.0.0.0")
