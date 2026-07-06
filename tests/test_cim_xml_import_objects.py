"""services/cim/serialization/xml_import.py -- CIM object extraction."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim.serialization import xml_import  # noqa: E402


def _xml(body):
    return f"""<?xml version="1.0"?>
<rdf:RDF
  xmlns:rdf="{xml_import.RDF_NAMESPACE}"
  xmlns:cim="http://diep.local/cim/spec-shaped#">
  {body}
</rdf:RDF>
"""


def _reason_for(xml_text):
    try:
        xml_import.parse_cim_objects(xml_text)
    except xml_import.CimXmlImportError as exc:
        return exc.reason
    return None


def test_extracts_supported_cim_class_and_rdf_id():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:Meter rdf:ID="meter-1">
  <cim:Meter.name>MTR-001</cim:Meter.name>
</cim:Meter>
"""))
    assert len(objects) == 1
    assert objects[0].class_name == "Meter"
    assert objects[0].identifier == "meter-1"


def test_extracts_rdf_about_identifier_and_strips_fragment_marker():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:ConnectivityNode rdf:about="#node-1">
  <cim:ConnectivityNode.name>Node 1</cim:ConnectivityNode.name>
</cim:ConnectivityNode>
"""))
    assert objects[0].identifier == "node-1"


def test_captures_simple_scalar_child_values():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:Meter rdf:ID="meter-1">
  <cim:Meter.name>MTR-001</cim:Meter.name>
  <cim:Meter.status>ONLINE</cim:Meter.status>
</cim:Meter>
"""))
    assert objects[0].fields == {"name": "MTR-001", "status": "ONLINE"}


def test_captures_raw_resource_references_without_resolution():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:Terminal rdf:ID="terminal-1">
  <cim:Terminal.ConnectivityNode rdf:resource="#node-1" />
</cim:Terminal>
"""))
    reference = objects[0].references["ConnectivityNode"]
    assert reference.field_name == "ConnectivityNode"
    assert reference.resource == "#node-1"
    assert objects[0].fields == {}


def test_unsupported_cim_object_class_is_rejected():
    assert _reason_for(_xml("""
<cim:Breaker rdf:ID="breaker-1" />
""")) == "unsupported_cim_class"


def test_duplicate_rdf_id_is_rejected():
    assert _reason_for(_xml("""
<cim:Meter rdf:ID="duplicate" />
<cim:EndDevice rdf:ID="duplicate" />
""")) == "duplicate_object_identifier"


def test_duplicate_rdf_id_and_about_fragment_are_rejected_after_normalization():
    assert _reason_for(_xml("""
<cim:Meter rdf:ID="duplicate" />
<cim:EndDevice rdf:about="#duplicate" />
""")) == "duplicate_object_identifier"


def test_object_without_identifier_is_allowed_for_later_validation_objectives():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:Customer>
  <cim:Customer.customerName>Ada Lovelace</cim:Customer.customerName>
</cim:Customer>
"""))
    assert objects[0].identifier is None
    assert objects[0].fields["customerName"] == "Ada Lovelace"


def test_parse_xml_document_still_only_parses_and_validates_namespaces():
    document = xml_import.parse_xml_document(_xml("""
<cim:Breaker rdf:ID="breaker-1" />
"""))
    assert document.root_name.local_name == "RDF"
