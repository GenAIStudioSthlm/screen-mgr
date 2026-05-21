"""Studio domain specialists — Anthropic-powered subagents wrapping
each MCP server with a skills library. See TASKS/PLAN_AGENTIC.md."""

# Auto-load .env so any CLI or import path picks up ANTHROPIC_API_KEY
# without each entry point having to remember.
from dotenv import load_dotenv

load_dotenv()
