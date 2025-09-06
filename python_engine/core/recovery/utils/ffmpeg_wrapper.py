import subprocess
import os

# FFmpeg 실행 파일 경로 (프로젝트 bin 폴더 기준)
FFMPEG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../../bin/ffmpeg.exe')
)

def convert_video(input_path, output_path, extra_args=None, use_gpu=True):
    cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error']

    # GPU 적용
    if use_gpu:
        cmd += [
            '-hwaccel', 'cuda',
            '-i', input_path,
            '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart'
        ]
    else:
        cmd += [
            '-i', input_path,
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart'
        ]


    if extra_args:
        if isinstance(extra_args, str):
            cmd += [extra_args]
        else:
            cmd += extra_args

    cmd += [output_path]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f"[INFO] ffmpeg (PID={process.pid}) | GPU={use_gpu}")
    return process
