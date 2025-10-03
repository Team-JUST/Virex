from encodings.cp932 import codec
import os
import re
import struct
import datetime
import json
import logging
from python_engine.core.recovery.utils.unit import bytes_to_unit
from python_engine.core.recovery.utils import ffmpeg_wrapper
from python_engine.core.analyzer.integrity import get_integrity_info

logger = logging.getLogger(__name__)

MAX_REASONABLE_CHUNK_SIZE = 10 * 1024 * 1024
MIN_REASONABLE_CHUNK_SIZE = 16
HEADER_SKIP = 20
CHUNK_SIG = {
    'front': [b'00VI', b'00VP'],
    'rear':  [b'01VI', b'01VP'],
    'side':  [b'02VI', b'02VP'],
    'audio': [b'00AD', b'01AD', b'02AD'],  # 전체 오디오 시그니처
}

PATTERNS = {
    'H264': {
        'start': re.compile(b'\x00{2,3}\x01\x67'),  # SPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x67'),
            re.compile(b'\x00{2,3}\x01\x68'),
            re.compile(b'\x00{2,3}\x01[\x25\x45\x65]'),
            re.compile(b'\x00{2,3}\x01[\x21\x41\x61]'),
        ]
    },
    'HEVC': {
        'start': re.compile(b'\x00{2,3}\x01\x40'),  # VPS
        'types': [
            re.compile(b'\x00{2,3}\x01\x40'),
            re.compile(b'\x00{2,3}\x01\x42'),
            re.compile(b'\x00{2,3}\x01\x44'),
            re.compile(b'\x00{2,3}\x01\x26'),
            re.compile(b'\x00{2,3}\x01\x02'),
        ]
    }
}

def detect_codec(data):
    h264_count = data.count(b'\x00{2,3}x01\x67') # SPS 개수 세기
    h265_count = data.count(b'\x00{2,3}x01\x40') # VPS 개수 세기

    if h264_count >= h265_count:
        return 'H264'
    else:
        return 'HEVC'

def find_next(data, start, sigs):
    sig, idx = None, -1
    for s in sigs:
        i = data.find(s, start)
        if i != -1 and (idx == -1 or i < idx):
            sig, idx = s, i
    return sig, idx

def parse_timestamp(data):
    if len(data) < 20:
        return None
    YYYY = struct.unpack('<H', data[4:6])[0]
    MM = struct.unpack('<H', data[6:8])[0]
    DD = struct.unpack('<H', data[10:12])[0]
    hh = struct.unpack('<H', data[12:14])[0]
    mm = struct.unpack('<H', data[14:16])[0]
    ss = struct.unpack('<H', data[16:18])[0]
    msec = struct.unpack('<H', data[18:20])[0]
    try:
        return datetime.datetime(YYYY, MM, DD, hh, mm, ss, msec*1000)
    except Exception:
        return None

def _fail_result():
    return {
        "recovered": False,
        "video_size": "0 B",
        "video_path": None
    }

class VideoChunk:
    def __init__(self, data, timestamp):
        self.data = data
        self.timestamp = timestamp

class AudioChunk:
    def __init__(self, data, timestamp, signature):
        self.data = data
        self.timestamp = timestamp
        self.signature = signature  # 00AD, 01AD, 02AD

def classify_normal_slack_regions(data):
    # total block count 계산
    signature = b'1VEJ'
    offset = data.find(signature)
    if offset == -1:
        return data, b''
    count_offset = offset + len(signature)
    if count_offset + 4 > len(data):
        print("[슬랙 offset] 블록 개수 위치가 데이터 범위를 벗어납니다.")
        return data, b''
    total_blocks = struct.unpack('<I', data[count_offset:count_offset + 4])[0]

    # 블록 count 정보 이후로부터 0x14 * (n-1)만큼 이동    
    block_table_offset = count_offset + 4 + 0x14 * (total_blocks - 1)
    if block_table_offset + 4 > len(data):
        print("[슬랙 offset] 마지막 블록 오프셋 위치가 데이터 범위를 벗어납니다.")
        return data, b''
    
    # block_table_offset에서 4바이트 리틀엔디안으로 읽고, 4비트 시프트하여 실제 오프셋 계산
    last_block_offset_raw = struct.unpack('<I', data[block_table_offset:block_table_offset+4])[0]
    last_block_offset = last_block_offset_raw >> 4

    # 마지막 블록 오프셋에서 0xC8만큼 이동
    slack_offset_ptr = last_block_offset + 0xC8
    if slack_offset_ptr + 4 > len(data):
        print("[슬랙 offset] 슬랙 offset 위치가 데이터 범위를 벗어납니다.")
        return data, b''
    
    # 슬랙 offset
    slack_offset = struct.unpack('<I', data[slack_offset_ptr:slack_offset_ptr+4])[0]
    if slack_offset > len(data):
        print("[슬랙 offset] 슬랙 시작 offset이 데이터 범위를 벗어납니다.")
        return data, b''
    normal_data = data[:slack_offset]
    slack_data = data[slack_offset:]
    return normal_data, slack_data

