import re
import struct

MAX_REASONABLE_CHUNK_SIZE = 10 * 1024 * 1024
MIN_REASONABLE_CHUNK_SIZE = 16  # 최소 청크 크기(0x10). idx 무시

CHUNK_SIG = {
    'front': b'00dc',
    'rear':  b'01dc',
    'side':  b'02dc',
}

PATTERNS = {
    'H264': {
        'start': re.compile(b'\x00{2,3}\x01\x67'), # SPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x67'), # SPS
            re.compile(b'\x00{2,3}\x01\x68'), # PPS
            re.compile(b'\x00{2,3}\x01[\x25\x45\x65]'), # I-Frame
            re.compile(b'\x00{2,3}\x01[\x21\x41\x61]'), # P-Frame
        ]
    },
    'HEVC': {
        'start': re.compile(b'\x00{2,3}\x01\x40'), # VPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x40'), # VPS
            re.compile(b'\x00{2,3}\x01\x42'), # SPS
            re.compile(b'\x00{2,3}\x01\x44'), # PPS
            re.compile(b'\x00{2,3}\x01\x26'), # I-Frame
            re.compile(b'\x00{2,3}\x01\x02'), # P-Frame
        ]
    }
}

def _guess_codec_by_signature(data):
    hevc_hits = data.count(b"\x00\x00\x01\x40") + data.count(b"\x00\x00\x00\x01\x40")
    sps_h264  = data.count(b"\x00\x00\x01\x67") + data.count(b"\x00\x00\x00\x01\x67")
    return 'HEVC' if hevc_hits > sps_h264 else 'H264'

def detect_codec(data):
    hdr = data[112:116]
    if hdr in (b'h264', b'H264', b'\x68\x32\x36\x34'):
        return 'H264'
    if hdr in (b'hev1', b'HEV1', b'\x68\x65\x76\x31'):
        return 'HEVC'
    return _guess_codec_by_signature(data)

def _guess_main_area_end(data):
    max_end = 0
    for sig in CHUNK_SIG.values():
        offset = 0
        while True:
            idx = data.find(sig, offset)
            if idx < 0 or idx + 8 > len(data):
                break
            size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
            start = idx + 8
            end   = start + size

            if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE or end > len(data):
                offset = idx + 4
                continue

            if end > max_end:
                max_end = end
            offset = end

    return max_end if max_end > 0 else 0

def split_channel_bytes(data, label):
    sig = CHUNK_SIG[label]
    codec = detect_codec(data)
    pats = PATTERNS[codec]

    if data.startswith(b'RIFF'):
        total = struct.unpack('<I', data[4:8])[0]
        riff_end = min(8 + total, len(data))
    else:
        riff_end = _guess_main_area_end(data)

    offset = max(riff_end, 0)

    out = bytearray()
    count = 0
    found = False

    while True:
        idx = data.find(sig, offset)
        if idx < 0 or idx + 8 > len(data):
            break

        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        start = idx + 8
        end   = start + size
        offset = end

        if size > MAX_REASONABLE_CHUNK_SIZE or end > len(data):
            continue

        chunk = data[start:end]
        if (not found and pats['start'].match(chunk)) or (found and any(p.match(chunk) for p in pats['types'])):
            out += chunk
            found = True
            count += 1

    return bytes(out), count, codec

def extract_full_channel_bytes(data, label):
    sig = CHUNK_SIG[label]

    if data.startswith(b'RIFF'):
        total = struct.unpack('<I', data[4:8])[0]
        riff_end = min(8 + total, len(data))
    else:
        riff_end = _guess_main_area_end(data)

    offset = 0
    file_end = riff_end
    out = bytearray()

    while True:
        idx = data.find(sig, offset)
        if idx < 0 or idx + 8 > file_end:
            break

        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        start = idx + 8
        end   = start + size

        # 손상된 청크는 건너뜀
        if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE or end > file_end:
            offset = idx + 4
            continue

        out += data[start:end]
        offset = end

    return bytes(out)