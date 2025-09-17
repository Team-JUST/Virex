import os
import logging
import shutil
import subprocess
import json
from python_engine.core.recovery.avi.avi_split_channel import (
    split_channel_bytes,
    extract_full_channel_bytes)
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video
from python_engine.core.recovery.utils.unit import bytes_to_unit

logger = logging.getLogger(__name__)

FFMPEG = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))
FFPROBE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffprobe.exe'))
SLACK_IMAGE_THRESHOLD_SEC = 0.6

def find_nal_start(buf, start):
    idx3 = buf.find(b'\x00\x00\x01', start)
    idx4 = buf.find(b'\x00\x00\x00\x01', start)
    candidates = [idx for idx in (idx3, idx4) if idx >= 0]
    if not candidates:
        return -1, 0
    idx = min(candidates)
    prefix_len = 4 if idx == idx4 else 3
    return idx, prefix_len

def extract_sps_pps_from_raw(raw, codec, label):
    # HEVC 여부 확장 판별
    is_hevc = any(x in codec.lower() for x in ('265', 'hev1', 'hevc', 'hvc1'))
    vps = sps = pps = b''
    i = 0

    while True:
        idx, prefix_len = find_nal_start(raw, i)
        if idx < 0:
            break
        nal_start = idx + prefix_len
        next_idx, _ = find_nal_start(raw, nal_start)
        nal = raw[nal_start : next_idx if next_idx > 0 else len(raw)]
        if not nal:
            break

        first = nal[0]
        if is_hevc:
            nal_type = (first >> 1) & 0x3F
            if nal_type == 32:
                vps = nal
            elif nal_type == 33:
                sps = nal
            elif nal_type == 34:
                pps = nal
        else:
            nal_type = first & 0x1F
            if nal_type == 7:
                sps = nal
            elif nal_type == 8:
                pps = nal

        if (is_hevc and vps and sps and pps) or (not is_hevc and sps and pps):
            break
        i = nal_start

    if is_hevc:
        if not (vps and sps and pps):
            logger.error(f"[{label}] raw에서 VPS/SPS/PPS를 못 찾음 (codec={codec})")
            return b''
        return b'\x00\x00\x00\x01' + vps + b'\x00\x00\x00\x01' + sps + b'\x00\x00\x00\x01' + pps
    else:
        if not (sps and pps):
            logger.error(f"[{label}] raw에서 SPS/PPS를 못 찾음 (codec={codec})")
            return b''
        return b'\x00\x00\x00\x01' + sps + b'\x00\x00\x00\x01' + pps

def extract_frames_from_raw(raw, sps_pps, out_fn):
    if not sps_pps:
        return 0, 0
    
    stream = sps_pps + raw
    count = 0
    recovered_bytes = len(sps_pps)

    with open(out_fn, 'wb') as wf:
        wf.write(sps_pps)
        pos = 0
        while True:
            idx, prefix = find_nal_start(stream, pos)
            if idx < 0:
                break
            nal_start = idx + prefix
            next_idx, _ = find_nal_start(stream, nal_start)
            nal = stream[nal_start:next_idx if next_idx > 0 else len(stream)]
            if not nal:
                break

            wf.write((b'\x00\x00\x00\x01' if prefix == 4 else b'\x00\x00\x01') + nal)
            recovered_bytes += len(nal) + (4 if prefix == 4 else 3)
            count += 1
            pos = nal_start

    return count, recovered_bytes

def get_video_frame_count(video_path):
    try:
        out = subprocess.check_output(
            [FFPROBE, '-v', 'error',
            '-show-entries', 'format=nb_frames',
            '-print_format', 'json',
            video_path],
            stderr=subprocess.DEVNULL
        )
        meta = json.loads(out.decode('utf-8', 'ignore'))
        s = (meta.get("streams") or [{}])[0]
        nb = s.get("nb_frames")
        if nb not in (None, 'N/A'):
            return int(nb)
        
        out2 = subprocess.check_output(
            [FFPROBE, '-v', 'error',
            '-select_streams', 'v:0',
            '-count_frames',
            '-show_entries', 'stream=nb_read_frames',
            '-print_format', 'json',
            video_path],
            stderr=subprocess.DEVNULL
        )
        meta2 = json.loads(out2.decode('utf-8', 'ignore'))
        s2 = (meta2.get("streams") or [{}])[0]
        nb_read = s2.get("nb_read_frames")
        return int(nb_read) if nb_read not in (None, 'N/A') else 0
    except Exception:
        return None
    
def get_video_duration_sec(video_path: str) -> float:
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path],
            stderr=subprocess.STDOUT
        )
        meta = json.loads(out.decode("utf-8", "ignore"))
        dur = float(meta.get("format", {}).get("duration", "0"))
        return dur if dur >= 0 else -1.0
    except Exception:
        return -1.0
    
def extract_first_frame(video_path, out_jpeg, force_input_format):
    try:
        cmd = [FFMPEG, '-y']
        if force_input_format:
            cmd += ['-f', force_input_format]
        cmd += ['-i', video_path, '-frames:v', '1', out_jpeg]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(out_jpeg)
    except Exception:
        return False

