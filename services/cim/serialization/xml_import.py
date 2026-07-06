"""Secure CIM/XML parsing foundations.

This module deliberately stops at XML safety and namespace-aware document
parsing. CIM object extraction, relationship resolution, persistence, and
API exposure belong to later WP-006-03B objectives.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

try:  # pragma: no cover - exercised only when defusedxml is unavailable.
    from defusedxml import ElementTree as SafeElementTree
    from defusedxml.common import DefusedXmlException
except ImportError:  # pragma: no cover - local/CI environments normally have it.
    from xml.etree import ElementTree as SafeElementTree  # type: ignore[no-redef]

    class DefusedXmlException(Exception):
        pass


UNSAFE_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


@dataclass(frozen=True)
class ParsedXmlDocument:
    """Namespace-aware parsed XML document.

    `root` is intentionally exposed for later parser objectives; this
    objective only guarantees that the tree was parsed through the secure
    framework and that namespace declarations were captured.
    """

    root: Any
    namespaces: dict[str, str]

    @property
    def root_tag(self) -> str:
        return self.root.tag


class CimXmlImportError(ValueError):
    """Deterministic XML import rejection with a stable reason code."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def parse_xml_document(xml_input: str | bytes) -> ParsedXmlDocument:
    """Parse a CIM/XML document using the secure import framework."""

    xml_bytes = _to_bytes(xml_input)
    _reject_unsafe_xml_constructs(xml_bytes)

    try:
        namespaces = _collect_namespaces(xml_bytes)
        root = SafeElementTree.fromstring(xml_bytes)
    except DefusedXmlException as exc:
        raise CimXmlImportError("unsafe_xml", str(exc)) from None
    except SafeElementTree.ParseError as exc:
        raise CimXmlImportError("malformed_xml", str(exc)) from None

    return ParsedXmlDocument(root=root, namespaces=namespaces)


def split_expanded_tag(tag: str) -> tuple[str | None, str]:
    """Return `(namespace_uri, local_name)` for ElementTree expanded tags."""

    if tag.startswith("{"):
        namespace_uri, _, local_name = tag[1:].partition("}")
        return namespace_uri, local_name
    return None, tag


def _to_bytes(xml_input: str | bytes) -> bytes:
    if isinstance(xml_input, bytes):
        return xml_input
    if isinstance(xml_input, str):
        return xml_input.encode("utf-8")
    raise TypeError("xml_input must be str or bytes")


def _reject_unsafe_xml_constructs(xml_bytes: bytes) -> None:
    normalized = xml_bytes.upper()
    for marker in UNSAFE_XML_MARKERS:
        if marker in normalized:
            raise CimXmlImportError(
                "unsafe_xml",
                "DTD and entity declarations are not accepted in CIM/XML imports",
            )


def _collect_namespaces(xml_bytes: bytes) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    try:
        for _, namespace in SafeElementTree.iterparse(BytesIO(xml_bytes), events=("start-ns",)):
            prefix, uri = namespace
            namespaces[prefix or ""] = uri
    except DefusedXmlException as exc:
        raise CimXmlImportError("unsafe_xml", str(exc)) from None
    except SafeElementTree.ParseError as exc:
        raise CimXmlImportError("malformed_xml", str(exc)) from None
    return namespaces
