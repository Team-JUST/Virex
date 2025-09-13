import os
import re
import struct
import logging
import subprocess
import json
import math
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video
from python_engine.core.recovery.utils.unit import bytes_to_unit

logger = logging.getLogger(__name__)

FFMPEG = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))
FFPROBE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffprobe.exe'))

SLACK_IMAGE_THRESHOLD_SEC = 0.6
MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_BOX_SIZE = 8
MIN_FRAME_SIZE = 5
NAL_START_CODE = b'\x00\x00\x00\x01'
IFRAME_PATTERN = re.compile(b'\x00.{3}[\x25\x45\x65]\x88\x80')
PFRAME_PATTERN = re.compile(b'\x00\x00.{2}[\x21\x41\x61]\x9A')

def _process_one_mp4(path: str, h264_root: str, out_root: str):
    base = os.path.splitext(os.path.basename(path))[0]
    h264_dir = os.path.join(h264_root, base)
    out_dir  = os.path.join(out_root,  base)
    os.makedirs(h264_dir, exist_ok=True)
    os.makedirs(out_dir,  exist_ok=True)
    return recover_mp4_slack(path, h264_dir, out_dir, target_format="mp4", use_gpu=False)

def _choose_workers(max_cap=4):
    cpu = os.cpu_count() or 4
    return max(2, min(max_cap, math.ceil(cpu/2))) 

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
    
def extract_sps_pps_anywhere(data):
    pos = 0
    while True:
        avcc_pos = data.find(b'avcC', pos)
        if avcc_pos == -1:
            return b''
        try:
            avcc_start = avcc_pos + 4
            sps_len = struct.unpack('>H', data[avcc_start + 6:avcc_start + 8])[0]
            sps_start = avcc_start + 8
            sps = data[sps_start:sps_start + sps_len]

            pps_len_start = sps_start + sps_len + 1
            pps_len = struct.unpack('>H', data[pps_len_start:pps_len_start + 2])[0]
            pps_start = pps_len_start + 2
            pps = data[pps_start:pps_start + pps_len]

            return NAL_START_CODE + sps + NAL_START_CODE + pps
        except (IndexError, struct.error):
            pos = avcc_pos + 4
            continue

def extract_frames(slack, offset, sps_pps, output_path):
    matches = []
    has_i_frame = False

    for m in IFRAME_PATTERN.finditer(slack):
        matches.append((m.start()))
        has_i_frame = True
    for m in PFRAME_PATTERN.finditer(slack):
        matches.append((m.start()))

    matches.sort()

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

def extract_frames_from_whole_file(data, sps_pps, output_path):
    matches = []
    has_i_frame = False

    for m in IFRAME_PATTERN.finditer(data):
        matches.append((m.start()))
        has_i_frame = True
    for m in PFRAME_PATTERN.finditer(data):
        matches.append((m.start()))
    
    matches.sort()
    if not has_i_frame or len(matches) < 3:
        logger.info("유효한 프레임 없음")
        return 0, 0

    recovered = 0
    recovered_bytes = 0
    with open(output_path, 'wb') as f:
        f.write(sps_pps)
        recovered_bytes += len(sps_pps)

        for start in matches:
            try:
                size = struct.unpack('>I', data[start:start + 4])[0]
                if size > MAX_CHUNK_SIZE or size < MIN_FRAME_SIZE:
                    continue

                end = start + 4 + size
                if end > len(data):
                    continue

                chunk = (NAL_START_CODE + data[start + 4:end])
                f.write(chunk)
                recovered += 1
                recovered_bytes += len(chunk)
            except (struct.error, IndexError):
                continue
    
    return recovered, recovered_bytes

def get_video_frame_count(video_path):
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_read_frames',
            '-print_format', 'json',
            video_path
            ],
            stderr=subprocess.DEVNULL
        )
        meta = json.loads(out.decode('utf-8', 'ignore'))
        s = (meta.get('streams') or [{}])[0]
        nb = s.get('nb_frames')
        if nb not in (None, 'N/A'):
            return int(nb)
        
        out2 = subprocess.check_output(
            [FFPROBE, '-v', 'error',
            '-count_frames',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_read_frames',
            '-print_format', 'json',
            video_path
            ],
            stderr=subprocess.STDOUT
        )
        meta2 = json.loads(out2.decode('utf-8', 'ignore'))
        s2 = (meta2.get('streams') or [{}])[0]
        nb_read = s2.get('nb_read_frames')
        return int(nb_read) if nb_read not in (None, 'N/A') else None
    except Exception:
        return None
    
