import os
import re
import struct
import logging
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video

logger = logging.getLogger(__name__)

MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_BOX_SIZE = 8
MIN_FRAME_SIZE = 5
NAL_START_CODE = b'\x00\x00\x00\x01'
IFRAME_PATTERN = re.compile(b'\x00.{3}[\x25\x45\x65]\x88\x80')
PFRAME_PATTERN = re.compile(b'\x00\x00.{2}[\x21\x41\x61]\x9A')

def get_slack_after_moov(data):
    offset = 0
    total_size = len(data)

    while offset + MIN_BOX_SIZE <= total_size:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
        except struct.error:
            logger.error(f"size 언팩 실패 @ offset=0x{offset:X}")
            break

        box_type = data[offset + 4:offset + 8].decode("utf-8", errors="ignore")
        if box_type == "moov":
            slack = data[offset + size:]
            return slack, offset + size, data[offset:offset + size]

        if size < MIN_BOX_SIZE:
            logger.warning(f"비정상적인 박스 크기(size={size}) → 루프 종료 @ offset=0x{offset:X}")
            break

        offset += size

    return b'', None, None

def extract_sps_pps(moov_data):
    avcc_pos = moov_data.find(b'avcC')
    if avcc_pos == -1:
        logger.error("avcC 박스를 찾을 수 없습니다.")
        return b''

    try:
        avcc_start = avcc_pos + 4
        sps_len = struct.unpack('>H', moov_data[avcc_start + 6:avcc_start + 8])[0]
        sps_start = avcc_start + 8
        sps = moov_data[sps_start:sps_start + sps_len]

        pps_len_start = sps_start + sps_len + 1
        pps_len = struct.unpack('>H', moov_data[pps_len_start:pps_len_start + 2])[0]
        pps_start = pps_len_start + 2
        pps = moov_data[pps_start:pps_start + pps_len]

        return NAL_START_CODE + sps + NAL_START_CODE + pps
    except (IndexError, struct.error) as e:
        logger.error(f"SPS/PPS 추출 실패: {e}")
        return b''

def extract_frames(slack, offset, sps_pps, output_path):
    matches = []

    for label, pattern in [("I", IFRAME_PATTERN), ("P", PFRAME_PATTERN)]:
        for m in pattern.finditer(slack):
            matches.append((m.start(), label))

    matches.sort(key=lambda x: x[0])

    has_i_frame = any(ftype == "I" for _, ftype in matches)
    if not has_i_frame or len(matches) < 3:
        logger.info("유효한 슬랙 프레임 없음")
        return 0, 0
    
    recovered = 0
    recovered_bytes = 0

    with open(output_path, 'wb') as f:
        f.write(sps_pps)
        recovered_bytes += len(sps_pps)

        for start in matches:
            try:
                size = struct.unpack('>I', slack[start:start + 4])[0]
                if size > MAX_CHUNK_SIZE or size < MIN_FRAME_SIZE:
                    logger.debug(f"size={size} @ 0x{offset + start:X} → skip")
                    continue

                end = start + 4 + size
                if end > len(slack):
                    logger.debug(f"슬랙 초과 frame @ 0x{offset + start:X}")
                    continue

                chunk = (NAL_START_CODE + slack[start + 4:end])
                f.write(chunk)
                recovered += 1
                recovered_bytes += len(chunk)
            except (struct.error, IndexError):
                continue

    return recovered, recovered_bytes

def recover_mp4_slack(filepath, output_h264_dir, output_video_dir, target_format="mp4"):
    os.makedirs(output_h264_dir, exist_ok=True)
    os.makedirs(output_video_dir, exist_ok=True)

    filename = os.path.splitext(os.path.basename(filepath))[0]
    h264_path = os.path.join(output_h264_dir, f"{filename}_slack.h264")
    mp4_path  = os.path.join(output_video_dir, f"{filename}_slack.{target_format}")

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        slack, slack_offset, moov_data = get_slack_after_moov(data)
        
        if slack_offset is None:
            logger.error(f"{filename} → moov 박스 없음 → 복원 불가")
            return _fail_result()
        
        sps_pps = extract_sps_pps(moov_data)
        if not sps_pps:
            logger.info(f"{filename} → SPS/PPS 추출 실패")
            return _fail_result()

        frame_count, recovered_bytes = extract_frames(slack, slack_offset, sps_pps, h264_path)
        slack_rate = round((recovered_bytes / len(data) * 100), 2) if len(data) else 0.0

        if frame_count == 0:
            if os.path.exists(h264_path):
                os.remove(h264_path)
            logger.info(f"{filename} → 유효한 프레임 없음")
            return _fail_result()

        try:
            convert_video(h264_path, mp4_path, extra_args=['-c:v', 'copy'])
            logger.info(f"{filename} → mp4 변환 완료")
        except Exception as convert_err:
            logger.error(f"{filename} → mp4 변환 실패: {convert_err}")

        final_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else recovered_bytes

        return {
            "recovered": True,
            "file_size_bytes": int(final_size),
            "video_path": mp4_path,
            "slack_rate": slack_rate
            }

    except Exception as e:
        logger.error(f"{filename} 복원 중 예외 발생: {type(e).__name__}: {e}")
        logger.exception(e)
        return _fail_result()
    
def _fail_result():
    return {
        "recovered": False,
        "file_size_bytes": 0,
        "video_path": None,
        "slack_rate": 0.0,
    }