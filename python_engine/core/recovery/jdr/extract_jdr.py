from encodings.cp932 import codec
import os
import re
import struct
import datetime
import json
import logging
from python_engine.core.recovery.utils.unit import bytes_to_unit
from python_engine.core.recovery.utils import ffmpeg_wrapper

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

def calculate_fps(chunks):
    """I-frame부터 다음 I-frame까지의 프레임 수를 세서 fps 계산"""
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
    offset = 0

    channel_prefix = {
        'front': 'F_',
        'rear': 'R_',
        'side': 'S_'
    }[label]

    def format_datetime(dt):
        return dt.strftime("%Y_%m_%d_%H_%M_%S") if dt else "unknown_time"

    video_paths = []
    audio_paths = []
    video_chunks = []
    audio_chunks = []
    found_start = False
    prev_video_ts = None
    prev_audio_ts = None
    cur_video_data = bytearray()
    cur_audio_data = bytearray()
    cur_video_first_ts = None
    cur_audio_first_ts = None

    def save_video_file(ts, data_bytes):
        if not data_bytes:
            return None
        video_filename = f"{channel_prefix}{format_datetime(ts)}.vrx" if ts else f"{channel_prefix}unknown_time_video.vrx"
        video_path = os.path.join(output_dir, video_filename)
        with open(video_path, "wb") as f:
            f.write(data_bytes)
        video_paths.append(video_path)
        return video_path

    def save_audio_file(ts, data_bytes):
        if not data_bytes:
            return None
        audio_filename = f"A_{format_datetime(ts)}.bin" if ts else f"{channel_prefix}unknown_time_audio.bin"
        audio_path = os.path.join(output_dir, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(data_bytes)
        audio_paths.append(audio_path)
        return audio_path

    # 모든 청크 찾기
    while True:
        sig, idx = find_next(data, offset, video_sigs + (audio_sigs if save_audio else []))
        if idx == -1 or idx + 8 > len(data):
            break

        size = struct.unpack('<I', data[idx + 4:idx + 8])[0]
        timestamp = parse_timestamp(data[idx + 8:idx + 8 + HEADER_SKIP])

        start = idx + 8 + HEADER_SKIP
        end = start + size

        if size > MAX_REASONABLE_CHUNK_SIZE or size <= MIN_REASONABLE_CHUNK_SIZE or end > len(data):
            offset = idx + 4
            continue

        chunk = data[start:end]
        offset = end

        if sig in video_sigs:
            # 비디오 청크 처리
            if (not found_start and pats['start'].match(chunk)) or found_start:
                if not found_start and pats['start'].match(chunk):
                    found_start = True
                if found_start:
                    # 비디오 분리 조건: 이전 프레임과 1초 이상 차이
                    if prev_video_ts and timestamp and (timestamp - prev_video_ts).total_seconds() > 1:
                        save_video_file(cur_video_first_ts, cur_video_data)
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
                    save_audio_file(cur_audio_first_ts, cur_audio_data)
                    cur_audio_data = bytearray()
                    cur_audio_first_ts = timestamp
                if cur_audio_first_ts is None:
                    cur_audio_first_ts = timestamp
                cur_audio_data.extend(chunk)
                audio_chunks.append(AudioChunk(chunk, timestamp, sig))
                prev_audio_ts = timestamp

    # 마지막 남은 데이터 저장
    if cur_video_data:
        save_video_file(cur_video_first_ts, cur_video_data)
    if save_audio and cur_audio_data:
        save_audio_file(cur_audio_first_ts, cur_audio_data)

    # fps 계산
    fps = calculate_fps(video_chunks) if video_chunks else 30

    return {
        "recovered": len(video_chunks) > 0 or (save_audio and len(audio_chunks) > 0),
        "video_size": bytes_to_unit(sum(len(chunk.data) for chunk in video_chunks)),
        "video_paths": video_paths if output_dir else [],
        "audio_paths": (audio_paths if (output_dir and save_audio) else []),
        "fps": fps
    }

def recover_jdr(input_jdr, base_dir, target_format='mp4'):
    try:
        with open(input_jdr, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_jdr}")
        return {}
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        return {}

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
                "video_size": "0 B"
            }
            continue

        final_video_paths = []
        for i, video_path in enumerate(channel_result.get("video_paths", [])):
            try:
                output_filename = os.path.basename(video_path).replace('.vrx', f'.{target_format}')
                output_path = os.path.join(output_root, output_filename)

                ffmpeg_wrapper.convert_video(video_path, output_path, fps=channel_result.get("fps", 30))
                final_video_paths.append(output_path)
                logger.info(f"Successfully created {output_path}")

                # 첫 비디오의 타임스탬프 문자열 확보
                if i == 0 and not first_timestamp_str:
                    match = re.search(r'\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}', os.path.basename(video_path))
                    if match:
                        first_timestamp_str = match.group(0)
            except Exception as e:
                logger.error(f"Failed to process video for {video_path}: {e}")

        results[label] = {
            "recovered": True,
            "video_path": final_video_paths,
            "video_size": channel_result.get("video_size", "0 B")
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
    for mp3_path in audio_mp3_paths:
        m = re.search(r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})', os.path.basename(mp3_path))
        if m:
            date_key = m.group(1)
            audio_by_date.setdefault(date_key, mp3_path)

    # 채널별 비디오에 대해 같은 날짜의 오디오가 있으면 머지
    merged_any = False
    for channel in ['front', 'rear', 'side']:
        if channel in results and results[channel].get('video_path'):
            merged_files = []
            for video_path in results[channel]['video_path']:
                try:
                    video_name = os.path.basename(video_path)
                    vdate = re.search(r'(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})', video_name)
                    if not vdate:
                        continue
                    date_str = vdate.group(1)
                    matching_audio = audio_by_date.get(date_str)
                    if not matching_audio:
                        # 동일 타임스탬프를 못 찾으면 머지 생략
                        continue

                    channel_prefix = {'front': 'F', 'rear': 'R', 'side': 'S'}[channel]
                    merged_filename = f"{channel_prefix}_{date_str}_merged.mp4"
                    merged_path = os.path.join(output_root, merged_filename)

                    ffmpeg_wrapper.merge_video_audio(video_path, matching_audio, merged_path)
                    merged_files.append(merged_path)
                    logger.info(f"Created merged file: {merged_path}")
                except Exception as e:
                    logger.error(f"Failed to merge video and audio: {e}")

            if merged_files:
                merged_any = True
                if 'merge' not in results:
                    results['merge'] = {'merged_files': [], 'file_sizes': {}}
                results['merge']['merged_files'].extend(merged_files)
                # 파일 크기 기록
                for merged_file in merged_files:
                    try:
                        if os.path.exists(merged_file):
                            file_size = os.path.getsize(merged_file)
                            filename = os.path.basename(merged_file)
                            results['merge']['file_sizes'][filename] = bytes_to_unit(file_size)
                    except Exception as e:
                        logger.warning(f"Could not get size of merged file {merged_file}: {e}")

    try:
        import shutil
        if os.path.exists(temp_base_dir):
            shutil.rmtree(temp_base_dir)
            logger.info(f"Removed temporary directory: {temp_base_dir}")
    except Exception as e:
        logger.warning(f"Could not remove temp directory {temp_base_dir}: {e}")

    return results