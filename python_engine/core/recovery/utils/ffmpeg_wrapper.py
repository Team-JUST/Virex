import subprocess
import os
from python_engine.core.analyzer.basic_info_parser import video_metadata

# FFmpeg 실행 파일 경로 
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../bin/ffmpeg.exe'))

def convert_video(input_path, output_path, fps=None, extra_args=None, use_gpu=True, wait=True):
    cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'info']

    try:
        meta = video_metadata(input_path)
        fps = meta.get('frame_rate', 0.0)
        fps = round(fps, 2) if fps else None
        if not (fps and 10 <= fps <= 120):
            fps = 30
        codec = meta.get('codec', 'unknown')
        if codec == 'h264':
            vcodec = 'libx264'
        elif codec in ('hevc', 'h265'):
            vcodec = 'libx265'
        else:
            vcodec = 'libx264'
    except Exception:
        fps = 30
        vcodec = 'libx264'

    want_copy = (extra_args and any(a.lower() == 'copy' for a in extra_args[1::2])) if extra_args else False
    is_raw_h264 = input_path.lower().endswith(('.h264', '.vrx', '.tmp'))
    wrapping_mode = want_copy or is_raw_h264

    # fps가 있으면 -r 옵션에 적용
    if wrapping_mode:
        if fps:
            cmd += ['-r', str(fps)]
        else:
            cmd += ['-r', '30']
        
        # want_copy가 True이면 copy 옵션 사용, 아니면 인코딩
        if want_copy:
            cmd += ['-i', input_path, '-c:v', 'copy', '-movflags', '+faststart']
        else:
            cmd += ['-i', input_path, '-c:v', vcodec, '-preset', 'medium', '-crf', '23', '-movflags', '+faststart']
        cmd += [output_path]
    else:
        if use_gpu:
            if fps:
                cmd += ['-r', str(fps)]
            # h264: h264_nvenc, hevc/h265: hevc_nvenc
            if vcodec == 'libx265':
                gpu_codec = 'hevc_nvenc'
            else:
                gpu_codec = 'h264_nvenc'
            cmd += [
                '-hwaccel', 'cuda',
                '-i', input_path,
                '-c:v', gpu_codec, '-preset', 'p3', '-cq', '23',
                '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart'
            ]
        else:
            if fps:
                cmd += ['-r', str(fps)]
            cmd += [
                '-i', input_path,
                '-c:v', vcodec, '-preset', 'medium', '-crf', '23',
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