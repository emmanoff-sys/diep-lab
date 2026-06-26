"""CIM/RDF-style XML export (`<cim:ClassName rdf:ID="...">` elements,
one child element per attribute) -- **spec-shaped, not independently
verified** against the official IEC 61970-301 / CGMES RDF/XSD schema (no
access to that artifact here). See LIMITATIONS.md.
"""
from __future__ import annotations

from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from ..models.identified_object import IdentifiedObject

# Placeholder namespace -- this platform's own, not an official CIM
# namespace URI (not verified against one).
_CIM_NS = "http://diep.local/cim/spec-shaped#"
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def to_xml(objects: list[IdentifiedObject], object_type: str) -> str:
    root = Element("rdf:RDF", {"xmlns:rdf": _RDF_NS, "xmlns:cim": _CIM_NS})
    for obj in objects:
        el = SubElement(root, f"cim:{object_type}", {"rdf:ID": obj.mRID})
        for key, value in obj.to_dict().items():
            if key == "mRID" or value is None:
                continue
            child = SubElement(el, f"cim:{object_type}.{key}")
            child.text = str(value)
    rough = tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")
