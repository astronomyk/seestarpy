"""Unit tests for the port-4800 binary frame protocol.

Two things about this protocol are easy to get wrong and were both wrong
until firmware 8.46 forced the issue:

1. The frame header is **80 bytes**, not the 34 that carry named fields.
   The extra 46 are zero padding announced at offset 4, and a reader that
   skips only 34 leaves them in the stream — every payload comes back
   shifted 46 bytes early and 46 bytes short.
2. Firmware 8.46+ sends the stack as a finished JPEG (``img_type=4``)
   and reports ``width``/``height`` as **0**, because the real dimensions
   live inside the JPEG.  Anything testing width/height to tell an image
   from an ack throws those frames away.

These tests build frames by hand, so no telescope is involved.
"""

import io
import struct

import pytest

from seestarpy import stream

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")


# ---------------------------------------------------------------------------
# Frame construction
# ---------------------------------------------------------------------------

def make_header(length, img_type=5, width=0, height=0, header_size=80,
                image_id=7):
    """Build the 34 named bytes of a frame header."""
    buf = bytearray(34)
    struct.pack_into('>H', buf, 0, stream.MAGIC_NUMBER)
    struct.pack_into('>H', buf, 2, 2)                 # version
    struct.pack_into('>H', buf, 4, header_size)
    struct.pack_into('>I', buf, 6, length)
    buf[13] = img_type
    struct.pack_into('>H', buf, 16, width)
    struct.pack_into('>H', buf, 18, height)
    struct.pack_into('>H', buf, 24, 1000)             # hfd
    struct.pack_into('>H', buf, 28, image_id)
    return bytes(buf)


def make_frame(payload, **kwargs):
    """A full wire frame: 34 named header bytes + padding + payload."""
    header = make_header(len(payload), **kwargs)
    header_size = kwargs.get('header_size', 80)
    return header + bytes(max(0, header_size - 34)) + payload


def jpeg_bytes(size=(8, 12), colour=(30, 40, 50)):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="JPEG")
    return buf.getvalue()


class FakeSocket:
    """Serves a fixed byte string through the recv() interface."""

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def recv(self, n):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk          # b"" once exhausted, like a closed socket


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

class TestParseHeader:
    def test_reads_the_header_size_from_offset_4(self):
        header = stream.parse_header(make_header(100, header_size=80))
        assert header['header_size'] == 80
        assert header['length'] == 100

    def test_falls_back_when_the_header_size_is_implausible(self):
        """A garbled value is used to skip bytes — never trust it blindly."""
        for bogus in (0, 12, 70000 % 65536, 5000):
            header = stream.parse_header(make_header(100, header_size=bogus))
            assert header['header_size'] == stream.HEADER_SIZE_DEFAULT

    def test_rejects_a_short_buffer(self):
        with pytest.raises(ValueError):
            stream.parse_header(b"\x03\xc3")


class TestReadFrame:
    def test_consumes_the_full_header_before_the_payload(self):
        payload = b"PAYLOAD-" * 4
        sock = FakeSocket(make_frame(payload, img_type=5, width=2, height=2))
        header, got = stream._read_frame(sock)
        assert header['header_size'] == 80
        assert got == payload

    def test_leaves_the_stream_aligned_for_the_next_frame(self):
        """The bug this guards: 46 stray bytes desynced every read."""
        one, two = b"first-payload!!!", b"second-payload!!"
        sock = FakeSocket(make_frame(one, width=2, height=2)
                          + make_frame(two, width=2, height=2))
        assert stream._read_frame(sock)[1] == one
        # No magic-number rescan needed if the first read consumed exactly.
        assert stream._read_frame(sock)[1] == two
        assert sock.pos == len(sock.data)

    def test_skips_interleaved_json(self):
        payload = b"abcd"
        sock = FakeSocket(b'{"id":2,"result":"ok"}\r\n'
                          + make_frame(payload, width=1, height=1))
        assert stream._read_frame(sock)[1] == payload


# ---------------------------------------------------------------------------
# Frame classification
# ---------------------------------------------------------------------------

class TestFrameClassification:
    def test_ack_is_not_an_image(self):
        assert not stream.is_image_frame(
            stream.parse_header(make_header(17, img_type=0)))

    def test_zero_length_is_not_an_image(self):
        assert not stream.is_image_frame(
            stream.parse_header(make_header(0, img_type=5)))

    def test_jpeg_frame_is_an_image_despite_zero_dimensions(self):
        """The regression that broke firmware 8.46: 0x0 but a real image."""
        header = stream.parse_header(
            make_header(2500000, img_type=4, width=0, height=0))
        assert stream.is_image_frame(header)

    def test_raw_frame_needs_dimensions(self):
        assert stream.is_image_frame(stream.parse_header(
            make_header(100, img_type=5, width=4, height=4)))
        assert not stream.is_image_frame(stream.parse_header(
            make_header(100, img_type=5, width=0, height=0)))

    @pytest.mark.parametrize("img_type,expected", [
        (stream.IMG_TYPE_STACKED, True),
        (stream.IMG_TYPE_JPEG, True),
        (stream.IMG_TYPE_PREVIEW, False),
        (stream.IMG_TYPE_ACK, False),
    ])
    def test_stacked_covers_both_stack_transports(self, img_type, expected):
        header = stream.parse_header(make_header(10, img_type=img_type))
        assert stream.is_stacked_frame(header) is expected


# ---------------------------------------------------------------------------
# Payload decoding
# ---------------------------------------------------------------------------

