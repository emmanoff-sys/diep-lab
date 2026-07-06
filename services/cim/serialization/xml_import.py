"""Secure CIM/XML parsing foundations.

This module deliberately stops at XML safety and namespace-aware document
parsing. CIM object extraction, relationship resolution, persistence, and
API exposure belong to later WP-006-03B objectives.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from .. import models

try:  # pragma: no cover - exercised only when defusedxml is unavailable.
    from defusedxml import ElementTree as SafeElementTree
    from defusedxml.common import DefusedXmlException
except ImportError:  # pragma: no cover - local/CI environments normally have it.
    from xml.etree import ElementTree as SafeElementTree  # type: ignore[no-redef]

    class DefusedXmlException(Exception):
        pass


UNSAFE_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")
RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
SUPPORTED_CIM_NAMESPACES = frozenset({"http://diep.local/cim/spec-shaped#"})
SUPPORTED_CIM_CLASSES = frozenset(
    name for name in models.__all__ if name != "IdentifiedObject"
)


@dataclass(frozen=True)
class XmlName:
    namespace_uri: str | None
    local_name: str


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

    @property
    def root_name(self) -> XmlName:
        return normalize_name(self.root.tag)


@dataclass(frozen=True)
class UnresolvedReference:
    field_name: str
    resource: str


@dataclass(frozen=True)
class ResolvedReference:
    field_name: str
    resource: str
    target_identifier: str
    target: "ExtractedCimObject"


@dataclass(frozen=True)
class ExtractedCimObject:
    class_name: str
    identifier: str | None
    fields: dict[str, str]
    references: dict[str, UnresolvedReference]


@dataclass(frozen=True)
class ResolvedCimObject:
    source: ExtractedCimObject
    references: dict[str, ResolvedReference]


@dataclass(frozen=True)
class ResolvedCimDocument:
    objects: list[ResolvedCimObject]
    by_identifier: dict[str, ExtractedCimObject]


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

    document = ParsedXmlDocument(root=root, namespaces=namespaces)
    _validate_namespaces(document)
    return document


def extract_objects(document: ParsedXmlDocument) -> list[ExtractedCimObject]:
    """Extract supported CIM object elements without resolving references."""

    objects: list[ExtractedCimObject] = []
    seen_identifiers: set[str] = set()

    for element in list(document.root):
        object_name = normalize_name(element.tag)
        if object_name.namespace_uri not in SUPPORTED_CIM_NAMESPACES:
            raise CimXmlImportError(
                "unsupported_cim_namespace",
                f"object namespace {object_name.namespace_uri!r} is not supported",
            )
        if object_name.local_name not in SUPPORTED_CIM_CLASSES:
            raise CimXmlImportError(
                "unsupported_cim_class",
                f"CIM class {object_name.local_name!r} is not supported",
            )

        identifier = _object_identifier(element)
        if identifier is not None:
            if identifier in seen_identifiers:
                raise CimXmlImportError(
                    "duplicate_object_identifier",
                    f"CIM object identifier {identifier!r} appears more than once",
                )
            seen_identifiers.add(identifier)

        fields: dict[str, str] = {}
        references: dict[str, UnresolvedReference] = {}
        for child in list(element):
            child_name = _field_name(child.tag, object_name.local_name)
            resource = _attribute(child, RDF_NAMESPACE, "resource")
            if resource is not None:
                references[child_name] = UnresolvedReference(
                    field_name=child_name,
                    resource=resource,
                )
                continue

            text = child.text.strip() if child.text is not None else ""
            if text:
                fields[child_name] = text

        objects.append(
            ExtractedCimObject(
                class_name=object_name.local_name,
                identifier=identifier,
                fields=fields,
                references=references,
            )
        )

    return objects


def parse_cim_objects(xml_input: str | bytes) -> list[ExtractedCimObject]:
    """Parse XML and extract supported CIM objects."""

    return extract_objects(parse_xml_document(xml_input))


def resolve_references(objects: list[ExtractedCimObject]) -> ResolvedCimDocument:
    """Resolve captured RDF resources against extracted CIM object IDs."""

    by_identifier = _index_objects_by_identifier(objects)
    resolved_objects: list[ResolvedCimObject] = []

    for source in objects:
        resolved_references: dict[str, ResolvedReference] = {}
        for field_name, reference in source.references.items():
            target_identifier = normalize_identifier(reference.resource)
            target = by_identifier.get(target_identifier)
            if target is None:
                source_identifier = source.identifier or f"<unidentified {source.class_name}>"
                raise CimXmlImportError(
                    "unresolved_reference",
                    f"{source_identifier}.{field_name} references missing object "
                    f"{target_identifier!r}",
                )
            resolved_references[field_name] = ResolvedReference(
                field_name=field_name,
                resource=reference.resource,
                target_identifier=target_identifier,
                target=target,
            )
        resolved_objects.append(
            ResolvedCimObject(source=source, references=resolved_references)
        )

    return ResolvedCimDocument(objects=resolved_objects, by_identifier=by_identifier)


def parse_resolved_cim_document(xml_input: str | bytes) -> ResolvedCimDocument:
    """Parse, extract, and resolve CIM object references."""

    return resolve_references(parse_cim_objects(xml_input))


def split_expanded_tag(tag: str) -> tuple[str | None, str]:
    """Return `(namespace_uri, local_name)` for ElementTree expanded tags."""

    if tag.startswith("{"):
        namespace_uri, _, local_name = tag[1:].partition("}")
        return namespace_uri, local_name
    return None, tag


def normalize_name(tag: str) -> XmlName:
    """Normalize an ElementTree tag into namespace URI and local name."""

    namespace_uri, local_name = split_expanded_tag(tag)
    if not local_name:
        raise CimXmlImportError("malformed_namespace", f"tag {tag!r} has no local name")
    return XmlName(namespace_uri=namespace_uri, local_name=local_name)


def normalize_identifier(identifier: str) -> str:
    """Normalize RDF IDs/about values into deterministic object identifiers."""

    value = identifier.strip()
    if value.startswith("#"):
        return value[1:]
    return value


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


def _validate_namespaces(document: ParsedXmlDocument) -> None:
    rdf_namespace = document.namespaces.get("rdf")
    if rdf_namespace is None:
        raise CimXmlImportError("missing_rdf_namespace", "rdf namespace declaration is required")
    if rdf_namespace != RDF_NAMESPACE:
        raise CimXmlImportError(
            "unsupported_rdf_namespace",
            f"rdf namespace {rdf_namespace!r} is not supported",
        )

    cim_namespace = document.namespaces.get("cim")
    if cim_namespace is None:
        raise CimXmlImportError("missing_cim_namespace", "cim namespace declaration is required")
    if cim_namespace not in SUPPORTED_CIM_NAMESPACES:
        raise CimXmlImportError(
            "unsupported_cim_namespace",
            f"cim namespace {cim_namespace!r} is not supported",
        )

    root_name = document.root_name
    if root_name.namespace_uri != RDF_NAMESPACE or root_name.local_name != "RDF":
        raise CimXmlImportError(
            "malformed_namespace",
            "CIM/XML import root must be rdf:RDF in the supported RDF namespace",
        )


def _attribute(element: Any, namespace_uri: str, local_name: str) -> str | None:
    return element.attrib.get(f"{{{namespace_uri}}}{local_name}")


def _object_identifier(element: Any) -> str | None:
    raw_identifier = _attribute(element, RDF_NAMESPACE, "ID")
    if raw_identifier is None:
        raw_identifier = _attribute(element, RDF_NAMESPACE, "about")
    if raw_identifier is None:
        return None
    return normalize_identifier(raw_identifier)


def _field_name(tag: str, class_name: str) -> str:
    name = normalize_name(tag)
    if name.namespace_uri not in SUPPORTED_CIM_NAMESPACES:
        raise CimXmlImportError(
            "unsupported_cim_namespace",
            f"field namespace {name.namespace_uri!r} is not supported",
        )
    prefix = f"{class_name}."
    if name.local_name.startswith(prefix):
        return name.local_name[len(prefix):]
    return name.local_name


def _index_objects_by_identifier(
    objects: list[ExtractedCimObject],
) -> dict[str, ExtractedCimObject]:
    by_identifier: dict[str, ExtractedCimObject] = {}
    for obj in objects:
        if obj.identifier is None:
            continue
        if obj.identifier in by_identifier:
            raise CimXmlImportError(
                "duplicate_object_identifier",
                f"CIM object identifier {obj.identifier!r} appears more than once",
            )
        by_identifier[obj.identifier] = obj
    return by_identifier
