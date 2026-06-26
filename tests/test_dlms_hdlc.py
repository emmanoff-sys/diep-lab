"""Isolated unit tests for the HDLC framing layer (Phase 2).

No live connection: build/parse/CRC logic only, per the Phase-2 spec. Covers
the HDLC code path the DlmsMeterClient `interface="hdlc"` branch relies on.

⚠️ See drivers/dlms/protocol.py VALIDATION CAVEAT — minimal HDLC subset, not
meter-validated.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "drivers"))

from dlms import protocol, transport  # noqa: E402


def test_hdlc_frame_round_trip():
    frame = transport.build_hdlc_frame(address=0x10, control=transport.HDLC_SNRM, info=b"\x01\x02")
    addr, ctrl, info = transport.parse_hdlc_frame(frame)
    assert addr == 0x10
    assert ctrl == transport.HDLC_SNRM
    assert info == b"\x01\x02"


def test_hdlc_flags_present():
    frame = transport.build_hdlc_frame(0x10, transport.HDLC_UA, b"abc")
    assert frame[0] == transport.HDLC_FLAG and frame[-1] == transport.HDLC_FLAG


def test_hdlc_fcs_detects_corruption():
    frame = bytearray(transport.build_hdlc_frame(0x10, transport.HDLC_UA, b"abc"))
    frame[3] ^= 0xFF  # flip a byte inside the body (after FLAG+addr+ctrl)
    with pytest.raises(ValueError):
        transport.parse_hdlc_frame(bytes(frame))


def test_hdlc_bad_flags_rejected():
    with pytest.raises(ValueError):
        transport.parse_hdlc_frame(b"\x00\x01\x02\x03\x00")  # no 0x7E delimiters


def test_snrm_ua_build_parse():
    _a, ctrl_snrm, _i = transport.parse_hdlc_frame(transport.build_snrm(0x10))
    assert ctrl_snrm == transport.HDLC_SNRM
    assert transport.is_u_frame(ctrl_snrm)
    _a, ctrl_ua, _i = transport.parse_hdlc_frame(transport.build_ua(0x10))
    assert ctrl_ua == transport.HDLC_UA
    assert transport.is_u_frame(ctrl_ua)


def test_iframe_carries_aarq_and_getresponse():
    # An AARQ PDU wrapped in an I-frame must round-trip and still parse as AARQ input.
    aarq = protocol.build_aarq(16, 1)
    f1 = transport.build_iframe(0x10, send_seq=0, recv_seq=0, info=aarq)
    _a, ctrl1, info1 = transport.parse_hdlc_frame(f1)
    assert transport.is_i_frame(ctrl1)
    assert info1 == aarq
    # A GET-response PDU wrapped in an I-frame must decode to its value.
    resp = protocol.build_get_response(1, protocol.encode_value(230.0))
    f2 = transport.build_iframe(0x10, send_seq=1, recv_seq=1, info=resp)
    _a, ctrl2, info2 = transport.parse_hdlc_frame(f2)
    assert transport.is_i_frame(ctrl2)
    _iid, _r, vb = protocol.parse_get_response(info2)
    assert protocol.decode_value(vb) == 230.0


def test_iframe_sequence_numbers_round_trip():
    f = transport.build_iframe(0x10, send_seq=2, recv_seq=3, info=b"x")
    _a, ctrl, _i = transport.parse_hdlc_frame(f)
    assert transport.iframe_seq(ctrl) == (2, 3)
