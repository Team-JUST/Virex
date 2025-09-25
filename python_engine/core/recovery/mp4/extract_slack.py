import os
import re
import struct
import logging
import subprocess
import json
import math
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video, convert_audio
from python_engine.core.recovery.mp4.get_slack import get_slack
from python_engine.core.recovery.utils.unit import bytes_to_unit
from python_engine.core.recovery.mp4.extract_audio import extract_mp4_audio

logger = logging.getLogger(__name__)

FFMPEG = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))
FFPROBE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffprobe.exe'))

SLACK_IMAGE_THRESHOLD_SEC = 0.6
MAX_CHUNK_SIZE = 10 * 1024 * 1024  # 10MB
MIN_BOX_SIZE = 8
MIN_FRAME_SIZE = 5
NAL_START_CODE = b'\x00\x00\x00\x01'

# H264 패턴
H264_IFRAME_PATTERN = re.compile(b'\x00.{3}[\x25\x45\x65]\x88\x80')
H264_PFRAME_PATTERN = re.compile(b'\x00\x00.{2}[\x21\x41\x61]\x9A')

# H265 패턴 
H265_IFRAME_PATTERN = re.compile(b'\x00.{3}\x26\x01')
H265_PFRAME_PATTERN = re.compile(b'\x00\x00.{2}\x02\x01')

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

def detect_video_codec(data):
    if b'avcC' in data:
        return 'H264'
    if b'hvcC' in data:
        return 'H265'
    # H264 기본
    return 'H264'

def extract_sps_pps(moov_data):
    """H264와 H265의 SPS/PPS를 추출합니다."""
    codec = detect_video_codec(moov_data)
    
    if codec == 'H264':
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
            logger.error(f"H264 SPS/PPS 추출 실패: {e}")
            return b''
    elif codec == 'H265':
        hvcc_pos = moov_data.find(b'hvcC')
        if hvcc_pos == -1:
            logger.error("hvcC 박스를 찾을 수 없습니다.")
            return b''

        try:
            hvcc_start = hvcc_pos + 4
            offset = hvcc_start + 22
            num_arrays = moov_data[offset]
            offset += 1
            
            result = b''
            
            # 각 array 처리 (VPS, SPS, PPS 순서)
            for _ in range(num_arrays):
                if offset + 3 > len(moov_data):
                    break
                    
                nal_unit_type = moov_data[offset] & 0x3F
                offset += 1
                
                num_nalus = struct.unpack('>H', moov_data[offset:offset + 2])[0]
                offset += 2
                
                for _ in range(num_nalus):
                    if offset + 2 > len(moov_data):
                        break
                        
                    nalu_len = struct.unpack('>H', moov_data[offset:offset + 2])[0]
                    offset += 2
                    
                    if offset + nalu_len > len(moov_data):
                        break
                        
                    nalu = moov_data[offset:offset + nalu_len]
                    offset += nalu_len
                    
                    # NAL start code와 함께 추가
                    result += NAL_START_CODE + nalu
            
            return result
        except (IndexError, struct.error) as e:
            logger.error(f"H265 VPS/SPS/PPS 추출 실패: {e}")
            return b''
    else:
        logger.error(f"지원하지 않는 코덱: {codec}")
        return b''
    
def extract_sps_pps_anywhere(data):
    """데이터 전체에서 SPS/PPS를 찾습니다. H264와 H265 모두 지원."""
    codec = detect_video_codec(data)
    
    if codec == 'H264':
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
    elif codec == 'H265':
        pos = 0
        while True:
            hvcc_pos = data.find(b'hvcC', pos)
            if hvcc_pos == -1:
                return b''
            try:
                hvcc_start = hvcc_pos + 4
                offset = hvcc_start + 22
                num_arrays = data[offset]
                offset += 1
                
                result = b''
                
                for _ in range(num_arrays):
                    if offset + 3 > len(data):
                        break
                        
                    nal_unit_type = data[offset] & 0x3F
                    offset += 1
                    
                    num_nalus = struct.unpack('>H', data[offset:offset + 2])[0]
                    offset += 2
                    
                    for _ in range(num_nalus):
                        if offset + 2 > len(data):
                            break
                            
                        nalu_len = struct.unpack('>H', data[offset:offset + 2])[0]
                        offset += 2
                        
                        if offset + nalu_len > len(data):
                            break
                            
                        nalu = data[offset:offset + nalu_len]
                        offset += nalu_len
                        
                        result += NAL_START_CODE + nalu
                
                return result
            except (IndexError, struct.error):
                pos = hvcc_pos + 4
                continue
    else:
        return b''

def extract_frames(slack, offset, sps_pps, output_path, codec='H264'):
    matches = []
    has_i_frame = False

    if codec == 'H264':
        iframe_pattern = H264_IFRAME_PATTERN
        pframe_pattern = H264_PFRAME_PATTERN
    else:  # H265
        iframe_pattern = H265_IFRAME_PATTERN
        pframe_pattern = H265_PFRAME_PATTERN

    for m in iframe_pattern.finditer(slack):
        matches.append((m.start()))
        has_i_frame = True
    for m in pframe_pattern.finditer(slack):
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

