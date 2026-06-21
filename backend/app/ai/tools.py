from __future__ import annotations

from agents import function_tool
from agents.tool_context import ToolContext

from app.ai.context import RunContext


@function_tool
async def echo_tool(
    ctx: ToolContext[RunContext],
    message: str,
) -> str:
    """Echo a message back. Used only by the echo agent as a demonstration tool.

    Args:
        message: Any string to echo.

    Returns:
        The input string prefixed with 'Echo: '.
    """
    return f"Echo: {message}"
