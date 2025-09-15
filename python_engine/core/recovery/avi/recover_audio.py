import logging
import struct

logger = logging.getLogger(__name__)

AUDIO_CHUNK_SIG = b'\x30\x32\x77\x62'  # '02wb'
MAX_AUDIO_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_AUDIO_CHUNK_SIZE = 16  

def extract_original_audio(data):
    """ 원본 음성 추출. 원본 채널 분리 시 사용 """
    if not data.startswith(b'RIFF'):
        logger.warning("RIFF 헤더가 없습니다.")
        return []

    chunks = []
    offset = 0
    count = 0
    real_file_size = struct.unpack('<I', data[4:8])[0]
    valid_end = 8 + real_file_size  

    while offset < valid_end:
        index = data.find(AUDIO_CHUNK_SIG, offset, valid_end) 
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
        count += 1
    
    return chunks

def extract_slack_audio(data):
    """ 슬랙 음성 추출. 슬랙 추출 시 사용 """
    chunks = []
    count = 0
    
    # RIFF 헤더가 있으면 정상 파일 영역 이후부터 시작
    if not data.startswith(b'RIFF'):
        logger.warning("RIFF 헤더가 없습니다.")
        offset = 0
    else:
        real_file_size = struct.unpack('<I', data[4:8])[0]
        offset = 8 + real_file_size  

    while offset < len(data):
        index = data.find(AUDIO_CHUNK_SIG, offset)
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
        count += 1
    
    return chunks
