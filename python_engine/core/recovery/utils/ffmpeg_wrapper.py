import subprocess
import os

# FFmpeg 실행 파일 경로 
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))

def convert_video(input_path, output_path, extra_args=None, use_gpu=True, wait=True):
    cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error']

    want_copy = (extra_args and any(a.lower() == 'copy' for a in extra_args[1::2])) if extra_args else False
    is_raw_h264 = input_path.lower().endswith('.h264')
    wrapping_mode = want_copy or is_raw_h264

    if wrapping_mode:
        cmd += ['-r', '30', '-f', 'h264', '-i', input_path, '-c:v', 'copy', '-movflags', '+faststart']
    else:
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
            cmd += list(extra_args)

    cmd += [output_path]

    if wait:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None
    else:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[INFO] ffmpeg (PID={p.pid}) | GPU={use_gpu} | wrapping_mode={wrapping_mode}")
        return p