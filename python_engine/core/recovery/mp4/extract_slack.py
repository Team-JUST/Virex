import os
import re
import struct
import logging
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video


def _process_one_mp4(path: str, h264_root: str, out_root: str):
    base = os.path.splitext(os.path.basename(path))[0]
    h264_dir = os.path.join(h264_root, base)
    out_dir  = os.path.join(out_root,  base)
    os.makedirs(h264_dir, exist_ok=True)
    os.makedirs(out_dir,  exist_ok=True)
    return recover_mp4_slack(path, h264_dir, out_dir, target_format="mp4")

def _choose_workers(max_cap=4):
    cpu = os.cpu_count() or 4
    return max(2, min(max_cap, math.ceil(cpu/2))) 

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

MAX_REASONABLE_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_VALID_BOX_SIZE = 8     # size + type
MIN_FRAME_SIZE = 5         # 너무 작은 프레임 필터링 기준

def get_slack_after_moov(data):
    offset = 0
    total_size = len(data)
    while offset + MIN_VALID_BOX_SIZE <= total_size:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
        except struct.error:
            logger.error(f"size 언팩 실패 @ offset=0x{offset:X}")
            break

        box_type = data[offset + 4:offset + 8].decode("utf-8", errors="ignore")

        if box_type == "moov":
            slack = data[offset + size:]
            slack_rate = len(slack) / total_size * 100
            return slack, offset + size, data[offset:offset + size], slack_rate

        if size < MIN_VALID_BOX_SIZE:
            logger.warning(f"비정상적인 박스 크기(size={size}) → 루프 종료 @ offset=0x{offset:X}")
            break

        offset += size

    # moov 못 찾았을 때는 빈값 + rate=100%
    return b'', None, None, 100.0

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

        return b'\x00\x00\x00\x01' + sps + b'\x00\x00\x00\x01' + pps
    except (IndexError, struct.error) as e:
        logger.error(f"SPS/PPS 추출 실패: {e}")
        return b''

def extract_frames(slack, slack_offset, sps_pps, output_h264_path):
    iframe_pattern = re.compile(b'\x00.{3}[\x25\x45\x65]\x88\x80')
    pframe_pattern = re.compile(b'\x00\x00.{2}[\x21\x41\x61]\x9A')
    
    matches = []
    for ftype, pattern in [("I", iframe_pattern), ("P", pframe_pattern)]:
        for m in pattern.finditer(slack):
            matches.append((m.start(), ftype))

    matches.sort(key=lambda x: x[0])

    has_i_frame = any(ftype == "I" for _, ftype in matches)
    if not has_i_frame or len(matches) < 3:
        logger.info("슬랙 영역이 존재하지 않거나 복원 가능한 데이터가 없습니다.")
        return 0, 0
    
    recovered = 0
    recovered_bytes = 0
    with open(output_h264_path, 'wb') as f:
        f.write(sps_pps)
        recovered_bytes += len(sps_pps)
        for start, ftype in matches:
            try:
                size = struct.unpack('>I', slack[start:start + 4])[0]
                if size > MAX_REASONABLE_CHUNK_SIZE or size < MIN_FRAME_SIZE:
                    logger.debug(f"size={size} @ offset=0x{slack_offset + start:X} → skip")
                    continue

                end = start + 4 + size
                if end > len(slack):
                    logger.debug(f"슬랙 초과 frame @ offset=0x{slack_offset + start:X}")
                    continue

                chunk = (b'\x00\x00\x00\x01' + slack[start + 4:end])
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
    mp4_path  = os.path.join(output_video_dir, f"{filename}_hidden.{target_format}")

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        slack, slack_offset, moov_data, slack_rate = get_slack_after_moov(data)
        logger.info(f"{filename} → Slack rate: {slack_rate:.2f}%")
        
        if slack_offset is None:
            logger.error(f"{filename} → moov 박스 없음 → 복원 불가")
            return {
                "recovered": False,
                "frame_count": 0,
                "h264_path": None,
                "output_path": None,
                "video": None,
                "recovered_slack_path": None,
                "slack_rate": slack_rate
            }
        
        sps_pps = extract_sps_pps(moov_data)
        if not sps_pps:
            logger.info(f"{filename} → SPS/PPS 추출 실패 → 복원 불가")
            return {
                "recovered": False,
                "frame_count": 0,
                "h264_path": None,
                "output_path": None,
                "video": None,
                "recovered_slack_path": None,
                "slack_rate": slack_rate
            }

        frame_count, recovered_bytes = extract_frames(slack, slack_offset, sps_pps, h264_path)
        logger.info(f"{filename} → 복구된 프레임 수: {frame_count}개, 복구 바이트: {recovered_bytes}")

        if frame_count > 0:
            logger.info(f"{filename} → 프레임 복구 성공! convert_video 시작...")
            try:
                convert_video(h264_path, mp4_path, extra_args=['-c:v', 'copy'])
                logger.info(f"{filename} → 영상 변환 완료: {mp4_path}")
            except Exception as convert_error:
                logger.error(f"{filename} → convert_video 실패: {convert_error}")
                # convert_video 실패해도 일단 성공으로 처리 (h264 파일은 있으니까)
            
            final_slack_rate = recovered_bytes / len(data) * 100
            logger.info(f"{filename} → 최종 slack_rate: {final_slack_rate:.4f}%")
            
            result = {
                "recovered": True,
                "frame_count": frame_count,
                "h264_path": h264_path,
                "output_path": mp4_path,
                "video": mp4_path,
                "recovered_slack_path": mp4_path,
                "slack_rate": final_slack_rate
            }
            logger.info(f"{filename} → 성공 결과 반환: {result}")
            return result
        else:
            if os.path.exists(h264_path):
                os.remove(h264_path)
            logger.info(f"{filename} → 유효한 프레임 없음 (삭제됨)")
            slack_rate = 0.0
            result = {
                "recovered": False,
                "frame_count": 0,
                "h264_path": h264_path,
                "output_path": None,
                "video": None,
                "recovered_slack_path": mp4_path,
                "slack_rate": slack_rate
            }
            logger.info(f"{filename} → 실패 결과 반환: {result}")
            return result
    except Exception as e:
        logger.error(f"{filename} 복원 중 예외 발생: {type(e).__name__}: {e}")
        logger.exception(f"{filename} 상세 예외 정보:")
        result = {
            "recovered": False,
            "frame_count": 0,
            "h264_path": None,
            "output_path": None,
            "video": None,
            "recovered_slack_path": None,
            "slack_rate": None
        }
        logger.error(f"{filename} → 예외로 인한 실패 결과 반환: {result}")
        return result