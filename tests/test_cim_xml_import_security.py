"""services/cim/serialization/xml_import.py -- secure XML parsing foundation.

Objective 2 covers parser safety and namespace-aware foundations only. It
does not extract CIM objects, resolve references, persist data, or expose
an API.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim.serialization import xml_import  # noqa: E402


SAFE_CIM_XML = """<?xml version="1.0"?>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:cim="http://diep.local/cim/spec-shaped#">
  <cim:Meter rdf:ID="meter-1">
    <cim:Meter.name>MTR-001</cim:Meter.name>
  </cim:Meter>
</rdf:RDF>
"""


def _reason_for(xml_text):
    try:
        xml_import.parse_xml_document(xml_text)
    except xml_import.CimXmlImportError as exc:
        return exc.reason
    return None


def test_secure_parser_accepts_well_formed_cim_xml():
    document = xml_import.parse_xml_document(SAFE_CIM_XML)
    assert document.root_tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"


def test_secure_parser_captures_namespaces():
    document = xml_import.parse_xml_document(SAFE_CIM_XML)
    assert document.namespaces["rdf"] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    assert document.namespaces["cim"] == "http://diep.local/cim/spec-shaped#"


def test_expanded_tag_split_preserves_namespace_and_local_name():
    namespace_uri, local_name = xml_import.split_expanded_tag(
        "{http://diep.local/cim/spec-shaped#}Meter"
    )
    assert namespace_uri == "http://diep.local/cim/spec-shaped#"
    assert local_name == "Meter"


def test_malformed_xml_is_rejected_deterministically():
    assert _reason_for("<rdf:RDF><cim:Meter></rdf:RDF>") == "malformed_xml"


def test_doctype_is_rejected_as_unsafe_xml():
    xml_text = """<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
  <!ELEMENT rdf:RDF ANY>
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" />
"""
    assert _reason_for(xml_text) == "unsafe_xml"


def test_entity_declaration_is_rejected_as_unsafe_xml():
    xml_text = """<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
  <!ENTITY unsafe "expanded">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">&unsafe;</rdf:RDF>
"""
    assert _reason_for(xml_text) == "unsafe_xml"


def test_external_entity_declaration_is_rejected_as_unsafe_xml():
    xml_text = """<?xml version="1.0"?>
<!DOCTYPE rdf:RDF [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">&xxe;</rdf:RDF>
"""
    assert _reason_for(xml_text) == "unsafe_xml"


def test_parser_accepts_bytes_input():
    document = xml_import.parse_xml_document(SAFE_CIM_XML.encode("utf-8"))
    assert "cim" in document.namespaces