def extract_frames_from_whole_file(data, sps_pps, output_path, codec='H264'):
    matches = []
    has_i_frame = False

    if codec == 'H264':
        iframe_pattern = H264_IFRAME_PATTERN
        pframe_pattern = H264_PFRAME_PATTERN
    else:  # H265
        iframe_pattern = H265_IFRAME_PATTERN
        pframe_pattern = H265_PFRAME_PATTERN

    for m in iframe_pattern.finditer(data):
        matches.append((m.start()))
        has_i_frame = True
    for m in pframe_pattern.finditer(data):
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
    
def _paths_for(filename, h264_dir, out_dir, suffix, codec='H264'):
    if codec == 'H265':
        raw_ext = 'h265'
    else:
        raw_ext = 'h264'
    
    raw_path = os.path.join(h264_dir, f"{filename}_{suffix}.{raw_ext}")
    mp4_path = os.path.join(out_dir, f"{filename}_{suffix}.mp4")
    jpeg_path = os.path.join(out_dir, f"{filename}_{suffix}.jpeg")
    return raw_path, mp4_path, jpeg_path

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
    
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # 먼저 코덱을 감지
        codec = detect_video_codec(data)
        
        # 파일 확장자를 코덱에 맞게 설정
        if codec == 'H265':
            raw_ext = 'h265'
        else:
            raw_ext = 'h264'
            
        raw_path = os.path.join(output_h264_dir, f"{filename}_slack.{raw_ext}")
        mp4_path = os.path.join(output_video_dir, f"{filename}_slack.{target_format}")
        jpeg_path = os.path.join(output_video_dir, f"{filename}_slack.jpeg")
        audio_dir = os.path.join(output_video_dir, "audio")
        
        slack, slack_offset, moov_data = get_slack(data)
        
        if slack_offset is None:
            logger.warning(f"{filename} → moov/슬랙 탐지 실패 → 전체 스캔 fallback")
            raw_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "damaged", codec)
            return _fallback_wholefile(
                data=data, filename=filename,
                h264_path=raw_path, mp4_path=mp4_path, jpeg_path=jpeg_path,
                use_gpu=use_gpu
            )

        if not slack:
            return {
                "recovered": False,
                "slack_size": "0 B",
                "video_path": None,
                "image_path": None,
                "is_image_fallback": False,
                "slack_rate": 0.0,
            }
        
        sps_pps = extract_sps_pps(moov_data)
        codec = detect_video_codec(moov_data)
        if not sps_pps:
            logger.info(f"{filename} → SPS/PPS 추출 실패 → 전체 스캔 fallback")
            raw_path, mp4_path, jpeg_path = _paths_for(filename, output_h264_dir, output_video_dir, "damaged", codec)
            return _fallback_wholefile(
                data=data, filename=filename,
                h264_path=raw_path, mp4_path=mp4_path, jpeg_path=jpeg_path,
                use_gpu=use_gpu
            )

        frame_count, recovered_bytes = extract_frames(slack, slack_offset, sps_pps, raw_path, codec)
        slack_rate = round((recovered_bytes / len(data) * 100), 2) if len(data) else 0.0

        if frame_count == 0:
            try:
                if os.path.exists(raw_path):
                    os.remove(raw_path)
            except Exception:
                pass
            return {
                "recovered": False,
                "slack_size": "0 B",
                "video_path": None,
                "image_path": None,
                "is_image_fallback": False,
                "slack_rate": slack_rate
            }

        try:
            common_args = [
                '-fflags', '+genpts',
                '-c:v', 'copy',
                '-movflags', '+faststart'
            ]
            convert_video(raw_path, mp4_path, extra_args=common_args)
            logger.info(f"{filename} → mp4 변환 완료")
        except Exception as convert_err:
            logger.error(f"{filename} → mp4 변환 실패: {convert_err}")
            if os.path.exists(mp4_path):
                try:
                    os.remove(mp4_path)
                except Exception:
                    pass
            return _fail_result()

        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except Exception:
                pass
        
        # 오디오 추출 및 처리
        audio_result = extract_mp4_audio(filepath, audio_dir)
        audio_path = None
        audio_size = "0 B"

        if audio_result.get('recovered', False):
            audio_path = audio_result['audio_path']
            audio_size = audio_result['audio_size']
            logger.info(f"{filename} → 오디오 추출 성공: {audio_path}")

            # 오디오 변환 (raw → mp3)
            if os.path.exists(audio_path):
                mp3_path = os.path.join(audio_dir, f"{filename}_audio.mp3")
                
                # 오디오 샘플레이트 확인
                try:
                    probe_out = subprocess.check_output([
                        FFPROBE, "-v", "quiet",
                        "-print_format", "json",
                        "-show_streams",
                        filepath
                    ], stderr=subprocess.DEVNULL)
                    probe_data = json.loads(probe_out.decode('utf-8', 'ignore'))
                    
                    audio_rate = 48000  # 기본값
                    for stream in probe_data.get('streams', []):
                        if stream.get('codec_type') == 'audio':
                            audio_rate = int(stream.get('sample_rate', 48000))
                            break
                except Exception:
                    logger.warning("오디오 샘플레이트 정보를 가져오는데 실패했습니다. 기본값 48000Hz를 사용합니다.")
                
                try:
                    convert_audio(audio_path, mp3_path, sample_rate=audio_rate, extra_args=[
                        '-c:a', 'libmp3lame',
                        '-q:a', '4'
                    ])
                    logger.info(f"{filename} → MP3 변환 성공 (sample_rate: {audio_rate}Hz)")
                    
                    try:
                        os.remove(audio_path)  # 원본 raw 파일 제거
                        audio_path = mp3_path  # 새 mp3 파일 경로로 업데이트
                        audio_size = bytes_to_unit(os.path.getsize(mp3_path))
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"{filename} → MP3 변환 실패: {e}")

        if os.path.exists(mp4_path):
            duration = get_video_duration_sec(mp4_path)

            # 1초 미만 영상이면 mp4 삭제, jpeg 생성
            if duration is not None and duration < 1.0:
                ok = extract_first_frame(mp4_path, jpeg_path)
                if ok:
                    try:
                        os.remove(mp4_path)
                    except Exception:
                        pass
                    final_size = os.path.getsize(jpeg_path) if os.path.exists(jpeg_path) else recovered_bytes
                    return {
                        "recovered": True,
                        "slack_size": bytes_to_unit(int(final_size)),
                        "video_path": None,
                        "image_path": jpeg_path,
                        "is_image_fallback": True,
                        "slack_rate": slack_rate,
                        "audio": {
                            "slack": {
                                "path": audio_path,
                                "size": audio_size
                            }
                        } if audio_result.get('recovered', False) and audio_path else {}
                    }
                else:
                    # jpeg 추출 실패 시 mp4 경로 반환
                    final_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else recovered_bytes
                    return {
                        "recovered": True,
                        "slack_size": bytes_to_unit(int(final_size)),
                        "video_path": mp4_path,
                        "image_path": None,
                        "is_image_fallback": False,
                        "slack_rate": slack_rate,
                        "audio": {
                            "slack": {
                                "path": audio_path,
                                "size": audio_size
                            }
                        } if audio_result.get('recovered', False) and audio_path else {}
                    }

            final_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else recovered_bytes
            result = {
                "recovered": True,
                "slack_size": bytes_to_unit(int(final_size)),
                "video_path": mp4_path,
                "image_path": None,
                "is_image_fallback": False,
                "slack_rate": slack_rate,
            }
            
            # 오디오 정보 추가
            if audio_result.get('recovered', False) and audio_path:
                result["audio"] = {
                    "slack": {
                        "path": audio_path,
                        "size": audio_size
                    }
                }
            
            return result
        
        else:
            logger.error(f"{filename} → mp4 파일 미생성")
            return _fail_result()
    
    except Exception as e:
        logger.error(f"{filename} 복원 중 예외 발생: {type(e).__name__}: {e}")
        logger.exception(e)
        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except Exception:
                pass
        return _fail_result()
    
