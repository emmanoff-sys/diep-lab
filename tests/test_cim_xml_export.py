"""services/cim/serialization/xml_export.py -- well-formed CIM/RDF-style
XML (parseable via stdlib xml.etree), one element per object, correct
rdf:ID, every non-None field present as a child element."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from xml.etree import ElementTree  # noqa: E402

from services.cim.models import Meter  # noqa: E402
from services.cim.serialization import xml_export  # noqa: E402

_METER = Meter(mRID="11111111-1111-1111-1111-111111111111", name="SIT-METER-001",
                deviceType="smartmeter", status="ONLINE", tenantId="sit-tenant")


def test_xml_export_is_well_formed():
    xml_str = xml_export.to_xml([_METER], "Meter")
    root = ElementTree.fromstring(xml_str)  # raises ParseError if malformed
    assert root is not None


def test_xml_export_has_one_element_per_object_with_correct_rdf_id():
    xml_str = xml_export.to_xml([_METER, _METER], "Meter")
    root = ElementTree.fromstring(xml_str)
    meters = root.findall("{http://diep.local/cim/spec-shaped#}Meter")
    assert len(meters) == 2
    for el in meters:
        assert el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}ID") == _METER.mRID


def test_xml_export_includes_non_none_fields_as_child_elements():
    xml_str = xml_export.to_xml([_METER], "Meter")
    assert "Meter.deviceType" in xml_str
    assert "smartmeter" in xml_str
    assert "Meter.status" in xml_str


def test_xml_export_omits_none_fields_rather_than_emitting_empty_tags():
    xml_str = xml_export.to_xml([_METER], "Meter")
    assert "Meter.description" not in xml_str  # _METER.description is None


def test_xml_export_of_empty_list_is_still_well_formed():
    xml_str = xml_export.to_xml([], "Feeder")
    root = ElementTree.fromstring(xml_str)
    assert len(list(root)) == 0


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
