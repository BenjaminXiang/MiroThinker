from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_SUB_TAG_RE = re.compile(r"<sub\b[^>]*>(.*?)</sub>", re.IGNORECASE | re.DOTALL)
_SUP_TAG_RE = re.compile(r"<sup\b[^>]*>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_MATH_BLOCK_RE = re.compile(
    r"<(?P<tag>(?:[A-Za-z0-9_]+:)?math)\b.*?</(?P=tag)>", re.IGNORECASE | re.DOTALL
)
_CONTROL_RE = re.compile(r"[\u200b-\u200f\ufeff]")
_FORMULA_SEQUENCE_RE = re.compile(
    r"\b(?:[A-Za-z\u0370-\u03FF]{1,4}|\d{1,3})(?:\s+(?:[A-Za-z\u0370-\u03FF]{1,4}|\d{1,3})){2,5}\b"
)
_FORMULA_DIGIT_SUFFIX_RE = re.compile(
    r"\b([A-Za-z\u0370-\u03FF0-9-]*\d[A-Za-z\u0370-\u03FF0-9-]*)\s+(\d{1,3})\b"
)


def clean_paper_title(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _MATH_BLOCK_RE.sub(_replace_math_block, text)
    text = _SUB_TAG_RE.sub(lambda match: _clean_inline_fragment(match.group(1)), text)
    text = _SUP_TAG_RE.sub(lambda match: _clean_inline_fragment(match.group(1)), text)
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = _CONTROL_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([(/])\s+", r"\1", text)
    text = re.sub(r"\s+([)])", r"\1", text)
    text = _compact_formula_spacing(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _clean_inline_fragment(fragment: str) -> str:
    text = html.unescape(fragment or "")
    text = _TAG_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return _WHITESPACE_RE.sub("", text)


def _replace_math_block(match: re.Match[str]) -> str:
    fragment = match.group(0)
    rendered = _render_mathml_fragment(fragment)
    if rendered:
        return rendered
    fallback = _TAG_RE.sub(" ", fragment)
    fallback = html.unescape(fallback)
    return _WHITESPACE_RE.sub(" ", fallback).strip()


def _render_mathml_fragment(fragment: str) -> str:
    try:
        root = ET.fromstring(fragment)
    except ET.ParseError:
        return ""
    rendered = _render_mathml_node(root)
    rendered = html.unescape(rendered)
    rendered = _CONTROL_RE.sub("", rendered)
    rendered = _WHITESPACE_RE.sub(" ", rendered).strip()
    rendered = re.sub(r"\s*/\s*", "/", rendered)
    return rendered


def _render_mathml_node(node: ET.Element) -> str:
    tag = _local_name(node.tag)
    children = list(node)

    if tag == "mfrac":
        numerator = _render_mathml_node(children[0]) if len(children) > 0 else ""
        denominator = _render_mathml_node(children[1]) if len(children) > 1 else ""
        return f"{numerator}/{denominator}".strip("/")

    if tag in {"msub", "msup", "msubsup", "msqrt", "mroot"}:
        rendered_children = "".join(_render_mathml_node(child) for child in children)
        return f"{(node.text or '')}{rendered_children}"

    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in children:
        parts.append(_render_mathml_node(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1].casefold()
    if ":" in tag:
        return tag.rsplit(":", 1)[-1].casefold()
    return tag.casefold()


def _compact_formula_spacing(text: str) -> str:
    previous = None
    while text != previous:
        previous = text
        text = _FORMULA_SEQUENCE_RE.sub(_replace_formula_sequence, text)
        text = _FORMULA_DIGIT_SUFFIX_RE.sub(r"\1\2", text)
    return text


def _replace_formula_sequence(match: re.Match[str]) -> str:
    tokens = match.group(0).split()
    if not _looks_like_formula_sequence(tokens):
        return match.group(0)
    return "".join(tokens)


def _looks_like_formula_sequence(tokens: list[str]) -> bool:
    if len(tokens) < 3 or not any(token.isdigit() for token in tokens):
        return False
    for token in tokens:
        if token.isdigit():
            continue
        if len(token) > 4 or not re.fullmatch(r"[A-Za-z\u0370-\u03FF]+", token):
            return False
        if token.islower() and len(token) > 1:
            return False
    return True