def _fallback_wholefile(data, filename, h264_path, mp4_path, jpeg_path, use_gpu):
    sps_pps_any = extract_sps_pps_anywhere(data)
    codec = detect_video_codec(data)

    frame_count, recovered_bytes = extract_frames_from_whole_file(
        data=data,
        sps_pps=sps_pps_any,
        output_path=h264_path,
        codec=codec
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
            if ok:
                try:
                    os.remove(mp4_path)
                except Exception:
                    pass
                final_size = os.path.getsize(jpeg_path) if os.path.exists(jpeg_path) else recovered_bytes
                return {
                    "recovered": True,
                    "slack_size": bytes_to_unit(int(final_size)),
                    "video_path": None,
                    "image_path": jpeg_path,
                    "is_image_fallback": True,
                    "slack_rate": slack_rate,
                    "audio": {
                        "slack": {
                            "path": None,  # fallback에서는 오디오 없음
                            "size": "0 B"
                        }
                    }
                }
            else:
                # jpeg 추출 실패 시 mp4 경로 반환
                final_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else recovered_bytes
                return {
                    "recovered": True,
                    "slack_size": bytes_to_unit(int(final_size)),
                    "video_path": mp4_path,
                    "image_path": None,
                    "is_image_fallback": False,
                    "slack_rate": slack_rate,
                    "audio": {
                        "slack": {
                            "path": None,  # fallback에서는 오디오 없음
                            "size": "0 B"
                        }
                    }
                }
            
        final_size = os.path.getsize(mp4_path) if os.path.exists(mp4_path) else recovered_bytes
        return {
            "recovered": True,
            "slack_size": bytes_to_unit(int(final_size)),
            "video_path": mp4_path,
            "image_path": None,
            "is_image_fallback": False,
            "slack_rate": slack_rate,
            "audio": {
                "slack": {
                    "path": None,  # fallback에서는 오디오 없음
                    "size": "0 B"
                }
            }
        }
    
    else: 
        logger.info(f"[fallback] {filename} → mp4 생성 실패")
        return _fail_result()
