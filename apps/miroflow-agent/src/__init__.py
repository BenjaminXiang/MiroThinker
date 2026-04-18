# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""MiroFlow Agent - A modular agent framework for task execution.

Keep top-level exports lazy so subpackage imports like ``src.data_agents...`` do not
pull in unrelated runtime dependencies during admin-console tests or tooling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "Orchestrator",
    "create_pipeline_components",
    "execute_task_pipeline",
    "OutputFormatter",
    "ClientFactory",
    "TaskLog",
    "bootstrap_logger",
]

if TYPE_CHECKING:  # pragma: no cover
    from .core.orchestrator import Orchestrator
    from .core.pipeline import create_pipeline_components, execute_task_pipeline
    from .io.output_formatter import OutputFormatter
    from .llm.factory import ClientFactory
    from .logging.task_logger import TaskLog, bootstrap_logger


def __getattr__(name: str) -> Any:
    if name == "Orchestrator":
        from .core.orchestrator import Orchestrator
        return Orchestrator
    if name in {"create_pipeline_components", "execute_task_pipeline"}:
        from .core.pipeline import create_pipeline_components, execute_task_pipeline
        return {
            "create_pipeline_components": create_pipeline_components,
            "execute_task_pipeline": execute_task_pipeline,
        }[name]
    if name == "OutputFormatter":
        from .io.output_formatter import OutputFormatter
        return OutputFormatter
    if name == "ClientFactory":
        from .llm.factory import ClientFactory
        return ClientFactory
    if name in {"TaskLog", "bootstrap_logger"}:
        from .logging.task_logger import TaskLog, bootstrap_logger
        return {"TaskLog": TaskLog, "bootstrap_logger": bootstrap_logger}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
