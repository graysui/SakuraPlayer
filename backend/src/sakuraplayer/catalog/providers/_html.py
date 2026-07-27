from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    children: list[HtmlNode | str] = field(default_factory=list)

    def descendants(self, tag: str | None = None) -> Iterable[HtmlNode]:
        for child in self.children:
            if not isinstance(child, HtmlNode):
                continue
            if tag is None or child.tag == tag:
                yield child
            yield from child.descendants(tag)

    def classes(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").split())

    def text(self) -> str:
        parts: list[str] = []
        self._append_text(parts)
        return " ".join(" ".join(parts).split())

    def _append_text(self, parts: list[str]) -> None:
        if self.tag in {"script", "style"}:
            return
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                child._append_text(parts)


class _TreeParser(HTMLParser):
    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(
            tag.lower(), {name.lower(): value or "" for name, value in attrs}
        )
        self._stack[-1].children.append(node)
        if node.tag not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack[-1].tag == tag.lower():
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse_html(value: str) -> HtmlNode:
    parser = _TreeParser()
    parser.feed(value)
    parser.close()
    return parser.root


__all__ = ["HtmlNode", "parse_html"]
