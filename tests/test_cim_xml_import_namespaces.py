"""services/cim/serialization/xml_import.py -- CIM/XML namespace handling."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim.serialization import xml_import  # noqa: E402


def _xml(rdf_ns=xml_import.RDF_NAMESPACE, cim_ns="http://diep.local/cim/spec-shaped#",
         root="rdf:RDF", extra_namespaces=""):
    return f"""<?xml version="1.0"?>
<{root}
  xmlns:rdf="{rdf_ns}"
  xmlns:cim="{cim_ns}"{extra_namespaces}>
  <cim:Meter rdf:ID="meter-1" />
</{root}>
"""


def _reason_for(xml_text):
    try:
        xml_import.parse_xml_document(xml_text)
    except xml_import.CimXmlImportError as exc:
        return exc.reason
    return None


def test_valid_rdf_and_cim_namespaces_pass():
    document = xml_import.parse_xml_document(_xml())
    assert document.namespaces["rdf"] == xml_import.RDF_NAMESPACE
    assert document.namespaces["cim"] in xml_import.SUPPORTED_CIM_NAMESPACES


def test_root_name_is_normalized():
    document = xml_import.parse_xml_document(_xml())
    assert document.root_name.namespace_uri == xml_import.RDF_NAMESPACE
    assert document.root_name.local_name == "RDF"


def test_missing_rdf_namespace_is_rejected():
    xml_text = """<?xml version="1.0"?>
<RDF xmlns:cim="http://diep.local/cim/spec-shaped#">
  <cim:Meter />
</RDF>
"""
    assert _reason_for(xml_text) == "missing_rdf_namespace"


def test_unsupported_rdf_namespace_is_rejected():
    assert _reason_for(_xml(rdf_ns="http://example.invalid/rdf#")) == "unsupported_rdf_namespace"


def test_missing_cim_namespace_is_rejected():
    xml_text = f"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="{xml_import.RDF_NAMESPACE}">
  <Meter />
</rdf:RDF>
"""
    assert _reason_for(xml_text) == "missing_cim_namespace"


def test_unsupported_cim_namespace_is_rejected():
    assert _reason_for(_xml(cim_ns="http://example.invalid/cim#")) == "unsupported_cim_namespace"


def test_non_rdf_root_is_rejected_with_malformed_namespace():
    xml_text = f"""<?xml version="1.0"?>
<cim:Meter
  xmlns:rdf="{xml_import.RDF_NAMESPACE}"
  xmlns:cim="http://diep.local/cim/spec-shaped#"
  rdf:ID="meter-1" />
"""
    assert _reason_for(xml_text) == "malformed_namespace"


def test_default_namespace_does_not_replace_required_cim_prefix():
    xml_text = f"""<?xml version="1.0"?>
<rdf:RDF
  xmlns:rdf="{xml_import.RDF_NAMESPACE}"
  xmlns="http://diep.local/cim/spec-shaped#">
  <Meter />
</rdf:RDF>
"""
    assert _reason_for(xml_text) == "missing_cim_namespace"


def test_normalize_name_handles_unqualified_tag():
    name = xml_import.normalize_name("Meter")
    assert name.namespace_uri is None
    assert name.local_name == "Meter"
