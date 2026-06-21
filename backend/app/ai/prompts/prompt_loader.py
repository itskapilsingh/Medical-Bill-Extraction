"""Jinja2 prompt loader backed by the local filesystem.

Templates live under ``app/ai/prompts/templates/``. Keys are paths relative to
that directory, e.g. ``echo/system.j2`` → ``templates/echo/system.j2``.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# Default root for Jinja templates (``templates/`` next to this module).
DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class PromptLoader:
    """Load and render Jinja2 prompt templates from the local filesystem.

    Args:
        prompts_dir: Root directory whose layout mirrors template keys (typically
            ``…/prompts/templates``). Defaults to ``DEFAULT_TEMPLATES_DIR``.
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        root = prompts_dir if prompts_dir is not None else DEFAULT_TEMPLATES_DIR
        self._templates_root = root.resolve()
        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_root)),
            autoescape=False,
            keep_trailing_newline=True,
        )

    async def render(self, key: str, variables: dict) -> str:
        """Render a template by key with the given variables.

        Args:
            key: Relative path under the templates root, e.g. ``echo/system.j2``.
            variables: Variables passed into the Jinja2 render context.

        Returns:
            Fully rendered template string.

        Raises:
            TemplateNotFound: If no template exists at the given key.
        """
        try:
            template = self._env.get_template(key)
        except TemplateNotFound:
            raise TemplateNotFound(
                f"Prompt template not found: {key}. "
                f"Expected at {self._templates_root / key}"
            )
        return template.render(**variables)
