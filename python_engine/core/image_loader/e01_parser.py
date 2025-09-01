import os
import struct
import pyewf
import pytsk3
import tkinter as tk
from tkinter import filedialog
from io import BytesIO
import time
import logging
import tempfile
import shutil
import json, sys
from python_engine.core.recovery.mp4.extract_slack import recover_mp4_slack
from python_engine.core.recovery.avi.extract_slack import recover_avi_slack
from python_engine.core.analyzer.basic_info_parser import get_basic_info
from python_engine.core.analyzer.integrity import get_integrity_info
from python_engine.core.analyzer.struc import get_structure_info

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = ('.mp4', '.avi')

class EWFImgInfo(pytsk3.Img_Info):
    def __init__(self, ewf_handle):
        self._ewf_handle = ewf_handle
        super().__init__("", pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def read(self, offset, size):
        self._ewf_handle.seek(offset)
        return self._ewf_handle.read(size)

    def get_size(self):
        return self._ewf_handle.get_media_size()
    
def select_image_file():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title="이미지 파일 선택 (.E01 또는 .001)",
        filetypes=[
            ("이미지(.E01, .001)", "*.E01;*.001")]
    )

# 이미지 파일(.E01 or .001) 열기
def open_image_file(img_path):
    img_path = os.path.abspath(img_path)
    ext = os.path.splitext(img_path)[1].lower()
    if ext in ('.e01', '.ex01'):
        ewf_paths = pyewf.glob(img_path)
        ewf_handle = pyewf.handle()
        ewf_handle.open(ewf_paths)
        return EWFImgInfo(ewf_handle)
    else:
        return pytsk3.Img_Info(img_path, pytsk3.TSK_IMG_TYPE_DETECT)
    
def count_video_files(fs_info, path="/"):
    count = 0
    for e in fs_info.open_dir(path=path):
        nm = e.info.name.name
        if nm in (b'.', b'..') or e.info.meta is None:
            continue
        name = nm.decode('utf-8', 'ignore')
        if e.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            count += count_video_files(fs_info, path + "/" + name)
        elif name.lower().endswith(VIDEO_EXTENSIONS):
            count += 1
    return count