def get_video_duration_sec(video_path):
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            video_path],
            stderr=subprocess.STDOUT
        )
        meta = json.loads(out.decode('utf-8', 'ignore'))
        dur = float(meta.get('format', {}).get('duration', 0))
        return dur if dur >= 0 else -1.0
    except Exception:
        return -1.0

def extract_first_frame(video_path, out_jpeg):
    try:
        subprocess.run(
            [FFMPEG, '-y', '-i', video_path, '-frames:v', '1', out_jpeg],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return os.path.exists(out_jpeg)
    except Exception:
        return False
    
def _paths_for(filename, h264_dir, out_dir, suffix):
    h264_path = os.path.join(h264_dir, f"{filename}_{suffix}.h264")
    mp4_path  = os.path.join(out_dir,  f"{filename}_{suffix}.mp4")
    jpeg_path = os.path.join(out_dir,  f"{filename}_{suffix}.jpeg")
    return h264_path, mp4_path, jpeg_path

def _fail_result():
    return {
        "recovered": False,
        "slack_size": "0 B",
        "video_path": None,
        "image_path": None,
        "is_image_fallback": False,
        "slack_rate": 0.0,
    }

def recover_mp4_slack(filepath, output_h264_dir, output_video_dir, target_format="mp4", use_gpu=False):
    os.makedirs(output_h264_dir, exist_ok=True)
    os.makedirs(output_video_dir, exist_ok=True)

    filename = os.path.splitext(os.path.basename(filepath))[0]

    h264_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "slack")

    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        slack, slack_offset, moov_data = get_slack_after_moov(data)
        
        if slack_offset is None:
            logger.warning(f"{filename} → moov/슬랙 탐지 실패 → 전체 스캔 fallback")
            h264_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "damaged")
            return _fallback_wholefile(
                data=data, filename=filename,
                h264_path=h264_path, mp4_path=mp4_path, jpeg_path=jpeg_path,
                use_gpu=use_gpu
            )
        
        sps_pps = extract_sps_pps(moov_data)
        if not sps_pps:
            logger.info(f"{filename} → SPS/PPS 추출 실패 → 전체 스캔 fallback")
            h264_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "damaged")
            return _fallback_wholefile(
                data=data, filename=filename,
                h264_path=h264_path, mp4_path=mp4_path, jpeg_path=jpeg_path,
                use_gpu=use_gpu
            )

        frame_count, recovered_bytes = extract_frames(slack, slack_offset, sps_pps, h264_path)
        slack_rate = round((recovered_bytes / len(data) * 100), 2) if len(data) else 0.0

        if frame_count == 0:
            logger.info(f"{filename} → 슬랙 내 유효 프레임 없음 → 전체 스캔 fallback")
            try: os.remove(h264_path)
            except: pass
            h264_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "damaged")
            return _fallback_wholefile(
                data=data, filename=filename,
                h264_path=h264_path, mp4_path=mp4_path, jpeg_path=jpeg_path,
                use_gpu=use_gpu
            )

        try:
            convert_video(h264_path, mp4_path, extra_args=['-c:v', 'copy'], use_gpu=use_gpu, wait=True)
            logger.info(f"{filename} → mp4 변환 완료")
        except Exception as convert_err:
            logger.error(f"{filename} → mp4 변환 실패: {convert_err}")


        if os.path.exists(h264_path):
            try:
                os.remove(h264_path)
            except Exception:
                pass
        
        if os.path.exists(mp4_path):
            duration = get_video_duration_sec(mp4_path)

            # 1초 미만 영상이면 mp4 삭제, jpeg 생성
            if duration is not None and duration < 1.0:
                ok = extract_first_frame(mp4_path, jpeg_path)
                try:
                    os.remove(mp4_path)
                except Exception:
                    pass
                if ok:
                    final_size = os.path.getsize(jpeg_path) if os.path.exists(jpeg_path) else recovered_bytes
                    return {
                        "recovered": True,
                        "slack_size": bytes_to_unit(int(final_size)),
                        "video_path": None,
                        "image_path": jpeg_path,
                        "is_image_fallback": True,
                        "slack_rate": slack_rate
                    }
                else:
                    # jpeg 추출 실패 시 mp4 경로 반환
                    final_size = os.path.getsize(mp4_path)
                    return {
                        "recovered": True,
                        "slack_size": bytes_to_unit(int(final_size)),
                        "video_path": mp4_path,
                        "image_path": None,
                        "is_image_fallback": False,
                        "slack_rate": slack_rate
                    }
            else:
                # 1초 이상이면 mp4 경로 반환
                final_size = os.path.getsize(mp4_path)
                return {
                    "recovered": True,
                    "slack_size": bytes_to_unit(int(final_size)),
                    "video_path": mp4_path,
                    "image_path": None,
                    "is_image_fallback": False,
                    "slack_rate": slack_rate
                }
        else:
            logger.error(f"{filename} → mp4 파일 미생성")
            return _fail_result()
    
    except Exception as e:
        logger.error(f"{filename} 복원 중 예외 발생: {type(e).__name__}: {e}")
        logger.exception(e)
        if os.path.exists(h264_path):
            try:
                os.remove(h264_path)
            except Exception:
                pass
        return _fail_result()
    
