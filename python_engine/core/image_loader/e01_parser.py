import os
import pyewf
import pytsk3
import logging
import tempfile
import shutil
import json
import time
from io import BytesIO
from python_engine.core.recovery.mp4.extract_slack import recover_mp4_slack
from python_engine.core.recovery.avi.extract_slack import recover_avi_slack
from python_engine.core.analyzer.basic_info_parser import get_basic_info
from python_engine.core.analyzer.integrity import get_integrity_info
from python_engine.core.analyzer.struc import get_structure_info

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

def open_image_file(img_path):
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
    for entry in fs_info.open_dir(path=path):
        name = entry.info.name.name
        if name in (b'.', b'..') or entry.info.meta is None:
            continue
        name_str = name.decode('utf-8', 'ignore')
        if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            count += count_video_files(fs_info, path + "/" + name_str)
        elif name_str.lower().endswith(VIDEO_EXTENSIONS):
            count += 1
    return count

def read_file_content(file_obj):
    size = file_obj.info.meta.size
    buffer = BytesIO()
    offset = 0
    chunk_size = 4 * 1024 * 1024
    while offset < size:
        try:
            chunk = file_obj.read_random(offset, min(chunk_size, size - offset))
        except OSError as e:
            logger.warning(f"read_random 오류 @ offset={offset}: {e}")
            break
        if not chunk:
            break
        buffer.write(chunk)
        offset += len(chunk)
    return buffer.getvalue()

def build_analysis(origin_video_path):
    return {
        'basic': get_basic_info(origin_video_path),
        'integrity': get_integrity_info(origin_video_path),
        'structure': get_structure_info(origin_video_path),
    }

def handle_mp4_file(name, filepath, data, output_dir, category):
    orig_dir = os.path.join(output_dir, category)
    os.makedirs(orig_dir, exist_ok=True)

    original_path = os.path.join(orig_dir, name)
    with open(original_path, 'wb') as wf:
        wf.write(data)

    raw_dir = os.path.join(orig_dir, 'raw')
    slack_dir = os.path.join(orig_dir, 'slack')
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(slack_dir, exist_ok=True)

    slack_info = recover_mp4_slack(
        filepath=original_path,
        output_h264_dir=raw_dir,
        output_video_dir=slack_dir,
        target_format="mp4"
    )

    origin_video_path = slack_info.get('source_path', original_path)

    return {
        'name': name,
        'path': filepath,
        'size': len(data),
        'origin_video': origin_video_path,
        'slack_info': slack_info,
        'analysis': build_analysis(origin_video_path)
    }

def handle_avi_file(name, filepath, data, output_dir, category):
    orig_dir = os.path.join(output_dir, category)
    os.makedirs(orig_dir, exist_ok=True)

    original_path = os.path.join(orig_dir, name)
    with open(original_path, 'wb') as wf:
        wf.write(data)

    avi_info = recover_avi_slack(
        input_avi=original_path,
        base_dir=orig_dir,
        target_format="mp4"
    )
    if avi_info is None:
        return None

    origin_video_path = avi_info.get('source_path', avi_info.get('origin_path', original_path))
    channels_only = {k: v for k, v in avi_info.items() if isinstance(v, dict)}
    
    return {
        'name': name,
        'path': filepath,
        'size': len(data),
        'origin_video': origin_video_path,
        'channels': channels_only,
        'analysis': build_analysis(origin_video_path)
    }

def extract_video_files(fs_info, output_dir, path="/", total_count=None, progress=None):
    results = []
    for entry in fs_info.open_dir(path=path):
        name = entry.info.name.name
        if name in [b'.', b'..'] or entry.info.meta is None:
            continue

        name_str = name.decode('utf-8', 'ignore')
        filepath = path.rstrip('/') + '/' + name_str

        if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            results += extract_video_files(fs_info, output_dir, filepath, total_count, progress)
            continue

        if not name_str.lower().endswith(VIDEO_EXTENSIONS):
            continue

        if progress:
            progress[0] += 1
            print(json.dumps({"processed": progress[0], "total": total_count}), flush=True)

        file_obj = fs_info.open(filepath)
        data = read_file_content(file_obj)
        category = path.lstrip('/').split('/',1)[0] or "root"

        if name_str.lower().endswith('.mp4'):
            result = handle_mp4_file(name_str, filepath, data, output_dir, category)
        else: 
            result = handle_avi_file(name_str, filepath, data, output_dir, category)
        
        if result:
            results.append(result)
    return results

def extract_videos_from_e01(e01_path):
    logger.info(f"▶ 분석용 E01 파일: {e01_path}")
    start_time = time.time()

    try:
        img_info = open_image_file(e01_path)
        volume = pytsk3.Volume_Info(img_info)
    except Exception as e:
        logger.error(f"이미지 열기 실패: {e}")
        return [], None, 0

    temp_base = tempfile.gettempdir()
    e01_size = os.stat(e01_path).st_size
    needed = int(e01_size * 1.2) + 1_000_000_000
    free = shutil.disk_usage(temp_base).free

    if free < needed:
        print(json.dumps({"event": "disk_full", "free": free, "needed": needed}), flush=True)
        return [], None, 0

    output_dir = tempfile.mkdtemp(prefix="retato_", dir=temp_base)

    for partition in volume:
        if partition.flags == pytsk3.TSK_VS_PART_FLAG_UNALLOC or partition.start == 0:
            logger.info(f"건너뜀: Unallocated 파티션 (offset: {partition.start})")
            continue

        fs_info = pytsk3.FS_Info(img_info, offset=partition.start * 512)
        total = count_video_files(fs_info)
        print(json.dumps({"processed": 0, "total": total}), flush=True)

        results = extract_video_files(fs_info, output_dir, path="/", total_count=total, progress=[0])

        elapsed = int(time.time() - start_time)
        h, m = divmod(elapsed, 60)
        logger.info(f"소요 시간: {h // 60}시간 {m % 60}분 {m}초")

        return results, output_dir, total

    return [], output_dir, 0