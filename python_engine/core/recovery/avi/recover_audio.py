import logging
import struct

logger = logging.getLogger(__name__)

AUDIO_CHUNK_SIG = [b'00wb', b'01wb', b'02wb']
MAX_AUDIO_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_AUDIO_CHUNK_SIZE = 16  

def extract_original_audio(data):
    """ 원본 음성 추출. 00wb, 01wb, 02wb 중 가장 먼저 나오는 시그니처만 사용 """
    if not data.startswith(b'RIFF'):
        logger.warning("RIFF 헤더가 없습니다.")
        return []

    # 가장 먼저 나오는 시그니처 찾기
    min_idx = len(data)
    found_sig = None
    for sig in AUDIO_CHUNK_SIG:
        idx = data.find(sig)
        if 0 <= idx < min_idx:
            min_idx = idx
            found_sig = sig
    if not found_sig:
        return []

    chunks = []
    offset = 0
    real_file_size = struct.unpack('<I', data[4:8])[0]
    valid_end = 8 + real_file_size

    while offset < valid_end:
        index = data.find(found_sig, offset, valid_end)
        if index == -1 or index + 8 > valid_end:
            break

        size = struct.unpack('<I', data[index+4:index+8])[0]
        chunk_start = index + 8
        chunk_end = chunk_start + size

        if size > MAX_AUDIO_CHUNK_SIZE:
            offset = index + 4
            continue
        if size <= MIN_AUDIO_CHUNK_SIZE:
            offset = index + 4
            continue
        if chunk_end > len(data):
            offset = index + 4
            continue

        chunks.append(data[chunk_start:chunk_end])
        offset = chunk_end
    return chunks

def extract_slack_audio(data):
    """ 슬랙 음성 추출. 슬랙 추출 시 사용. 00wb, 01wb, 02wb 중 가장 먼저 나오는 시그니처만 사용 """
    # 가장 먼저 나오는 시그니처 찾기
    min_idx = len(data)
    found_sig = None
    for sig in AUDIO_CHUNK_SIG:
        idx = data.find(sig)
        if 0 <= idx < min_idx:
            min_idx = idx
            found_sig = sig
    if not found_sig:
        return []

    chunks = []
    # RIFF 헤더가 있으면 정상 파일 영역 이후부터 시작
    if not data.startswith(b'RIFF'):
        logger.warning("RIFF 헤더가 없습니다.")
        offset = 0
    else:
        real_file_size = struct.unpack('<I', data[4:8])[0]
        offset = 8 + real_file_size

    while offset < len(data):
        index = data.find(found_sig, offset)
        if index == -1 or index + 8 > len(data):
            break

        size = struct.unpack('<I', data[index+4:index+8])[0]
        chunk_start = index + 8
        chunk_end = chunk_start + size

        if size > MAX_AUDIO_CHUNK_SIZE:
            offset = index + 4
            continue
        if size <= MIN_AUDIO_CHUNK_SIZE:
            offset = index + 4
            continue
        if chunk_end > len(data):
            offset = index + 4
            continue

        chunks.append(data[chunk_start:chunk_end])
        offset = chunk_end
    return chunks
