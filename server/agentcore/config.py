"""
SetuHaul AgentCore — Centralized Configuration & Logger

Single source of truth for:
- Environment variables (AWS, Supabase, model config)
- Structured logging (shared across handler, tools, memory)
- Agent configuration constants

Compatible with AgentCore Runtime deployment (reads from OS environment)
and local development (falls back to .env file).

Usage in other modules:
    from config import config, logger
"""

import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:
    # On AgentCore Runtime, python-dotenv may not be installed.
    # Env vars are set directly by the platform — no .env file needed.
    def load_dotenv(**kwargs):
        pass

# ---------------------------------------------------------------------------
# Path Setup — ensures imports work across the project
# ---------------------------------------------------------------------------

_current_dir = Path(__file__).resolve().parent
_parent_dir = _current_dir.parent  # server/

# Add both dirs to sys.path for cross-folder imports (db.py lives in server/)
for _dir in (str(_current_dir), str(_parent_dir)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

# Load .env — AgentCore Runtime sets env vars directly, so this is a no-op there.
# Locally, it loads from server/.env or project root/.env
for _candidate in (_current_dir / ".env", _parent_dir / ".env", _parent_dir.parent / ".env"):
    if _candidate.exists():
        load_dotenv(dotenv_path=_candidate)
        break


# ---------------------------------------------------------------------------
# Configuration Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Immutable application configuration loaded from environment."""

    # AWS
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))

    # Agent Model
    model_id: str = field(default_factory=lambda: os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"
    ))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("MODEL_MAX_TOKENS", "6000")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("MODEL_TEMPERATURE", "0.2")))
    top_p: float = field(default_factory=lambda: float(os.environ.get("MODEL_TOP_P", "0.5")))

    # Memory
    memory_id: str = field(default_factory=lambda: os.environ.get("MEMORY_ID", ""))
    max_history_turns: int = field(default_factory=lambda: int(os.environ.get("MAX_HISTORY_TURNS", "10")))

    # Agent Identity
    agent_name: str = field(default_factory=lambda: os.environ.get("AGENT_NAME", "sethaul_driver_agent"))
    agent_description: str = field(default_factory=lambda: os.environ.get(
        "AGENT_DESCRIPTION", "SetuHaul Driver Assistance Agent with conversational memory."
    ))

    # Supabase (used by tools via db.py)
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_KEY", ""))

    # Server
    port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8080")))

    # Deployment (AgentCore Runtime)
    codebuild_role_arn: str = field(default_factory=lambda: os.environ.get("CODEBUILD_ROLE_ARN", ""))
    runtime_role_arn: str = field(default_factory=lambda: os.environ.get("RUNTIME_ROLE_ARN", ""))

    @property
    def vpc_security_groups(self) -> list:
        return parse_list_env("VPC_SECURITY_GROUPS")

    @property
    def vpc_subnets(self) -> list:
        return parse_list_env("VPC_SUBNETS")

    @property
    def model_details(self) -> dict:
        """Returns model config dict compatible with Strands BedrockModel."""
        return {
            "model_id": self.model_id,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }


# Singleton config instance
config = Config()


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def parse_list_env(key: str, default: str = "[]") -> list:
    """
    Parse an environment variable containing a list.
    Handles both JSON format and Python list syntax (single quotes).

    Examples:
        '["sg-abc123"]'           → ["sg-abc123"]
        "['sg-abc123']"           → ["sg-abc123"]
        "sg-abc123, sg-def456"    → ["sg-abc123", "sg-def456"]
    """
    import json as _json

    raw = os.environ.get(key, default).strip()
    if not raw or raw == "[]":
        return []

    # Normalize Python single-quote lists to JSON double-quote
    normalized = raw.replace("'", '"')
    try:
        result = _json.loads(normalized)
        if isinstance(result, list):
            return result
    except (ValueError, TypeError):
        pass

    # Fallback: comma-separated values
    return [s.strip().strip("[]'\"") for s in raw.split(",") if s.strip().strip("[]'\"")]


# ---------------------------------------------------------------------------
# Logger Setup
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    """
    Create a structured logger for the agentcore package.

    On AgentCore Runtime: uses RequestContextFormatter (adds requestId, sessionId).
    Locally: uses a clean format with timestamp and level.
    """
    _logger = logging.getLogger("sethaul.agentcore")

    if _logger.handlers:
        return _logger  # Already configured

    _logger.setLevel(logging.INFO)
    _logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)

    try:
        # Use AgentCore's structured formatter if available
        from bedrock_agentcore.runtime.app import RequestContextFormatter
        handler.setFormatter(RequestContextFormatter())
    except ImportError:
        # Fallback for local development
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    _logger.addHandler(handler)
    return _logger


# Shared logger instance — import this in all modules
logger = _setup_logger()
