
import re
import os
import logging
from python_engine.core.recovery.mp4.get_slack import get_slack

logger = logging.getLogger(__name__)

MAX_AUDIO_CHUNK_SIZE = 10 * 1024 * 1024
MIN_AUDIO_CHUNK_SIZE = 16

AUDIO_SIG_RE = re.compile(br"\x00\x00\x00\x02\x09[\x10\x30]\x00\x00")

GSENSORI = b"gsensori"

def extract_mp4_audio(filepath, output_audio_dir, also_try_0x1000=True):
    os.makedirs(output_audio_dir, exist_ok=True)
    name, _ = os.path.splitext(os.path.basename(filepath))
    raw_out = os.path.join(output_audio_dir, f"{name}_audio.raw")
    try:
        with open(filepath, "rb") as f:
            buf = f.read()
        slack, slack_offset, moov_data = get_slack(buf)
        if slack_offset is None:
            logger.error(f"{filepath} → moov 박스 없음(slack 없음)")
            return _fail_result()
        stats = extract_mp4_audio_between_frames(slack, raw_out, also_try_0x1000=also_try_0x1000)
        recovered = stats["total_audio_bytes"] > 0
        return {
            "recovered": recovered,
            "audio_size": f"{stats['total_audio_bytes']} bytes",
            "audio_path": raw_out if recovered else None
        }
    except Exception as e:
        logger.error(f"{filepath} 오디오 추출 중 예외 발생: {type(e).__name__}: {e}")
        return _fail_result()

def extract_mp4_audio_between_frames(buffer: bytes, raw_out_path: str, also_try_0x1000: bool = True) -> dict:
    total_audio_bytes = 0
    blocks = 0

    with open(raw_out_path, "wb") as raw_fp:
        search_pos = 0
        buflen = len(buffer)

        while True:
            # 1) Audio Signature 찾기
            m = AUDIO_SIG_RE.search(buffer, search_pos)
            if not m:
                break

            sig_start = m.start()
            sig_bytes = m.group()
            header_selector = sig_bytes[5]

            if header_selector == 0x10:
                header_size = 54
            elif header_selector == 0x30:
                header_size = 24
            else:
                search_pos = m.end()
                continue

            # 2) 프레임 크기 읽고 프레임 종료 오프로 이동
            read_offset = sig_start
            frame_size_offset = read_offset + header_size
            if frame_size_offset + 4 > buflen:
                search_pos = m.end()
                continue

            frame_size = int.from_bytes(buffer[frame_size_offset:frame_size_offset+4], "big")
            if frame_size > MAX_AUDIO_CHUNK_SIZE or frame_size < MIN_AUDIO_CHUNK_SIZE:
                logger.debug(f"비정상 프레임 크기 {frame_size} @ 0x{frame_size_offset:X}")
                search_pos = m.end()
                continue

            frame_end = frame_size_offset + 4 + frame_size
            if frame_end > buflen:
                search_pos = m.end()
                continue

            cur = frame_end

            # 3) 종료 지점 +10바이트에서 'gsensori' 검사
            if cur + 10 + len(GSENSORI) <= buflen and buffer[cur+10:cur+10+len(GSENSORI)] == GSENSORI:
                if cur + 2 <= buflen:
                    subtitle_size = int.from_bytes(buffer[cur:cur+2], "big")
                    # 비정상 값이면 스킵하지 않음
                    if 0 <= subtitle_size <= (buflen - cur):
                        cur += subtitle_size
                    else:
                        logger.debug(f"비정상 자막 크기 {subtitle_size} @ 0x{cur:X}, 스킵 안 함")
                else:
                    logger.debug("자막 길이 읽기 범위 초과")

            # 4) 오디오 블록 후보 거리들(우선순위: 0x800 → 0xA00 → [옵션] 0x1000)
            candidate_steps = [0x800, 0xA00]
            if also_try_0x1000:
                candidate_steps.append(0x1000)

            wrote_block = False

            while True:
                found = False
                for step in candidate_steps:
                    next_pos = cur + step
                    if next_pos + len(sig_bytes) <= buflen and buffer[next_pos:next_pos+len(sig_bytes)] == sig_bytes:
                        # step 길이만큼 오디오로 저장
                        audio_chunk = buffer[cur:cur+step]
                        raw_fp.write(audio_chunk)
                        total_audio_bytes += len(audio_chunk)
                        blocks += 1
                        # 다음 검색을 그 다음 Audio Sig에서 계속
                        search_pos = next_pos
                        wrote_block = True
                        found = True
                        break

                    # Audio Sig 대신 'gsensori'가 또 나온 경우: 자막 스킵하고 다시 0x800/0xA00/(0x1000) 재시도
                    if next_pos + 10 + len(GSENSORI) <= buflen and buffer[next_pos+10:next_pos+10+len(GSENSORI)] == GSENSORI:
                        if next_pos + 2 <= buflen:
                            subtitle_size2 = int.from_bytes(buffer[next_pos:next_pos+2], "big")
                            if 0 <= subtitle_size2 <= (buflen - next_pos):
                                cur = next_pos + subtitle_size2
                                # 자막을 건너뛴 뒤 같은 후보 거리로 다시 루프
                                found = True
                                break
                        # 읽기 실패/비정상: 해당 step은 포기하고 다른 step 시도
                if wrote_block:
                    break
                if not found:
                    # (규칙 4에 따라) 0x800/0xA00/0x1000 어떤 지점에도 Audio Sig가 없으면 이 시그니처는 건너뛰고 다음 시그니처 탐색
                    search_pos = m.end()
                    break

    return {
        "raw_path": raw_out_path,
        "audio_blocks": blocks,
        "total_audio_bytes": total_audio_bytes
    }

def _fail_result():
    return {
        "recovered": False,
        "audio_size": "0 B",
        "audio_path": None
    }