def extract_video_files(fs_info, output_dir, path="/", total_count=None, progress=None):
    results = []
    processed = 0
    is_root = (path == "/")

    for e in fs_info.open_dir(path=path):
        nm = e.info.name.name
        if nm in [b'.', b'..'] or e.info.meta is None:
            continue

        name = nm.decode('utf-8', 'ignore')
        name_lower = name.lower()
        filepath = path.rstrip('/') + '/' + name

        if e.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            results += extract_video_files(
                fs_info, output_dir, filepath, total_count, progress
            )
            continue
        
        if not name_lower.endswith(VIDEO_EXTENSIONS):
            continue

        # 처리된 파일 수 카운트
        processed += 1
        if progress:
            progress[0] += 1
            msg = {"processed": progress[0], "total": total_count}
            print(json.dumps(msg), flush=True)
        
        # 파일 읽기
        fobj = fs_info.open(filepath)
        size = fobj.info.meta.size
        buffer = BytesIO()
        offset = 0
        chunk_size = 4 * 1024 * 1024

        while offset < size:
            try:
                chunk = fobj.read_random(offset, min(chunk_size, size - offset))
            except OSError as e:
                logger.warning(f"read_random 오류 @ offset={offset}: {e} → 중단")
                break

            if not chunk:
                break

            buffer.write(chunk)
            offset += len(chunk)

        data = buffer.getvalue()

        # 공통 카테고리
        category = path.lstrip('/').split('/',1)[0] or "root"
        
        # MP4 처리
        if name_lower.endswith('.mp4'):
            # 1) 원본 저장
            orig_dir = os.path.join(output_dir, category)
            os.makedirs(orig_dir, exist_ok=True)
            orig_path = os.path.join(orig_dir, name)
            with open(orig_path, 'wb') as wf:
                wf.write(data)

            # 2) 슬랙 히든 복원 (raw + slack)
            raw_dir = os.path.join(orig_dir, 'raw')
            slack_dir = os.path.join(orig_dir, 'slack')
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(slack_dir, exist_ok=True)

            slack_info = recover_mp4_slack(
                filepath=orig_path,
                output_h264_dir=raw_dir,
                output_video_dir=slack_dir,
                target_format="mp4"
            )

            # 3) 결과 기록
            analysis = {
                'basic': get_basic_info(orig_path),
                'integrity': get_integrity_info(orig_path),
                'structure': get_structure_info(orig_path)
            }
            results.append({
                'name': name,
                'path': filepath,
                'size': size,
                'origin_video': orig_path,
                'slack_info': slack_info,
                'analysis': analysis
            })
            continue

        # AVI 처리
        temp_dir = os.path.join(output_dir, category, 'tmp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_avi = os.path.join(temp_dir, name)
        with open(temp_avi, 'wb') as wf:
            wf.write(data)

        # 슬랙 & 채널 복원
        base_dir = os.path.join(output_dir, category)
        raw_dir = os.path.join(base_dir, 'raw')
        slack_dir = os.path.join(base_dir, 'slack')
        channels_dir = os.path.join(base_dir, 'channels')
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(slack_dir, exist_ok=True)
        os.makedirs(channels_dir, exist_ok=True)

        avi_info = recover_avi_slack(
            input_avi=temp_avi,
            raw_out_dir=raw_dir,
            slack_out_dir=slack_dir,
            channels_out_dir=channels_dir,
            target_format='mp4'
        )

        # 전체 채널 MP4 복사
        for label, info in avi_info.items():
            full_mp4 = info.get('full_path')
            if full_mp4 and os.path.exists(full_mp4):
                chan_dir = os.path.join(output_dir, category, label)
                os.makedirs(chan_dir, exist_ok=True)
                dst = os.path.join(chan_dir, os.path.basename(full_mp4))
                shutil.copy2(full_mp4, dst)

        # 결과 저장 - AVI의 경우 slack_info 추가
        # 각 채널의 slack_rate 중 최대값을 사용하거나 평균값을 사용
        slack_rates = [info.get('slack_rate', 0) for info in avi_info.values() if 'slack_rate' in info]
        overall_slack_rate = max(slack_rates) if slack_rates else 0.0
        
        slack_info = {
            'slack_rate': overall_slack_rate,
            'channels': avi_info  # 채널별 상세 정보도 포함
        }
        
        analysis = {
            'basic': get_basic_info(orig_path),
            'integrity': get_integrity_info(orig_path),
            'structure': get_structure_info(orig_path),
            'slack_info': slack_info  # 분석에도 포함
        }
        
        results.append({
            'name': name,
            'path': filepath,
            'size': size,
            'origin_video': orig_path,
            'slack_info': slack_info,  # 최상위 레벨에 slack_info 추가
            'channels': avi_info,
            'analysis': analysis
        })

    # 요약 출력
    if is_root and total_count is not None:
        logger.info(f"총 {total_count}개 파일 처리 완료")

    return results

def extract_videos_from_e01(e01_path):
    start_time = time.time()

    img_path = e01_path
    logger.info(f"▶ 분석용 E01 파일: {img_path}")

    if not img_path:
        print("E01 파일을 선택하지 않았습니다. 종료합니다.")
        return [], None, 0

    try:
        img_info = open_image_file(img_path)
        volume = pytsk3.Volume_Info(img_info)
    except Exception as e:
        logger.error(f"이미지 열기 실패: {e}")
        return [], None, 0

    temp_base = tempfile.gettempdir()                 # 예: C:\Users\user\AppData\Local\Temp
    e01_size  = os.stat(img_path).st_size
    needed    = int(e01_size * 1.2) + 1_000_000_000   # 1.2배 + 1GB 버퍼 (원하면 조정)
    free      = shutil.disk_usage(temp_base).free

    if free < needed:
        # 렌더러로 보낼 신호(JSON 한 줄)
        print(json.dumps({"event": "disk_full", "free": free, "needed": needed}), flush=True)
        return [], None, 0

    # 충분하면 임시 폴더 생성
    output_dir = tempfile.mkdtemp(prefix="retato_", dir=temp_base)

    for part in volume:
        # 사용 불가 파티션 건너뛰기
        if part.flags == pytsk3.TSK_VS_PART_FLAG_UNALLOC or part.start == 0:
            logger.info(f"건너뜀: Unallocated 파티션 (offset: {part.start})")
            continue

        fs = pytsk3.FS_Info(img_info, offset=part.start * 512)
        total = count_video_files(fs)

        # 시작 전 전체 개수 한 번 전송
        print(json.dumps({"processed": 0, "total": total}), flush=True)

        # 실제 복구 및 진행 상황 출력
        res = extract_video_files(
            fs,
            output_dir,
            path="/",
            total_count=total,
            progress=[0]
        )

        # 처리 시간 로깅
        elapsed = int(time.time() - start_time)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        print(f"소요 시간: {h}시간 {m}분 {s}초")

        # 첫 파티션만 처리하고 종료
        return res, output_dir, total

    # 파티션이 하나도 없을 경우
    return res, output_dir, total