def recover_avi_slack(input_avi, base_dir, target_format='mp4', use_gpu=False):
    os.makedirs(base_dir, exist_ok=True)
    with open(input_avi, "rb") as f:
        data = f.read()

    if len(data) == 0:
        logger.error(f"{input_avi} 파일 크기가 0입니다. 손상된 파일로 건너뜁니다.")
        shutil.rmtree(base_dir, ignore_errors=True)
        return None

    if not (data[:4] == b"RIFF" and b"AVI" in data[:12]):
        logger.error(f"{input_avi} AVI 헤더가 올바르지 않습니다. 건너뜁니다. 헤더: {data[:16]!r}")
        shutil.rmtree(base_dir, ignore_errors=True)
        return None

    origin_filename = os.path.basename(input_avi)
    basename = os.path.splitext(origin_filename)[0]
    origin_path = os.path.join(base_dir, origin_filename)
    if os.path.abspath(input_avi) != os.path.abspath(origin_path):
        shutil.copy2(input_avi, origin_path)

    results = {}

    common_args = [
        '-fflags', '+genpts',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '30'
    ]
    
    for label in("front", "rear", "side"):
        ch_dir = os.path.join(base_dir, label)
        os.makedirs(ch_dir, exist_ok=True)
        has_output = False
        
        channel_data, frame_count, codec = split_channel_bytes(data, label)

        if frame_count > 0:
            sps_pps = extract_sps_pps_from_raw(channel_data, codec, label)
            if sps_pps:
                slack_h264 = os.path.join(ch_dir, f"{basename}_{label}_slack.h264")
                slack_nal_count, recovered_bytes = extract_frames_from_raw(channel_data, sps_pps, slack_h264)

                if slack_nal_count > 0:
                    image_jpeg = os.path.join(ch_dir, f"{basename}_{label}_slack.jpg")

                    if frame_count <= 1:
                        ok = extract_first_frame(slack_h264, image_jpeg, force_input_format='h264')
                        try: 
                            os.remove(slack_h264)
                        except OSError: 
                            pass

                        if ok:
                            results[label] = {
                                'recovered': True,
                                'video_path': None,
                                'image_path': image_jpeg,
                                'is_image_fallback': True,
                                'slack_rate': round(recovered_bytes / len(data) * 100, 2),
                                'slack_size': bytes_to_unit(recovered_bytes)
                            }
                            has_output = True
                        else:
                            logger.warning(f"[{label}] 프레임 1장 케이스에서 이미지 추출 실패")
                    else:
                        slack_mp4 = os.path.join(ch_dir, f"{basename}_{label}_slack.{target_format}")
                        convert_video(slack_h264, slack_mp4, extra_args=common_args, use_gpu=use_gpu)

                        try:
                            os.remove(slack_h264)
                        finally:
                            try:
                                os.remove(slack_h264)
                            except OSError:
                                pass
                        
                        if os.path.exists(slack_mp4):
                            fcount = get_video_frame_count(slack_mp4)
                            duration = get_video_duration_sec(slack_mp4)
                            need_jpeg = (
                                (fcount is not None and fcount <= 1) or
                                (fcount is None and duration is not None and duration >= 0 and duration < SLACK_IMAGE_THRESHOLD_SEC)
                            )

                            if need_jpeg:
                                ok = extract_first_frame(slack_mp4, image_jpeg, force_input_format=None)
                                if ok:
                                    try:
                                        os.remove(slack_mp4)
                                    except OSError:
                                        pass
                                    results[label] = {
                                        'recovered': True,
                                        'video_path': None,
                                        'image_path': image_jpeg,
                                        'is_image_fallback': True,
                                        'slack_rate': round(recovered_bytes / len(data) * 100, 2),
                                        'slack_size': bytes_to_unit(recovered_bytes)
                                    }
                                else:
                                    results[label] = {
                                        'recovered': True,
                                        'video_path': slack_mp4,
                                        'image_path': None,
                                        'is_image_fallback': False,
                                        'slack_rate': round(recovered_bytes / len(data) * 100, 2),
                                        'slack_size': bytes_to_unit(recovered_bytes)
                                    }
                            else:
                                results[label] = {
                                    'recovered': True,
                                    'video_path': slack_mp4,
                                    'image_path': image_jpeg if os.path.exists(image_jpeg) else None,
                                    'is_image_fallback': False,
                                    'slack_rate': round(recovered_bytes / len(data) * 100, 2),
                                    'slack_size': bytes_to_unit(recovered_bytes)
                                }
                            has_output = True

        full_raw = extract_full_channel_bytes(data, label)
        if len(full_raw) > 0:
            raw_fn = os.path.join(ch_dir, f"{label}_full.raw")
            with open(raw_fn, 'wb') as rf:
                rf.write(full_raw)

            full_mp4 = os.path.join(ch_dir, f"{basename}_{label}.{target_format}")
            try:
                convert_video(raw_fn, full_mp4, extra_args=common_args, use_gpu=use_gpu)
            finally:
                try:
                    os.remove(raw_fn)
                except OSError:
                    pass

            if label not in results:
                results[label] = {
                    'recovered': False,
                    'video_path': None,
                    'image_path': None,
                    'is_image_fallback': False,
                    'slack_rate': 0.0,
                    'slack_size': "0 B"
                }

            if os.path.exists(full_mp4):
                results[label]['full_video_path'] = full_mp4
                has_output = True
            
        if not has_output:
            shutil.rmtree(ch_dir, ignore_errors=True)

    results['source_path'] = origin_path
    return results