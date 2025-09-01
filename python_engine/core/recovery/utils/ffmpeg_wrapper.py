import subprocess
import os

# FFmpeg 실행 파일 경로 (프로젝트 bin 폴더 기준)
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ffmpeg/ffmpeg.exe'))

def convert_video(input_path, output_path, extra_args=None):
    cmd = [
        FFMPEG_PATH,
        '-hide_banner',
        '-loglevel', 'error',
        '-i', input_path
    ]
    if extra_args:
        if isinstance(extra_args, str):
            cmd += ['-f', extra_args]
        else:
            cmd += extra_args
    cmd += [output_path]

    # subprocess.run → subprocess.Popen 으로 교체
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    # 작업관리자에서 확인하려고 Popen 사용

    print(f"[INFO] ffmpeg 실행됨 (PID={process.pid})")
    return process  # 실행 중인 프로세스 객체 반환
