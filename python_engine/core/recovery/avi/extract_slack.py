import os
import logging
from io import BytesIO
from python_engine.core.recovery.avi.avi_split_channel import (
    split_channel_bytes,
    extract_full_channel_bytes,
    CHUNK_SIG,
    detect_codec)
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
        return 0
    count = 0
    # raw 앞에 SPS/PPS 헤더 붙이기
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
            count += 1
            pos = nal_start
    return count

def recover_avi_slack(input_avi, raw_out_dir, slack_out_dir, channels_out_dir, target_format='mp4'):
    with open(input_avi, "rb") as f:
        data = f.read()
    
    orig_codec = detect_codec(data)
    
    # 1) pre-check: front/rear/side 중 하나라도 프레임 있나?
    counts = [ split_channel_bytes(data, lbl)[1] for lbl in ("front","rear","side") ]
    if max(counts) == 0:
        logger.info(f"{os.path.basename(input_avi)} → 실제 슬랙 프레임 없음, 복원 스킵")
        return {}

    os.makedirs(raw_out_dir, exist_ok=True)         # h264 슬랙 원본
    os.makedirs(slack_out_dir, exist_ok=True)       # 슬랙만 MP4
    os.makedirs(channels_out_dir, exist_ok=True)    # 전체 채널 MP4

    basename = os.path.splitext(os.path.basename(input_avi))[0]
    results = {}

    # 2) 슬랙 hidden MP4 생성
    for label in ("front","rear","side"):
        logger.info(f"[SLP][{label}] 채널 분리 시작: {basename}")
        channel_data, frame_count, codec = split_channel_bytes(data, label)
        logger.info(f"[BACKEND] AVI 슬랙 정보: {basename}_{label}, frame_count={frame_count}, codec={codec}")
        logger.info(f"[BACKEND] AVI 슬랙 데이터 크기: channel_data_size={len(channel_data)}, total_file_size={len(data)}")
        
        if frame_count == 0:
            logger.info(f"[SLP][{label}] 프레임 없음 → 건너뜀")
            continue

        # SPS/PPS 추출
        sps_pps = extract_sps_pps_from_raw(channel_data, codec, label)
        if not sps_pps:
            logger.warning(f"[{label}] SPS/PPS 실패 → 건너뜀")
            continue

        slack_h264 = os.path.join(raw_out_dir, f"{basename}_{label}_slack.h264")
        slack_count = extract_frames_from_raw(channel_data, sps_pps, codec, slack_h264)
        logger.info(f"[BACKEND] AVI 슬랙 프레임 추출 결과: {basename}_{label}, slack_count={slack_count}")
        if slack_count == 0:
            logger.info(f"[SLP][{label}] 슬랙 프레임 없음 → 삭제 및 건너뜀")
            os.remove(slack_h264)
            continue
        logger.info(f"[SLP][{label}] 슬랙 프레임 추출 완료: {slack_count}개")

        # hidden(slack) MP4 생성
        hidden_mp4 = os.path.join(slack_out_dir, f"{basename}_{label}_hidden.mp4")
        fmt = 'hevc' if any(x in orig_codec.lower() for x in ('265','hev1','hevc','hvc1')) else 'h264'
        convert_video(
            slack_h264, hidden_mp4,
            extra_args=[
                '-f', fmt,
                '-c:v', 'copy',
                '-movflags', 'faststart'
            ]
        )
        logger.info(f"[RST][{label}] hidden MP4 생성: {hidden_mp4}")

        results[label] = {
            'recovered': True,
            'hidden_path': hidden_mp4,
            'frame_count': slack_count,
            'slack_rate': float(len(channel_data) / len(data) * 100)  # 채널 데이터 크기 / 전체 파일 크기
        }
        logger.info(f"[BACKEND] AVI 슬랙 비율 계산: {basename}_{label}, channel_size={len(channel_data)}, total_size={len(data)}, slack_rate={results[label]['slack_rate']:.2f}%")

    # 3) 원본 채널 MP4 생성
    for label in ("front","rear","side"):
        # 전체 채널 raw 데이터 획득
        full_raw = extract_full_channel_bytes(data, label)
        full_count = full_raw.count(CHUNK_SIG[label])
        if full_count == 0:
            logger.info(f"[FULL][{label}] 채널 없음 → 건너뜀")
            continue

        # raw 저장
        raw_fn = os.path.join(raw_out_dir, f"{basename}_{label}.raw")
        with open(raw_fn, 'wb') as rf:
            rf.write(channel_data)
        logger.info(f"[FULL][{label}] raw 저장: {raw_fn}")

        # 포맷 결정
        fmt = 'hevc' if any(x in codec.lower() for x in ('265','hev1','hevc','hvc1')) else 'h264'

        full_mp4 = os.path.join(channels_out_dir, f"{basename}_{label}.{target_format}")
        convert_video(
            raw_fn, full_mp4,
            extra_args=[
                '-f', fmt,
                '-c:v', 'copy',
                '-movflags', 'faststart'
            ]
        )
        logger.info(f"[FULL][{label}] 변환 완료: {full_mp4}")

        # 결과에도 기록
        results[label].update(full_path=full_mp4)

    return results