import subprocess
import os

# FFmpeg 실행 파일 경로 
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))

def convert_video(input_path, output_path, fps=30, extra_args=None, use_gpu=True, wait=True):
    cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error']

    want_copy = (extra_args and any(a.lower() == 'copy' for a in extra_args[1::2])) if extra_args else False
    is_raw_h264 = input_path.lower().endswith(('.h264', '.vrx', '.tmp'))
    wrapping_mode = want_copy or is_raw_h264

    if wrapping_mode:
        # JDR 파일의 디코딩 에러 방지를 위해 재인코딩 모드로 변경
        # 손상된 프레임을 건너뛰고 안정적인 MP4 생성
        cmd += [
            '-r', str(fps), '-f', 'h264', '-i', input_path,
            '-err_detect', 'ignore_err',  # 에러 무시
            '-fflags', '+genpts',         # PTS 재생성
            '-avoid_negative_ts', 'make_zero',  # 음수 타임스탬프 방지
        ]
            
        cmd += ['-movflags', '+faststart']
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

def convert_audio(input_path, output_path, sample_rate=8000, extra_args=None, wait=True):
    """
    Converts a raw audio file to a standard format like WAV.
    """
    cmd = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error',
        '-f', 's16le',
        '-ar', str(sample_rate),
        '-ac', '1',
        '-i', input_path
    ]
    
    if extra_args:
        cmd += list(extra_args)

    cmd += [output_path]

    if wait:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None
    else:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[INFO] ffmpeg audio conversion (PID={p.pid})")
        return p

def merge_video_audio(video_path, audio_path, output_path, wait=True):
    cmd = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error',
        '-i', video_path,
        '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        output_path
    ]

    if wait:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None
    else:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[INFO] ffmpeg merge (PID={p.pid})")
        return p