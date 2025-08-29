import os
import logging
import shutil
from python_engine.core.recovery.avi.avi_split_channel import (
    split_channel_bytes,
    extract_full_channel_bytes,
    CHUNK_SIG)
from python_engine.core.recovery.utils.ffmpeg_wrapper import convert_video

logger = logging.getLogger(__name__)

def extract_sps_pps_from_raw(raw, codec, label):
    # HEVC 여부 확장 판별
    is_hevc = any(x in codec.lower() for x in ('265', 'hev1', 'hevc', 'hvc1'))
    vps = sps = pps = b''
    i = 0

    def find_start(buf, start):
        idx3 = buf.find(b'\x00\x00\x01', start)
        idx4 = buf.find(b'\x00\x00\x00\x01', start)
        candidates = [idx for idx in (idx3, idx4) if idx >= 0]
        if not candidates:
            return -1, 0
        idx = min(candidates)
        prefix = 4 if idx == idx4 else 3
        return idx, prefix

    while True:
        idx, prefix_len = find_start(raw, i)
        if idx < 0:
            break
        nal_start = idx + prefix_len
        next_idx, _ = find_start(raw, nal_start)
        nal = raw[nal_start : next_idx if next_idx > 0 else len(raw)]
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

def extract_frames_from_raw(raw, sps_pps, codec, out_fn):
    if not sps_pps:
        return 0, 0
    count = 0
    recovered_bytes = 0
    stream = sps_pps + raw

    def find_start(buf, pos):
        idx3 = buf.find(b'\x00\x00\x01', pos)
        idx4 = buf.find(b'\x00\x00\x00\x01', pos)
        candidates = [idx for idx in (idx3, idx4) if idx >= 0]
        if not candidates:
            return -1, 0
        idx = min(candidates)
        prefix = 4 if idx == idx4 else 3
        return idx, prefix

    with open(out_fn, 'wb') as wf:
        wf.write(sps_pps)
        recovered_bytes += len(sps_pps)
        pos = 0
        while True:
            idx, prefix = find_start(stream, pos)
            if idx < 0:
                break
            nal_start = idx + prefix
            next_idx, _ = find_start(stream, nal_start)
            nal = stream[nal_start : next_idx if next_idx > 0 else len(stream)]
            # 모든 NAL unit 저장
            wf.write((b'\x00\x00\x00\x01' if prefix == 4 else b'\x00\x00\x01') + nal)
            recovered_bytes += len(nal) + (4 if prefix == 4 else 3)
            count += 1
            pos = nal_start
    return count, recovered_bytes

def recover_avi_slack(input_avi, base_dir, target_format='mp4'):
    os.makedirs(base_dir, exist_ok=True)
    with open(input_avi, "rb") as f:
        data = f.read()

    # 0 bytes 파일 예외 처리
    if len(data) == 0:
        logger.error(f"{input_avi} 파일 크기가 0입니다. 손상된 파일로 건너뜁니다.")
        try:
            shutil.rmtree(base_dir)
        except Exception as e:
            logger.warning(f"{base_dir} 폴더 삭제 실패: {e}")
        return None

    # AVI 헤더 검사 (RIFF로 시작하고 AVI 포함)
    if not (data[:4] == b'RIFF' and b'AVI' in data[:12]):
        logger.error(f"{input_avi} AVI 헤더가 올바르지 않습니다. 건너뜁니다. 헤더: {data[:16]!r}")
        try:
            shutil.rmtree(base_dir)
        except Exception as e:
            logger.warning(f"{base_dir} 폴더 삭제 실패: {e}")
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
    
    # 1) 슬랙 채널 분리 및 슬랙 영상 생성
    for label in("front", "rear", "side"):
        ch_dir = os.path.join(base_dir, label)
        os.makedirs(ch_dir, exist_ok=True)
        has_output = False
        
        channel_data, frame_count, codec = split_channel_bytes(data, label)
        if frame_count > 0:
            sps_pps = extract_sps_pps_from_raw(channel_data, codec, label)
            if sps_pps:
                slack_h264 = os.path.join(ch_dir, f"{basename}_{label}_slack.h264")
                slack_count, recovered_bytes = extract_frames_from_raw(channel_data, sps_pps, codec, slack_h264)
                if slack_count > 0:
                    slack_mp4 = os.path.join(ch_dir, f"{basename}_{label}_slack.{target_format}")
                    convert_video(slack_h264, slack_mp4, extra_args=common_args)
                    results[label] = {
                        'recovered': True,
                        'video_path': slack_mp4,
                        'frame_count': slack_count,
                        'slack_rate': float(recovered_bytes / len(data) * 100)
                    }

        # 2) 원본 채널 분리
        full_raw = extract_full_channel_bytes(data, label)
        full_count = full_raw.count(CHUNK_SIG[label])
        if full_count > 0:
            raw_fn = os.path.join(ch_dir, f"{label}_full.raw")
            with open(raw_fn, 'wb') as rf:
                rf.write(full_raw)

            full_mp4 = os.path.join(ch_dir, f"{basename}_{label}.{target_format}")
            convert_video(raw_fn, full_mp4, extra_args=common_args)

            if label not in results:
                results[label] = {
                    'recovered': False,
                    'video_path': None,
                    'frame_count': 0,
                    'slack_rate': 0.0
                }
            results[label]['full_video_path'] = full_mp4
            has_output = True
        
        if not has_output:
            try:
                shutil.rmtree(ch_dir)
            except Exception as e:
                logger.warning(f"[{label}] 폴더 삭제 실패: {e}")

    results['source_path'] = origin_path
    results['file_size_bytes'] = len(data)
    return results