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
    frame_counts = []  # 각 구간별 프레임 수를 저장
    count = 0
    
    for i in range(len(chunks)):
        # 현재 청크가 I-frame인 경우
        if chunks[i].data.startswith(b'\x00\x00\x00\x01\x67'):
            if count > 0:  # 이전 구간의 프레임 수 저장
                frame_counts.append(count)
            count = 1  # 현재 I-frame부터 다시 카운트 시작
        else:
            count += 1
    
    # 마지막 구간의 프레임 수도 저장
    if count > 0:
        frame_counts.append(count)
    
    # 가장 많이 나온 프레임 수를 fps로 사용
    if frame_counts:
        return max(set(frame_counts), key=frame_counts.count)
    return 30  # 기본값

def _recover_channel_data(data, label, output_dir):
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

    def save_video_file(ts, data):
        if not data:
            return None
        video_filename = f"{channel_prefix}{format_datetime(ts)}.vrx" if ts else f"{channel_prefix}unknown_time_video.vrx"
        video_path = os.path.join(output_dir, video_filename)
        with open(video_path, "wb") as f:
            f.write(data)
        video_paths.append(video_path)
        return video_path

    def save_audio_file(ts, data):
        if not data:
            return None
        audio_filename = f"{channel_prefix}{format_datetime(ts)}.bin" if ts else f"{channel_prefix}unknown_time_audio.bin"
        audio_path = os.path.join(output_dir, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(data)
        audio_paths.append(audio_path)
        return audio_path

    # 모든 청크 찾기
    while True:
        sig, idx = find_next(data, offset, video_sigs + audio_sigs)
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
                    # 분리 조건: 이전 프레임과 1초 이상 차이
                    if prev_video_ts and timestamp and (timestamp - prev_video_ts).total_seconds() > 1:
                        # 현재까지 모은 비디오/오디오 저장
                        save_video_file(cur_video_first_ts, cur_video_data)
                        save_audio_file(cur_audio_first_ts, cur_audio_data)
                        cur_video_data = bytearray()
                        cur_audio_data = bytearray()
                        cur_video_first_ts = timestamp
                        cur_audio_first_ts = timestamp
                        found_start = False
                        # SPS로 시작하는지 다시 체크
                        if pats['start'].match(chunk):
                            found_start = True
                    if cur_video_first_ts is None:
                        cur_video_first_ts = timestamp
                    cur_video_data.extend(chunk)
                    video_chunks.append(VideoChunk(chunk, timestamp))
                    prev_video_ts = timestamp
        elif sig in audio_sigs:
            if found_start:
                # 오디오도 비디오 분리 기준에 맞춰 분리
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
    if cur_audio_data:
        save_audio_file(cur_audio_first_ts, cur_audio_data)

    # fps 계산
    fps = calculate_fps(video_chunks) if video_chunks else 30

    return {
        "recovered": len(video_chunks) > 0 or len(audio_chunks) > 0,
        "video_size": bytes_to_unit(sum(len(chunk.data) for chunk in video_chunks)),
        "video_paths": video_paths if output_dir else [],
        "audio_paths": audio_paths if output_dir else [],
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
    video_output_dir = os.path.join(output_root, 'video')
    audio_output_dir = os.path.join(output_root, 'audio')
    merge_output_dir = os.path.join(output_root, 'merge')
    
    os.makedirs(video_output_dir, exist_ok=True)
    os.makedirs(audio_output_dir, exist_ok=True)
    os.makedirs(merge_output_dir, exist_ok=True)

    # 원본 JDR 파일이 output_root 안에 없을 때만 복사
    dest_path = os.path.join(output_root, os.path.basename(input_jdr))
    if os.path.normpath(input_jdr) != os.path.normpath(dest_path):
        try:
            import shutil
            shutil.copy(input_jdr, dest_path)
        except Exception as e:
            logger.warning(f"Could not copy original JDR file: {e}")

    results = {}
    labels = ['front', 'rear', 'side']
    all_audio_files = []
    first_timestamp_str = None

    temp_base_dir = os.path.join(output_root, 'temp')

    for label in labels:
        logger.info(f"Recovering channel: {label}")
        
        temp_dir = os.path.join(temp_base_dir, label)
        os.makedirs(temp_dir, exist_ok=True)

        channel_result = _recover_channel_data(data, label, temp_dir)

        if not channel_result["recovered"]:
            logger.warning(f"No data recovered for channel: {label}")
            continue

        final_video_paths = []
        for i, video_path in enumerate(channel_result["video_paths"]):
            try:
                output_filename = os.path.basename(video_path).replace('.vrx', f'.{target_format}')
                output_path = os.path.join(video_output_dir, output_filename)
                
                ffmpeg_wrapper.convert_video(video_path, output_path, fps=channel_result["fps"])
                
                final_video_paths.append(output_path)
                logger.info(f"Successfully created {output_path}")

                if i == 0 and not first_timestamp_str:
                    # Extract timestamp from filename like 'F_2025_01_06_08_10_48_video.vrx'
                    match = re.search(r'\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}', os.path.basename(video_path))
                    if match:
                        first_timestamp_str = match.group(0)

            except Exception as e:
                logger.error(f"Failed to process video for {video_path}: {e}")
        
        all_audio_files.extend(channel_result.get("audio_paths", []))

        results[label] = {
            "recovered_files": final_video_paths,
            "video_size": channel_result["video_size"]
        }

    # Convert and save audio
    audio_file_path = None  # Initialize audio file path
    if all_audio_files:
        try:
            # Use the timestamp from the first video file for the audio filename
            if not first_timestamp_str:
                first_timestamp_str = "unknown_time"
            
            audio_output_filename = f"A_{first_timestamp_str}.mp3"
            final_audio_path = os.path.join(audio_output_dir, audio_output_filename)

            # 첫 번째 채널(00AD)의 오디오 파일만 사용
            front_channel_audio = next(
                (f for f in all_audio_files if "00AD" in f),
                all_audio_files[0]  # 없으면 첫 번째 파일 사용
            )
            
            logger.info("Converting audio file to MP3.")
            ffmpeg_wrapper.convert_audio(front_channel_audio, final_audio_path, extra_args=['-c:a', 'mp3', '-b:a', '128k'])
            logger.info(f"Successfully created audio file {final_audio_path}")
            
            # Audio file created but not stored in JSON - use direct file path for merging
            audio_file_path = final_audio_path

            # 각 채널의 비디오와 오디오를 병합
            for channel in ['front', 'rear', 'side']:
                if channel in results:
                    merged_files = []
                    for video_path in results[channel]['recovered_files']:
                        try:
                            # 비디오 파일명에서 날짜 추출
                            video_name = os.path.basename(video_path)
                            date_match = re.search(r'\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}', video_name)
                            if date_match:
                                date_str = date_match.group(0)
                                # 같은 날짜의 오디오 파일 찾기 (직접 파일 경로 사용)
                                if audio_file_path and os.path.exists(audio_file_path) and date_str in audio_file_path:
                                    matching_audio = audio_file_path
                                else:
                                    matching_audio = None
                                    
                                if matching_audio:
                                    channel_prefix = {'front': 'F', 'rear': 'R', 'side': 'S'}[channel]
                                    merged_filename = f"{channel_prefix}_{date_str}_merged.mp4"
                                    merged_path = os.path.join(merge_output_dir, merged_filename)
                                    
                                    ffmpeg_wrapper.merge_video_audio(
                                        video_path, matching_audio, merged_path
                                    )
                                    
                                    merged_files.append(merged_path)
                                    logger.info(f"Created merged file: {merged_path}")
                        except Exception as e:
                            logger.error(f"Failed to merge video and audio: {e}")
                    
                    if merged_files:
                        if 'merge' not in results:
                            results['merge'] = {'recovered_files': [], 'file_sizes': {}}
                        results['merge']['recovered_files'].extend(merged_files)
                        
                        # 각 merge 파일의 개별 크기 저장
                        for merged_file in merged_files:
                            try:
                                if os.path.exists(merged_file):
                                    file_size = os.path.getsize(merged_file)
                                    filename = os.path.basename(merged_file)
                                    results['merge']['file_sizes'][filename] = bytes_to_unit(file_size)
                            except Exception as e:
                                logger.warning(f"Could not get size of merged file {merged_file}: {e}")

        except Exception as e:
            logger.error(f"Failed to process combined audio: {e}")


    # Clean up temp directory
    try:
        import shutil
        if os.path.exists(temp_base_dir):
            shutil.rmtree(temp_base_dir)
            logger.info(f"Removed temporary directory: {temp_base_dir}")
    except Exception as e:
        logger.warning(f"Could not remove temp directory {temp_base_dir}: {e}")

    return results