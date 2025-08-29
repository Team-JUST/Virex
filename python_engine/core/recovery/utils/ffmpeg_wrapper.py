import subprocess
import os

# FFmpeg 실행 파일 경로
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))

def convert_video(input_path, output_path, extra_args=None):
    cmd = [
        FFMPEG_PATH,
        '-hide_banner',
        '-loglevel', 'error',
        '-framerate', '30',
        '-i', input_path
    ]
    if extra_args:
        if isinstance(extra_args, str):
            cmd += ['-f', extra_args]
        else:
            cmd += extra_args
    cmd += [output_path]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )