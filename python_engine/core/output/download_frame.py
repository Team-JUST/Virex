import os
import zipfile
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

# ffmpeg 실행 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRAME_EXTRACTOR = os.path.join(BASE_DIR, "bin", "ffmpeg.exe")

# 프레임 추출 함수
def extract_frames_with_ffmpeg(video_path, output_dir):
    cmd = [
        FRAME_EXTRACTOR,
        "-i", video_path,
        "-q:v", "2",
        os.path.join(output_dir, "frame_%03d.jpg")
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

# 디렉토리 압축 함수
def zip_directory(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

# 프레임 다운로드 함수
def download_frames(video_info_list, download_dir):
    os.makedirs(download_dir, exist_ok=True)
    frame_zip_path = os.path.join(download_dir, "frames.zip")

    with zipfile.ZipFile(frame_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for info in video_info_list:
            video_path = info.get("output_path")
            filename = info.get("filename")

            if not video_path or not filename or not os.path.exists(video_path):
                logger.warning(f"유효하지 않은 영상: {video_path}")
                continue

            name, _ = os.path.splitext(filename)
            with tempfile.TemporaryDirectory() as temp_dir:
                frame_dir = os.path.join(temp_dir, name)
                os.makedirs(frame_dir, exist_ok=True)

                logger.info(f"프레임 추출 중: {filename}")
                success = extract_frames_with_ffmpeg(video_path, frame_dir)
                if not success:
                    logger.error(f"프레임 추출 실패: {filename}")
                    continue

                for root, _, files in os.walk(frame_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(name, file)
                        zipf.write(file_path, arcname)

                logger.info(f"{filename} 프레임 압축 완료")

    return [{"saved_path": frame_zip_path, "filename": "slack_frame.zip"}]