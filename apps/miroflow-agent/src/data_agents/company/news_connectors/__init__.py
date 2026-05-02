from __future__ import annotations

from .base import NewsConnector, NewsRecord, parse_news_payload
from .cnstock import CNStockConnector
from .serper import SerperNewsConnector
from .tushare import TushareConnector

__all__ = [
    "CNStockConnector",
    "NewsConnector",
    "NewsRecord",
    "SerperNewsConnector",
    "TushareConnector",
    "parse_news_payload",
]
