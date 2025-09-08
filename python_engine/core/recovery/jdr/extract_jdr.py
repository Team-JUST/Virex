from encodings.cp932 import codec
import os
import re
import struct
import datetime
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video

MAX_REASONABLE_CHUNK_SIZE = 10 * 1024 * 1024
MIN_REASONABLE_CHUNK_SIZE = 16
HEADER_SKIP = 20
CHUNK_SIG = {
    'front': [b'00VI', b'00VP'],
    'rear':  [b'01VI', b'01VP'],
    'side':  [b'02VI', b'02VP'],
    'audio': [b'00AD', b'01AD', b'02AD'],
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

def find_next(data, start, sigs):
    sig, idx = None, -1
    for s in sigs:
        i = data.find(s, start)
        if i != -1 and (idx == -1 or i < idx):
            sig, idx = s, i
    return sig, idx

def timestamp(data):
    YYYY = struct.unpack('<H', data[4:6])[0]
    MM = struct.unpack('<H', data[6:8])[0]
    DD = struct.unpack('<H', data[10:12])[0]
    hh = struct.unpack('<H', data[12:14])[0]
    mm = struct.unpack('<H', data[14:16])[0]
    ss = struct.unpack('<H', data[16:18])[0]
    msec = struct.unpack('<H', data[18:20])[0]
    return YYYY, MM, DD, hh, mm, ss, msec

def split_channel_bytes(data, label):
    video_sigs = CHUNK_SIG[label]
    audio_sig = {
        'front': b'00AD',
        'rear':  b'01AD',
        'side':  b'02AD',
    }[label]
    codec = 'H264'
    pats = PATTERNS[codec]
    offset = 0

    out_video = bytearray()
    video_count = 0
    found_start = False
    prev_time = None
    file_idx = 0
    video_outputs = []

    out_audio = bytearray()
    audio_count = 0
    audio_file_idx = 0
    audio_outputs = []
    audio_prev_time = None

    def to_datetime(YYYY, MM, DD, hh, mm, ss, msec):
        try:
            return datetime.datetime(YYYY, MM, DD, hh, mm, ss, msec*1000)
        except Exception:
            return None

    while True:
        sig, idx = find_next(data, offset, video_sigs + [audio_sig])
        if idx == -1 or idx + 8 > len(data):
            break
        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        YYYY, MM, DD, hh, mm, ss, msec = timestamp(data[idx + 8:idx + 8 + HEADER_SKIP])
        curr_time = to_datetime(YYYY, MM, DD, hh, mm, ss, msec)
        start = idx + 8 + HEADER_SKIP
        end = start + size
        offset = end
        if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE:
            offset = idx + 4
            continue
        if end > len(data):
            offset = idx + 4
            continue

        chunk = data[start:end]

        if sig in video_sigs:
            # 비디오 처리
            if (not found_start and pats['start'].match(chunk)) or (found_start and any(p.match(chunk) for p in pats['types'])):
                if prev_time is not None and curr_time is not None:
                    if abs((curr_time - prev_time).total_seconds()) > 60:
                        print(f"파일 분리: {label}_output_{file_idx}.bin (timestamp: {prev_time} -> {curr_time})")
                        video_outputs.append((file_idx, out_video))
                        file_idx += 1
                        out_video = bytearray()
                prev_time = curr_time
                out_video += chunk
                found_start = True
                video_count += 1
        elif sig == audio_sig:
            # 오디오 처리: found_start 이후부터만 저장
            if found_start:
                if audio_prev_time is not None and curr_time is not None:
                    if abs((curr_time - audio_prev_time).total_seconds()) > 60:
                        print(f"오디오 파일 분리: {label}_audio_output_{audio_file_idx}.bin (timestamp: {audio_prev_time} -> {curr_time})")
                        audio_outputs.append((audio_file_idx, out_audio))
                        audio_file_idx += 1
                        out_audio = bytearray()
                audio_prev_time = curr_time
                out_audio += chunk
                audio_count += 1

    if out_video:
        video_outputs.append((file_idx, out_video))
    if out_audio:
        audio_outputs.append((audio_file_idx, out_audio))

    for idx, data_bytes in video_outputs:
        with open(f"{label}_output_{idx}.bin", "wb") as out_f:
            out_f.write(data_bytes)
    for idx, data_bytes in audio_outputs:
        with open(f"{label}_audio_output_{idx}.bin", "wb") as out_f:
            out_f.write(data_bytes)

    all_video_bytes = b"".join([b for _, b in video_outputs])
    all_audio_bytes = b"".join([b for _, b in audio_outputs])
    return all_video_bytes, video_count, all_audio_bytes, audio_count, codec

def extract_full_channel_bytes(data, label):
    sigs = CHUNK_SIG[label]
    codec = 'H264'
    pats = PATTERNS[codec]
    offset = 0
    out = bytearray()
    count = 0
    found_start = False
    prev_time = None
    file_idx = 0
    outputs = []

    def parse_timestamp(ts_str):
        # "YYYY-MM-DD hh:mm:ss.msec" -> datetime
        try:
            return datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            return None

    while True:
        sig, idx = find_next(data, offset, sigs)
        if idx == -1 or idx + 8 > len(data):
            break
        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        timestamp_str = timestamp(data[idx + 8:idx + 8 + HEADER_SKIP])
        start = idx + 8 + HEADER_SKIP
        end = start + size
        offset = end
        if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE:
            offset = idx + 4
            continue
        if end > len(data):
            offset = idx + 4
            continue

        chunk = data[start:end]

        # start NAL 만났거나, 이후 정상 NAL
        if (not found_start and pats['start'].match(chunk)) or (found_start and any(p.match(chunk) for p in pats['types'])):
            curr_time = parse_timestamp(timestamp_str)
            if prev_time is not None and curr_time is not None:
                # 임계값: 1분(60초) 이상 차이나면 분리
                if abs((curr_time - prev_time).total_seconds()) > 60:
                    # 이전 파일 저장
                    outputs.append((file_idx, out))
                    file_idx += 1
                    out = bytearray()
            prev_time = curr_time
            print(f"count: {count}, timestamp: {timestamp_str}")
            out += chunk
            found_start = True
            count += 1

    # 마지막 파일 저장
    if out:
        outputs.append((file_idx, out))

    # 파일로 저장
    for idx, data_bytes in outputs:
        with open(f"{label}_output_{idx}.bin", "wb") as out_f:
            out_f.write(data_bytes)

    # 전체 합친 bytes, count, codec 반환 (기존 인터페이스 유지)
    all_bytes = b"".join([b for _, b in outputs])
    return all_bytes, count, codec

def extract_audio(data, label):
    sigs = CHUNK_SIG[label]
    codec = 'H264'
    pats = PATTERNS[codec]
    results = []

    def to_datetime(YYYY, MM, DD, hh, mm, ss, msec):
        try:
            return datetime.datetime(YYYY, MM, DD, hh, mm, ss, msec*1000)
        except Exception:
            return None

    for sig_idx, sig in enumerate(sigs):
        offset = 0
        out = bytearray()
        count = 0
        found_start = False
        prev_time = None
        file_idx = 0
        outputs = []

        while True:
            _, idx = find_next(data, offset, [sig])
            if idx == -1 or idx + 8 > len(data):
                break
            size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
            YYYY, MM, DD, hh, mm, ss, msec = timestamp(data[idx + 8:idx + 8 + HEADER_SKIP])
            curr_time = to_datetime(YYYY, MM, DD, hh, mm, ss, msec)
            start = idx + 8 + HEADER_SKIP
            end = start + size
            offset = end
            if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE:
                offset = idx + 4
                continue
            if end > len(data):
                offset = idx + 4
                continue

            chunk = data[start:end]

            if (not found_start and pats['start'].match(chunk)) or (found_start and any(p.match(chunk) for p in pats['types'])):
                if prev_time is not None and curr_time is not None:
                    if abs((curr_time - prev_time).total_seconds()) > 60:
                        print(f"파일 분리: {label}_{sig_idx}_output_{file_idx}.bin (timestamp: {prev_time} -> {curr_time})")
                        outputs.append((file_idx, out))
                        file_idx += 1
                        out = bytearray()
                prev_time = curr_time
                out += chunk
                found_start = True
                count += 1

        if out:
            outputs.append((file_idx, out))

        for idx, data_bytes in outputs:
            with open(f"{label}_{sig_idx}_output_{idx}.bin", "wb") as out_f:
                out_f.write(data_bytes)

        all_bytes = b"".join([b for _, b in outputs])
        results.append((all_bytes, count, codec))

    # 여러 시그니처 결과를 리스트로 반환
    return results