def _fallback_wholefile(data, filename, h264_path, mp4_path, jpeg_path, use_gpu):
    sps_pps_any = extract_sps_pps_anywhere(data)

    frame_count, recovered_bytes = extract_frames_from_whole_file(
        data=data,
        sps_pps=sps_pps_any,
        output_path=h264_path
    )
    slack_rate = round((recovered_bytes / len(data) * 100), 2) if len(data) else 0.0

    if frame_count == 0:
        if os.path.exists(h264_path):
            try:
                os.remove(h264_path)
            except Exception:
                pass
        return _fail_result()
    
    try:
        convert_video(h264_path, mp4_path, extra_args=['-c:v', 'copy'], use_gpu=use_gpu, wait=True)
        logger.info(f"[fallback] {filename} → mp4 변환 완료")
    except Exception as convert_err:
        logger.error(f"[fallback] {filename} → mp4 변환 실패: {convert_err}")

    if os.path.exists(h264_path):
        try:
            os.remove(h264_path)
        except Exception:
            pass

    if os.path.exists(mp4_path):
        duration = get_video_duration_sec(mp4_path)

        # 1초 미만 영상이면 mp4 삭제, jpeg 생성
        if duration is not None and duration < 1.0:
            ok = extract_first_frame(mp4_path, jpeg_path)
            try:
                os.remove(mp4_path)
            except Exception:
                pass
            if ok:
                final_size = os.path.getsize(jpeg_path) if os.path.exists(jpeg_path) else recovered_bytes
                return {
                    "recovered": True,
                    "slack_size": bytes_to_unit(int(final_size)),
                    "video_path": None,
                    "image_path": jpeg_path,
                    "is_image_fallback": True,
                    "slack_rate": slack_rate
                }
            else:
                # jpeg 추출 실패 시 mp4 경로 반환
                final_size = os.path.getsize(mp4_path)
                return {
                    "recovered": True,
                    "slack_size": bytes_to_unit(int(final_size)),
                    "video_path": mp4_path,
                    "image_path": None,
                    "is_image_fallback": False,
                    "slack_rate": slack_rate
                }
        else:
            # 1초 이상이면 mp4 경로 반환
            final_size = os.path.getsize(mp4_path)
            return {
                "recovered": True,
                "slack_size": bytes_to_unit(int(final_size)),
                "video_path": mp4_path,
                "image_path": None,
                "is_image_fallback": False,
                "slack_rate": slack_rate
            }
    
    logger.info(f"[fallback] {filename} → mp4 생성 실패")
    return _fail_result()