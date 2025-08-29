import os
import datetime
import subprocess
import json
from fractions import Fraction

# FFprobe 실행 파일 경로 (프로젝트 bin 폴더 기준)
FFPROBE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../bin/ffprobe.exe'))

def file_format(file_path):
    with open(file_path, 'rb') as f:
        header = f.read(12)

    # AVI: RIFF 헤더
    if header[0:4] == b'RIFF' and header[8:12] == b'AVI ':
        return 'AVI'

    # MP4: ftyp 
    if header[4:8] == b'ftyp':
        return 'MP4'

    return 'Unknown'

def file_creation_time(file_path):
    created = os.path.getctime(file_path)
    modified = os.path.getmtime(file_path)
    accessed = os.path.getatime(file_path)

    return {
        "created": datetime.datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S'),
        "modified": datetime.datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
        "accessed": datetime.datetime.fromtimestamp(accessed).strftime('%Y-%m-%d %H:%M:%S')
    }

def video_metadata(file_path):
    cmd = [
        FFPROBE_PATH,
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height,r_frame_rate,duration',
        '-of', 'json',
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        info = json.loads(result.stdout)

        stream = info.get('streams', [{}])[0]
        codec    = stream.get('codec_name', 'unknown')
        width    = int(stream.get('width', 0))
        height   = int(stream.get('height', 0))
        duration = float(stream.get('duration', 0.0))

        fps_str    = stream.get('r_frame_rate', '0/1')
        frame_rate = float(Fraction(fps_str)) if fps_str != '0/0' else 0.0

        return {
            'duration': duration,
            'codec': codec,
            'width': width,
            'height': height,
            'frame_rate': frame_rate
        }

    except Exception:
        # ffprobe 실행 실패 시 기본값 반환
        return {
            'duration': 0.0,
            'codec': 'unknown',
            'width': 0,
            'height': 0,
            'frame_rate': 0.0
        }

def get_basic_info(file_path):
    return {
        "format": file_format(file_path),
        "timestamps": file_creation_time(file_path),
        "video_metadata": video_metadata(file_path)
    }