def calculate_fps(chunks):
    frame_counts = []
    count = 0

    for i in range(len(chunks)):
        if chunks[i].data.startswith(b'\x00\x00\x00\x01\x67'):
            if count > 0:
                frame_counts.append(count)
            count = 1
        else:
            count += 1

    if count > 0:
        frame_counts.append(count)

    if frame_counts:
        return max(set(frame_counts), key=frame_counts.count)
    return 30  # 기본값

def _recover_channel_data(data, label, output_dir, save_audio=True):
    video_sigs = CHUNK_SIG[label]
    audio_sigs = CHUNK_SIG['audio']
    codec = detect_codec(data)
    pats = PATTERNS[codec]

    channel_prefix = {
        'front': 'F_',
        'rear': 'R_',
        'side': 'S_'
    }[label]

    def format_datetime(dt):
        return dt.strftime("%Y_%m_%d_%H_%M_%S") if dt else "unknown_time"

    # 정상/슬랙 영역 구분
    normal_data, slack_data = classify_normal_slack_regions(data)
    
    results = {
        'normal': {'video_paths': [], 'audio_paths': [], 'video_chunks': [], 'audio_chunks': []},
        'slack': {'video_paths': [], 'audio_paths': [], 'video_chunks': [], 'audio_chunks': []}
    }

    def process_region_data(region_data, region_type):
        if not region_data:
            return
            
        offset = 0
        video_chunks = []
        audio_chunks = []
        found_start = False
        prev_video_ts = None
        prev_audio_ts = None
        cur_video_data = bytearray()
        cur_audio_data = bytearray()
        cur_video_first_ts = None
        cur_audio_first_ts = None

        def save_video_file(ts, data_bytes, region_suffix):
            if not data_bytes:
                return None
            base_name = f"{channel_prefix}{format_datetime(ts)}" if ts else f"{channel_prefix}unknown_time_video"
            video_filename = f"{base_name}_{region_suffix}.vrx"
            video_path = os.path.join(output_dir, video_filename)
            with open(video_path, "wb") as f:
                f.write(data_bytes)
            results[region_type]['video_paths'].append(video_path)
            return video_path

        def save_audio_file(ts, data_bytes, region_suffix):
            if not data_bytes:
                return None
            base_name = f"A_{format_datetime(ts)}" if ts else f"{channel_prefix}unknown_time_audio"
            audio_filename = f"{base_name}_{region_suffix}.bin"
            audio_path = os.path.join(output_dir, audio_filename)
            with open(audio_path, "wb") as f:
                f.write(data_bytes)
            results[region_type]['audio_paths'].append(audio_path)
            return audio_path

        # 모든 청크 찾기
        while True:
            sig, idx = find_next(region_data, offset, video_sigs + (audio_sigs if save_audio else []))
            if idx == -1 or idx + 8 > len(region_data):
                break

            size = struct.unpack('<I', region_data[idx + 4:idx + 8])[0]
            timestamp = parse_timestamp(region_data[idx + 8:idx + 8 + HEADER_SKIP])

            start = idx + 8 + HEADER_SKIP
            end = start + size

            if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE or end > len(region_data):
                offset = idx + 4
                continue

            chunk = region_data[start:end]
            offset = end

            if sig in video_sigs:
                # 비디오 청크 처리
                if (not found_start and pats['start'].match(chunk)) or found_start:
                    if not found_start and pats['start'].match(chunk):
                        found_start = True
                    if found_start:
                        # 비디오 분리 조건: 이전 프레임과 1초 이상 차이
                        if prev_video_ts and timestamp and (timestamp - prev_video_ts).total_seconds() > 1:
                            save_video_file(cur_video_first_ts, cur_video_data, region_type)
                            cur_video_data = bytearray()
                            cur_video_first_ts = None
                            found_start = False
                            if pats['start'].match(chunk):
                                found_start = True
                                cur_video_first_ts = timestamp
                        if cur_video_first_ts is None and timestamp:
                            cur_video_first_ts = timestamp
                        if found_start:
                            cur_video_data.extend(chunk)
                            video_chunks.append(VideoChunk(chunk, timestamp))
                        if timestamp:
                            prev_video_ts = timestamp

            elif save_audio and sig in audio_sigs:
                # 오디오는 save_audio=True일 때만 처리/저장
                if found_start:
                    if prev_audio_ts and timestamp and (timestamp - prev_audio_ts).total_seconds() > 1:
                        save_audio_file(cur_audio_first_ts, cur_audio_data, region_type)
                        cur_audio_data = bytearray()
                        cur_audio_first_ts = timestamp
                    if cur_audio_first_ts is None:
                        cur_audio_first_ts = timestamp
                    cur_audio_data.extend(chunk)
                    audio_chunks.append(AudioChunk(chunk, timestamp, sig))
                    prev_audio_ts = timestamp

        # 마지막 남은 데이터 저장
        if cur_video_data:
            save_video_file(cur_video_first_ts, cur_video_data, region_type)
        if save_audio and cur_audio_data:
            save_audio_file(cur_audio_first_ts, cur_audio_data, region_type)

        results[region_type]['video_chunks'] = video_chunks
        results[region_type]['audio_chunks'] = audio_chunks

    # 정상 영역과 슬랙 영역 각각 처리
    process_region_data(normal_data, 'normal')
    process_region_data(slack_data, 'slack')

    # 전체 결과 취합
    all_video_chunks = results['normal']['video_chunks'] + results['slack']['video_chunks']
    all_audio_chunks = results['normal']['audio_chunks'] + results['slack']['audio_chunks']
    all_video_paths = results['normal']['video_paths'] + results['slack']['video_paths']
    all_audio_paths = results['normal']['audio_paths'] + results['slack']['audio_paths']

    # fps 계산
    fps = calculate_fps(all_video_chunks) if all_video_chunks else 30

    return {
        "recovered": len(all_video_chunks) > 0 or (save_audio and len(all_audio_chunks) > 0),
        "video_size": bytes_to_unit(sum(len(chunk.data) for chunk in all_video_chunks)),
        "video_paths": all_video_paths if output_dir else [],
        "audio_paths": (all_audio_paths if (output_dir and save_audio) else []),
        "fps": fps,
        "regions": results  # 영역별 상세 정보
    }

