import os
import datetime
import subprocess
import json
from fractions import Fraction

# FFprobe 실행 파일 경로
FFPROBE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../../bin/ffprobe.exe')
)

# 영상 파일의 포맷 추출
def file_format(file_path):
    with open(file_path, 'rb') as f:
        header = f.read(12)

    is_avi = header[0:4] == b'RIFF' and header[8:12] == b'AVI '
    is_mp4 = header[4:8] == b'ftyp'

    if is_avi:
        return 'AVI'
    if is_mp4:
        return 'MP4'
    return 'Unknown'

# 파일 생성/수정/접근 시간 정보 반환
def file_timestamps(file_path):
    created = os.path.getctime(file_path)
    modified = os.path.getmtime(file_path)
    accessed = os.path.getatime(file_path)

    return {
        "created": datetime.datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S'),
        "modified": datetime.datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
        "accessed": datetime.datetime.fromtimestamp(accessed).strftime('%Y-%m-%d %H:%M:%S')
    }

def format_timestamp(ts):
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else None

# 비디오/오디오 메타데이터 추출
def video_metadata(file_path):
    cmd = [
        FFPROBE_PATH,
        '-v', 'error',
        '-show_entries', 'stream=index,codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate,duration',
        '-of', 'json',
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        info = json.loads(result.stdout)
        streams = info.get('streams', [])
        format_info = info.get('format', {})

        video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

        # duration robust: video stream > format > 0.0
        duration = 0.0
        if video_stream and video_stream.get('duration'):
            try:
                duration = float(video_stream.get('duration'))
            except Exception:
                duration = 0.0
        elif format_info.get('duration'):
            try:
                duration = float(format_info.get('duration'))
            except Exception:
                duration = 0.0

        # frame_rate robust 파싱
        frame_rate = 0.0
        if video_stream and video_stream.get('r_frame_rate'):
            try:
                fr_str = video_stream.get('r_frame_rate')
                if '/' in fr_str:
                    frame_rate = round(float(Fraction(fr_str)), 2)
                else:
                    frame_rate = round(float(fr_str), 2)
            except Exception:
                frame_rate = 0.0

        video_meta = {
            'duration': duration,
            'codec': video_stream.get('codec_name', 'unknown') if video_stream else 'unknown',
            'width': int(video_stream.get('width', 0)) if video_stream else 0,
            'height': int(video_stream.get('height', 0)) if video_stream else 0,
            'frame_rate': frame_rate
        }
        audio_meta = {
            'audio_codec': audio_stream.get('codec_name', 'unknown') if audio_stream else 'unknown',
            'audio_rate': int(audio_stream.get('sample_rate', 0)) if audio_stream else 0,
            'channels': int(audio_stream.get('channels', 0)) if audio_stream else 0
        }
        return {**video_meta, **audio_meta}

    except Exception:
        # ffprobe 실행 실패 시 기본값 반환
        return {
            'duration': 0.0,
            'codec': 'unknown',
            'width': 0,
            'height': 0,
            'frame_rate': 0.0,
            'audio_codec': 'unknown',
            'audio_rate': 0,
            'channels': 0
        }

# 종합 정보 반환
def get_basic_info(file_path):
    result = {
        "format": file_format(file_path),
        "timestamps": file_timestamps(file_path),
        "video_metadata": video_metadata(file_path)
    }
    return result

# E01 메타데이터 기반 버전
def get_basic_info_with_meta(file_path, meta):
    # meta가 None이거나 속성이 없을 때 안전하게 처리
    created = format_timestamp(getattr(meta, 'crtime', None)) if meta else None
    modified = format_timestamp(getattr(meta, 'mtime', None)) if meta else None
    accessed = format_timestamp(getattr(meta, 'atime', None)) if meta else None

    # meta가 없으면 파일 시스템의 타임스탬프 사용
    if not any([created, modified, accessed]):
        timestamps = file_timestamps(file_path)
    else:
        timestamps = {
            "created": created,
            "modified": modified,
            "accessed": accessed
        }

    result = {
        "format": file_format(file_path),
        "timestamps": timestamps,
        "video_metadata": video_metadata(file_path)
    }
    return result