import subprocess

# FFmpeg 실행 파일 경로
FFMPEG_PATH = r"E:\Retato\bin\ffmpeg.exe"

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

    # stdout/stderr 모두 버리기
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )