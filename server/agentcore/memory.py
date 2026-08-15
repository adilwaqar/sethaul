"""
SetuHaul AgentCore — Short-Term Memory (STM) Management

Handles loading and persisting conversation turns using AgentCore's
MemorySessionManager. Used by handler.py to maintain multi-turn context.
"""

from typing import List, Dict

from config import config, logger


# ---------------------------------------------------------------------------
# Memory Helpers
# ---------------------------------------------------------------------------


def _get_memory_manager(memory_id: str):
    """Create a MemorySessionManager instance for the given memory_id."""
    from bedrock_agentcore.memory import MemorySessionManager

    return MemorySessionManager(
        memory_id=memory_id,
        region_name=config.aws_region,
    )


def _load_conversation_history(memory_mgr, session_id: str) -> List[Dict]:
    """
    Load previous conversation turns from short-term memory.

    Returns a list of Strands-compatible message dicts:
        [{"role": "user", "content": [{"text": "..."}]},
         {"role": "assistant", "content": [{"text": "..."}]}, ...]
    """
    messages: List[Dict] = []

    try:
        turns = memory_mgr.get_last_k_turns(
            actor_id=config.agent_name,
            session_id=session_id,
            k=config.max_history_turns,
        )

        for turn in turns:
            for event_message in turn:
                role_raw = event_message.get("role", "").lower()
                text = event_message.get("content", {}).get("text", "")

                if not text:
                    continue

                if role_raw == "user":
                    messages.append({"role": "user", "content": [{"text": text}]})
                elif role_raw == "assistant":
                    messages.append({"role": "assistant", "content": [{"text": text}]})

        logger.info(f"[memory] Loaded {len(messages)} messages from STM for session {session_id}")

    except Exception as e:
        logger.warning(f"[memory] Failed to load history (will proceed stateless): {e}")

    return messages


def _persist_turn(memory_mgr, session_id: str, user_text: str, assistant_text: str):
    """Persist the current user+assistant turn to short-term memory."""
    from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

    try:
        memory_mgr.add_turns(
            actor_id=config.agent_name,
            session_id=session_id,
            messages=[
                ConversationalMessage(text=user_text, role=MessageRole.USER),
                ConversationalMessage(text=assistant_text, role=MessageRole.ASSISTANT),
            ],
        )
        logger.info(f"[memory] Persisted turn to STM for session {session_id}")
    except Exception as e:
        logger.error(f"[memory] Failed to persist turn: {e}")
