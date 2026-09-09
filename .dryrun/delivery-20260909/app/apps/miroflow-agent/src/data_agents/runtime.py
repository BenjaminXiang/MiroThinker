from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, TypeVar

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig
from pydantic import BaseModel

from src.core.pipeline import create_pipeline_components, execute_task_pipeline


ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class StructuredTaskExecutionError(RuntimeError):
    def __init__(self, message: str, *, log_file_path: str) -> None:
        super().__init__(f"{message}\nLog file: {log_file_path}")
        self.log_file_path = log_file_path


def schema_text_for_model(model_cls: type[ModelT]) -> str:
    return json.dumps(
        model_cls.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _extract_json_payload(payload: str) -> str:
    match = _JSON_FENCE_RE.search(payload)
    if match:
        return match.group(1).strip()
    return payload.strip()


def parse_structured_payload(payload: str, model_cls: type[ModelT]) -> ModelT:
    return model_cls.model_validate_json(_extract_json_payload(payload))


def load_domain_cfg(
    overrides: list[str] | None = None,
    *,
    config_name: str = "config",
) -> DictConfig:
    conf_dir = Path(__file__).resolve().parents[2] / "conf"
    resolved_overrides = list(overrides or [])
    if not any(
        override == "agent.output_mode=json"
        or override.startswith("agent.output_mode=")
        for override in resolved_overrides
    ):
        resolved_overrides.append("agent.output_mode=json")
    with initialize_config_dir(config_dir=str(conf_dir), version_base=None):
        return compose(config_name=config_name, overrides=resolved_overrides)


async def run_structured_task(
    *,
    cfg: DictConfig,
    task_id: str,
    task_description: str,
    output_model: type[ModelT],
    task_file_name: str = "",
    create_components_fn: Callable[[DictConfig], Any] = create_pipeline_components,
    execute_task_pipeline_fn: Callable[..., Any] = execute_task_pipeline,
) -> tuple[ModelT, str]:
    main_tools, sub_tools, output_formatter = create_components_fn(cfg)
    final_summary, payload, log_file_path, _ = await execute_task_pipeline_fn(
        cfg=cfg,
        task_id=task_id,
        task_description=task_description,
        task_file_name=task_file_name,
        main_agent_tool_manager=main_tools,
        sub_agent_tool_managers=sub_tools,
        output_formatter=output_formatter,
        log_dir=cfg.debug_dir,
        final_output_schema=schema_text_for_model(output_model),
    )
    if not payload.strip():
        raise StructuredTaskExecutionError(
            final_summary or f"Structured task {task_id} did not produce a payload.",
            log_file_path=log_file_path,
        )
    return parse_structured_payload(payload, output_model), log_file_path
