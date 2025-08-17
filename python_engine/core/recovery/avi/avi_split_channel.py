import os
import re
import struct
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video

MAX_CHUNK = 10 * 1024 * 1024
CHUNK_SIG = {
    'front': b'00dc',
    'rear':  b'01dc',
    'side':  b'02dc',
}

PATTERNS = {
    'H264': {
        'start': re.compile(b'\x00{2,3}\x01\x67'),  # SPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x67'),
            re.compile(b'\x00{2,3}\x01\x68'),
            re.compile(b'\x00{2,3}\x01[\x25\x45\x65]'),
            re.compile(b'\x00{2,3}\x01[\x21\x41\x61]'),
        ]
    },
    'HEVC': {
        'start': re.compile(b'\x00{2,3}\x01\x40'),  # VPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x40'),
            re.compile(b'\x00{2,3}\x01\x42'),
            re.compile(b'\x00{2,3}\x01\x44'),
            re.compile(b'\x00{2,3}\x01\x26'),
            re.compile(b'\x00{2,3}\x01\x02'),
        ]
    }
}

def detect_codec(data):
    hdr = data[112:116]
    if hdr in (b'h264', b'H264', b'\x68\x32\x36\x34'):
        return 'H264'
    if hdr in (b'hev1', b'HEV1', b'\x68\x65\x76\x31'):
        return 'HEVC'
    raise RuntimeError(f"Unknown codec header: {hdr!r}")

def split_channel_bytes(data, label):
    sig = CHUNK_SIG[label]
    codec = detect_codec(data)
    pats = PATTERNS[codec]

    # RIFF 헤더 건너뛰기
    offset = 0
    if data.startswith(b'RIFF'):
        total = struct.unpack('<I', data[4:8])[0]
        offset = 8 + total

    out = bytearray()
    count = 0
    found = False

    while True:
        idx = data.find(sig, offset)
        if idx < 0 or idx + 8 > len(data):
            break
        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        start = idx + 8
        end = start + size
        offset = end
        if size > MAX_CHUNK or end > len(data):
            continue

        chunk = data[start:end]
        # start NAL 만났거나, 이후 정상 NAL
        if (not found and pats['start'].match(chunk)) or (found and any(p.match(chunk) for p in pats['types'])):
            out += chunk
            found = True
            count += 1

    return bytes(out), count, codec

def extract_full_channel_bytes(data, label):
    sig = CHUNK_SIG[label]

    offset = 0
    if data.startswith(b'RIFF'):
        total_size = struct.unpack('<I', data[4:8])[0]
        file_end = 8 + total_size
    else:
        file_end = len(data)

    out = bytearray()

    while True:
        idx = data.find(sig, offset)
        if idx < 0 or idx + 8 > file_end:
            break
        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        start = idx + 8
        end = start + size

        if end > file_end:
            break

        out += data[start:end]
        offset = end
    
    return bytes(out)