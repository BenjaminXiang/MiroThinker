from __future__ import annotations

from .base import NewsConnector, NewsRecord, parse_news_payload
from .cnstock import CNStockConnector
from .iyiou import (
    IYIOU_SITE_FILTER,
    PITCHHUB_SITE_FILTER,
    PitchHubNewsConnector,
    YiouFetchResult,
    YiouNewsConnector,
    YiouSearchContext,
    YiouSearchHints,
    extract_yiou_search_hints_with_llm,
)
from .serper import (
    SerperNewsConnector,
    SerperSearchConnector,
    build_generic_identity_queries,
)
from .tushare import TushareConnector

__all__ = [
    "CNStockConnector",
    "IYIOU_SITE_FILTER",
    "NewsConnector",
    "NewsRecord",
    "PITCHHUB_SITE_FILTER",
    "PitchHubNewsConnector",
    "SerperNewsConnector",
    "SerperSearchConnector",
    "TushareConnector",
    "YiouFetchResult",
    "YiouNewsConnector",
    "YiouSearchContext",
    "YiouSearchHints",
    "build_generic_identity_queries",
    "extract_yiou_search_hints_with_llm",
    "parse_news_payload",
]
