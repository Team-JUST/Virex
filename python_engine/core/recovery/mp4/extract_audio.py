import re
import os
import struct
import logging
from python_engine.core.recovery.utils.unit import bytes_to_unit
from python_engine.core.recovery.mp4.get_slack_after_moov import get_slack_after_moov

logger = logging.getLogger(__name__)

# Audio extraction constants
AUDIO_SIGNATURE = b'\x00\x00\x00\x02\x09[\x10\x30]\x00\x00'
IFRAME_PATTERN = b'\x00.{3}[\x25\x45\x65]\x88'
MAX_AUDIO_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_AUDIO_CHUNK_SIZE = 16  # 최소 청크 크기

def extract_mp4_audio(filepath, output_audio_dir):
    os.makedirs(output_audio_dir, exist_ok=True)
    filename = os.path.splitext(os.path.basename(filepath))[0]
    raw_path = os.path.join(output_audio_dir, f"{filename}_audio.raw")

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        slack, slack_offset, moov_data = get_slack_after_moov(data)
        if slack_offset is None:
            logger.error(f"{filename} → moov 박스 없음")
            return _fail_result()

        # 첫 번째 I-Frame 찾기
        iframe_regex = re.compile(IFRAME_PATTERN)
        matches = list(iframe_regex.finditer(slack))
        if not matches:
            logger.error(f"{filename} → I-Frame을 찾을 수 없음")
            return _fail_result()

        # 첫 I-Frame의 끝 위치 계산
        first_iframe_end = None
        for m in matches:
            try:
                size = struct.unpack(">I", slack[m.start():m.start()+4])[0]
                first_iframe_end = m.start() + 4 + size
                break
            except struct.error:
                continue

        if first_iframe_end is None:
            logger.error(f"{filename} → 첫 I-Frame 끝 위치 계산 실패")
            return _fail_result()

        # 오디오 청크 추출
        audio_data = extract_audio_chunks(slack[first_iframe_end:], first_iframe_end)
        if not audio_data:
            logger.info(f"{filename} → 추출된 오디오 청크 없음")
            return _fail_result()

        # Raw 파일로 저장
        with open(raw_path, 'wb') as f:
            f.write(audio_data)

        recovered_bytes = os.path.getsize(raw_path)
        logger.info(f"{filename} → 추출된 오디오 데이터: {bytes_to_unit(recovered_bytes)}")

        return {
            "recovered": True,
            "audio_size": bytes_to_unit(recovered_bytes),
            "audio_path": raw_path  # raw 파일 경로 반환
        }

    except Exception as e:
        logger.error(f"{filename} 오디오 추출 중 예외 발생: {type(e).__name__}: {e}")
        return _fail_result()


def extract_audio_chunks(buffer, base_offset=0):
    """테스트 코드와 동일한 방식으로 오디오 청크를 추출합니다."""
    audio_regex = re.compile(AUDIO_SIGNATURE, re.MULTILINE | re.DOTALL)
    matches = list(audio_regex.finditer(buffer))
    
    if not matches:
        logger.info("오디오 청크를 찾을 수 없음")
        return b''

    logger.info(f"발견된 오디오 청크 수: {len(matches)}")
    start_offset_list = [match.start() for match in matches]
    
    audio_data = bytearray()
    saved_chunks = 0

    for idx, match in enumerate(matches):
        try:
            read_offset = match.start()
            matched = match.group()
            
            # 헤더 크기 결정 (테스트 코드와 동일)
            if matched[5] == 0x10:
                header_size = 54
            elif matched[5] == 0x30:
                header_size = 24
            else:
                continue

            # 프레임 크기 읽기
            frame_size_offset = read_offset + header_size
            if frame_size_offset + 4 > len(buffer):
                continue
                
            frame_size = int.from_bytes(buffer[frame_size_offset:frame_size_offset + 4], 'big')
            if frame_size > MAX_AUDIO_CHUNK_SIZE or frame_size < MIN_AUDIO_CHUNK_SIZE:
                logger.debug(f"비정상 프레임 크기: {frame_size} bytes @ offset 0x{base_offset + read_offset:X}")
                continue

            # 프레임 데이터 건너뛰기
            cur_pos = frame_size_offset + 4 + frame_size

            # 자막 데이터 확인 (10바이트)
            if cur_pos + 10 > len(buffer):
                continue
                
            subtitle_check = buffer[cur_pos:cur_pos + 10]
            if b'gsensori' in subtitle_check:
                subtitle_size = int.from_bytes(subtitle_check[:2], 'big')
                raw_audio_start = cur_pos + 2 + subtitle_size
            else:
                raw_audio_start = cur_pos

            # 기본 오디오 크기는 4096 바이트
            audio_size = 4096
            
            # 다음 오프셋과의 차이를 계산하여 오디오 크기 조정
            try:
                next_offset = start_offset_list[idx + 1]
                cur_offset_after_read = raw_audio_start + audio_size
                difference = next_offset - cur_offset_after_read
                
                if difference < 0:
                    audio_size = 2048  # 공간이 부족하면 2048바이트로 줄임
                    cur_offset_after_read = raw_audio_start + audio_size
                
                logger.debug(f'IDX: {idx+1}, CUR_POS: {cur_offset_after_read}, NEXT_OFFSET: {next_offset}, DIFFERENCE: {difference}')
            except IndexError:
                # 마지막 청크인 경우
                pass

            # 오디오 데이터 추출
            if raw_audio_start + audio_size <= len(buffer):
                raw_audio_data = buffer[raw_audio_start:raw_audio_start + audio_size]
                if len(raw_audio_data) == audio_size:
                    audio_data.extend(raw_audio_data)
                    saved_chunks += 1
                    
        except Exception as e:
            logger.debug(f"청크 {idx} 처리 중 오류: {e}")
            continue

    logger.info(f"저장된 오디오 청크 수: {saved_chunks}")
    return bytes(audio_data)


def _fail_result():
    return {
        "recovered": False,
        "audio_size": "0 B",
        "audio_path": None
    }
