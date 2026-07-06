"""services/cim/serialization/xml_import.py -- CIM reference resolution."""
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
        xml_import.parse_resolved_cim_document(xml_text)
    except xml_import.CimXmlImportError as exc:
        return exc.reason
    return None


def test_resolves_fragment_resource_to_extracted_object():
    document = xml_import.parse_resolved_cim_document(_xml("""
<cim:ConnectivityNode rdf:ID="node-1" />
<cim:Terminal rdf:ID="terminal-1">
  <cim:Terminal.ConnectivityNode rdf:resource="#node-1" />
</cim:Terminal>
"""))
    terminal = document.by_identifier["terminal-1"]
    resolved_terminal = next(obj for obj in document.objects if obj.source is terminal)
    reference = resolved_terminal.references["ConnectivityNode"]
    assert reference.target_identifier == "node-1"
    assert reference.target.class_name == "ConnectivityNode"


def test_resolves_plain_resource_identifier_to_extracted_object():
    document = xml_import.parse_resolved_cim_document(_xml("""
<cim:Meter rdf:ID="meter-1" />
<cim:UsagePoint rdf:ID="usage-point-1">
  <cim:UsagePoint.Meter rdf:resource="meter-1" />
</cim:UsagePoint>
"""))
    reference = document.objects[1].references["Meter"]
    assert reference.resource == "meter-1"
    assert reference.target_identifier == "meter-1"


def test_resolved_document_indexes_identified_objects_only():
    document = xml_import.parse_resolved_cim_document(_xml("""
<cim:Customer>
  <cim:Customer.customerName>Ada Lovelace</cim:Customer.customerName>
</cim:Customer>
<cim:ServicePoint rdf:ID="service-point-1" />
"""))
    assert sorted(document.by_identifier) == ["service-point-1"]
    assert len(document.objects) == 2


def test_unresolved_reference_is_rejected_deterministically():
    assert _reason_for(_xml("""
<cim:Terminal rdf:ID="terminal-1">
  <cim:Terminal.ConnectivityNode rdf:resource="#missing-node" />
</cim:Terminal>
""")) == "unresolved_reference"


def test_unidentified_source_reference_error_is_still_deterministic():
    assert _reason_for(_xml("""
<cim:Terminal>
  <cim:Terminal.ConnectivityNode rdf:resource="#missing-node" />
</cim:Terminal>
""")) == "unresolved_reference"


def test_object_extraction_still_leaves_references_unresolved():
    objects = xml_import.parse_cim_objects(_xml("""
<cim:ConnectivityNode rdf:ID="node-1" />
<cim:Terminal rdf:ID="terminal-1">
  <cim:Terminal.ConnectivityNode rdf:resource="#node-1" />
</cim:Terminal>
"""))
    reference = objects[1].references["ConnectivityNode"]
    assert isinstance(reference, xml_import.UnresolvedReference)
    assert reference.resource == "#node-1"


def test_duplicate_identifier_rejected_during_resolution_entrypoint():
    assert _reason_for(_xml("""
<cim:Meter rdf:ID="duplicate" />
<cim:EndDevice rdf:about="#duplicate" />
""")) == "duplicate_object_identifier"