def recover_jdr(input_jdr, base_dir, target_format='mp4'):
    integrity = get_integrity_info(input_jdr)
    try:
        with open(input_jdr, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        return {"integrity": integrity}
    except Exception as e:
        return {"integrity": integrity}

    output_root = base_dir

    results = {}
    labels = ['front', 'rear', 'side']
    all_audio_bin_files = []
    audio_saved = False
    first_timestamp_str = None

    temp_base_dir = os.path.join(output_root, 'temp')
    os.makedirs(temp_base_dir, exist_ok=True)

    for label in labels:
        logger.info(f"Recovering channel: {label}")

        channel_result = _recover_channel_data(
            data=data,
            label=label,
            output_dir=temp_base_dir,
            save_audio=(not audio_saved)
        )

        if not audio_saved and channel_result.get("audio_paths"):
            all_audio_bin_files.extend(channel_result["audio_paths"])
            audio_saved = True

        if not channel_result["recovered"]:
            logger.warning(f"No data recovered for channel: {label}")
            results[label] = {
                "recovered": False,
                "video_path": None,
                "slack_rate": 0,
                "slack_size": "0 B",
                "full_video_path": None,
                "merged_video_path": None,
                "merged_video_size": "0 B"
            }
            continue

        # normal/slack별로 비디오 파일 변환 처리
        normal_video_paths = []
        slack_video_paths = []
        normal_video_size = 0
        slack_video_size = 0
        merged_video_path = None
        merged_video_size = "0 B"
        full_video_path = None
        slack_rate = 0
        slack_size = "0 B"

        regions = channel_result.get("regions", {})

        # Normal 영역 처리
        for i, video_path in enumerate(regions.get('normal', {}).get('video_paths', [])):
            try:
                output_filename = os.path.basename(video_path).replace('.vrx', f'.{target_format}')
                output_path = os.path.join(output_root, output_filename)

                ffmpeg_wrapper.convert_video(video_path, output_path, fps=channel_result.get("fps", 30))
                normal_video_paths.append(output_path)
                normal_video_size += os.path.getsize(output_path) if os.path.exists(output_path) else 0
                logger.info(f"Successfully created normal video {output_path}")

                # 첫 비디오의 타임스탬프 문자열 확보
                if i == 0 and not first_timestamp_str:
                    match = re.search(r'\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}', os.path.basename(video_path))
                    if match:
                        first_timestamp_str = match.group(0)
                if i == 0:
                    full_video_path = output_path
            except Exception as e:
                logger.error(f"Failed to process normal video for {video_path}: {e}")

        # Slack 영역 처리
        for video_path in regions.get('slack', {}).get('video_paths', []):
            try:
                output_filename = os.path.basename(video_path).replace('.vrx', f'.{target_format}')
                output_path = os.path.join(output_root, output_filename)

                ffmpeg_wrapper.convert_video(video_path, output_path, fps=channel_result.get("fps", 30))
                slack_video_paths.append(output_path)
                slack_video_size += os.path.getsize(output_path) if os.path.exists(output_path) else 0
                logger.info(f"Successfully created slack video {output_path}")
            except Exception as e:
                logger.error(f"Failed to process slack video for {video_path}: {e}")

        # slack_rate/slack_size 계산
        if slack_video_paths:
            # 슬랙 비디오 용량 및 비율 계산
            slack_size = bytes_to_unit(slack_video_size)
            total_size = normal_video_size + slack_video_size
            slack_rate = round((slack_video_size / total_size) * 100, 2) if total_size > 0 else 0

        if normal_video_paths:
            video_name = os.path.basename(normal_video_paths[0])
            vdate = re.search(r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})', video_name)
            if vdate:
                date_str = vdate.group(1)
                # 오디오 mp3는 아래에서 생성됨, audio_by_date에서 찾음
                # merged_video_path는 아래에서 실제로 생성됨
                pass

        # 결과 구조체에 AVI와 동일한 필드로 저장
        results[label] = {
            "recovered": True,
            "video_path": slack_video_paths[0] if slack_video_paths else None,
            "slack_rate": slack_rate,
            "slack_size": slack_size,
            "full_video_path": full_video_path,
            "merged_video_path": None,  # 아래에서 실제 경로 할당
            "merged_video_size": "0 B"
        }

    audio_mp3_paths = []
    if all_audio_bin_files:
        try:
            for bin_file in all_audio_bin_files:
                base_name = os.path.basename(bin_file).replace(".bin", "")
                audio_output_filename = f"{base_name}.mp3"
                final_audio_path = os.path.join(output_root, audio_output_filename)

                logger.info(f"Converting {bin_file} to {final_audio_path}")
                ffmpeg_wrapper.convert_audio(
                    bin_file,
                    final_audio_path,
                    extra_args=['-c:a', 'mp3', '-b:a', '128k']
                )
                logger.info(f"Successfully created audio file {final_audio_path}")
                audio_mp3_paths.append(final_audio_path)
        except Exception as e:
            logger.error(f"Failed to process audio files: {e}")

    audio_by_date = {}
    slack_audio_by_date = {}
    for mp3_path in audio_mp3_paths:
        m = re.search(r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})', os.path.basename(mp3_path))
        if m:
            date_key = m.group(1)
            if 'slack' in os.path.basename(mp3_path):
                slack_audio_by_date[date_key] = mp3_path
            else:
                audio_by_date[date_key] = mp3_path

    # 채널별 비디오에 대해 같은 날짜의 오디오가 있으면 머지
    for channel in ['front', 'rear', 'side']:
        if channel in results and results[channel].get('recovered'):
            normal_video_path = results[channel]['full_video_path']
            merged_path = None
            merged_size = "0 B"
            if normal_video_path:
                video_name = os.path.basename(normal_video_path)
                vdate = re.search(r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})', video_name)
                if vdate:
                    date_str = vdate.group(1)
                    matching_audio = audio_by_date.get(date_str)
                    if matching_audio:
                        channel_prefix = {'front': 'F', 'rear': 'R', 'side': 'S'}[channel]
                        merged_filename = f"{channel_prefix}_{date_str}_with_audio.mp4"
                        merged_path = os.path.join(output_root, merged_filename)
                        try:
                            ffmpeg_wrapper.merge_video_audio(normal_video_path, matching_audio, merged_path)
                            merged_size = bytes_to_unit(os.path.getsize(merged_path)) if os.path.exists(merged_path) else "0 B"
                            logger.info(f"Created merged file: {merged_path}")
                        except Exception as e:
                            logger.error(f"Failed to merge video and audio: {e}")
            results[channel]["merged_video_path"] = merged_path
            results[channel]["merged_video_size"] = merged_size

    audio_result = {
        "slack": {
            "path": None,
            "size": "0 B"
        }
    }
    # original/slack 오디오 파일 경로 및 크기 할당
    for date_key, path in audio_by_date.items():
        if os.path.exists(path):
            audio_result["original"] = {
                "path": path,
                "size": bytes_to_unit(os.path.getsize(path))
            }
            break
    for date_key, path in slack_audio_by_date.items():
        if os.path.exists(path):
            audio_result["slack"] = {
                "path": path,
                "size": bytes_to_unit(os.path.getsize(path))
            }
            break

    results["audio"] = audio_result

    try:
        import shutil
        if os.path.exists(temp_base_dir):
            shutil.rmtree(temp_base_dir)
            logger.info(f"Removed temporary directory: {temp_base_dir}")
    except Exception as e:
        logger.warning(f"Could not remove temp directory {temp_base_dir}: {e}")

    results["integrity"] = integrity

    return results