class TestDecodePayload:
    def test_uncompressed_rgb(self):
        w, h = 4, 6
        payload = np.full((h, w, 3), 1234, dtype=np.uint16).tobytes()
        arr = stream.decode_payload(
            payload, {'width': w, 'height': h, 'img_type': 5})
        assert arr.shape == (h, w, 3) and arr.dtype == np.uint16

    def test_raw_bayer_preview(self):
        w, h = 4, 6
        payload = np.full((h, w), 999, dtype=np.uint16).tobytes()
        arr = stream.decode_payload(
            payload, {'width': w, 'height': h, 'img_type': 1})
        assert arr.shape == (h, w) and arr.dtype == np.uint16

    def test_jpeg_payload_ignores_the_zero_header_dimensions(self):
        payload = jpeg_bytes(size=(8, 12))
        arr = stream.decode_payload(
            payload, {'width': 0, 'height': 0, 'img_type': 4})
        assert arr.shape == (12, 8, 3)
        assert arr.dtype == np.uint8, "a JPEG frame is already 8-bit"

    def test_ack_still_raises(self):
        with pytest.raises(ValueError):
            stream.decode_payload(b"", {'width': 0, 'height': 0,
                                        'img_type': 0})

    def test_unknown_payload_raises(self):
        with pytest.raises(ValueError, match="Unknown payload format"):
            stream.decode_payload(b"12345", {'width': 4, 'height': 4,
                                             'img_type': 5})

    def test_exact_size_wins_over_a_stray_zip_signature(self):
        """PK\\x03\\x04 turns up by chance in ~1 uncompressed frame in 100.

        Sizes are decisive, so they must be checked first or those frames
        get routed into the decompressor and thrown away.
        """
        w, h = 4, 6
        arr = np.full((h, w, 3), 700, dtype=np.uint16)
        payload = bytearray(arr.tobytes())
        payload[10:14] = b"PK\x03\x04"          # plausible-looking accident
        out = stream.decode_payload(
            bytes(payload), {'width': w, 'height': h, 'img_type': 5})
        assert out.shape == (h, w, 3)


class TestToDisplay8:
    def test_jpeg_frames_pass_through_unstretched(self):
        arr = np.full((4, 4, 3), 60, dtype=np.uint8)
        out = stream.to_display8(arr)
        assert out.dtype == np.uint8
        assert (out == 60).all(), "already stretched by the firmware"

    def test_linear_data_is_stretched(self):
        rng = np.random.default_rng(0)
        arr = rng.normal(1300, 25, (32, 32, 3)).astype(np.uint16)
        out = stream.to_display8(arr, stretch=True)
        assert out.dtype == np.uint8
        assert out.max() > 0

    def test_bayer_is_expanded_to_rgb(self):
        arr = np.full((4, 4), 5000, dtype=np.uint16)
        assert stream.to_display8(arr).shape == (4, 4, 3)

    def test_unstretched_linear_data_is_shifted_not_blacked_out(self):
        arr = np.full((4, 4, 3), 0x4000, dtype=np.uint16)
        assert (stream.to_display8(arr, stretch=False) == 0x40).all()


class TestImageTransferMode:
    """The firmware 8.46 setting that selects which transport is used."""

    def _sent(self, mock):
        return mock.call_args[0][0]

    def test_sets_the_preview_block(self):
        from unittest.mock import patch
        from seestarpy import raw

        with patch("seestarpy.raw.send_command") as send:
            raw.set_image_transfer_mode("Jpg")
        assert self._sent(send) == {
            "method": "set_setting",
            "params": {"preview": {"image_transfer_mode": "Jpg"}},
        }

    @pytest.mark.parametrize("given,expected", [
        ("Jpg", "Jpg"), ("jpg", "Jpg"), ("JPEG", "Jpg"),
        ("compressed", "Jpg"), ("Raw", "Raw"), ("raw", "Raw"),
        ("lossless", "Raw"), ("full", "Raw"),
    ])
    def test_aliases(self, given, expected):
        from unittest.mock import patch
        from seestarpy import raw

        with patch("seestarpy.raw.send_command") as send:
            raw.set_image_transfer_mode(given)
        params = self._sent(send)["params"]["preview"]
        assert params["image_transfer_mode"] == expected

    def test_rejects_an_unknown_mode_before_the_round_trip(self):
        from unittest.mock import patch
        from seestarpy import raw

        with patch("seestarpy.raw.send_command") as send:
            with pytest.raises(ValueError, match="Unknown image transfer mode"):
                raw.set_image_transfer_mode("turbo")
        send.assert_not_called()

    def test_get_preview_setting_is_none_on_older_firmware(self):
        from unittest.mock import patch
        from seestarpy import raw

        with patch("seestarpy.raw.send_command",
                   return_value={"result": {"exp_ms": {}}}):
            assert raw.get_preview_setting() is None

    def test_get_preview_setting_returns_the_block(self):
        from unittest.mock import patch
        from seestarpy import raw

        block = {"image_transfer_mode": "Jpg", "rtsp_quality": "HighQuality"}
        with patch("seestarpy.raw.send_command",
                   return_value={"result": {"preview": block}}):
            assert raw.get_preview_setting() == block


class TestDashboardEncodesJpegFrames:
    def test_passes_a_jpeg_frame_through_without_restretching(self):
        from seestarpy.dashboard.monitor import encode_frame

        payload = jpeg_bytes(size=(120, 200), colour=(20, 30, 40))
        out, size = encode_frame({'width': 0, 'height': 0, 'img_type': 4,
                                  'image_id': 1}, payload, long_side=100)
        assert size == (120, 200), "dimensions come from the JPEG itself"
        img = Image.open(io.BytesIO(out))
        assert max(img.size) <= 100
        # A flat dark JPEG must stay dark; the STF would have lifted it.
        assert np.asarray(img.convert("RGB")).mean() < 60
