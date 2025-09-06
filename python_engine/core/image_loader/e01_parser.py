import os
import struct
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
from python_engine.core.analyzer.basic_info_parser import get_basic_info_with_meta
from python_engine.core.analyzer.integrity import get_integrity_info
from python_engine.core.analyzer.struc import get_structure_info
from python_engine.core.recovery.utils.unit import bytes_to_unit

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

def build_analysis(origin_video_path, meta):
    return {
        'basic': get_basic_info_with_meta(origin_video_path, meta),
        'integrity': get_integrity_info(origin_video_path),
        'structure': get_structure_info(origin_video_path),
    }

def handle_mp4_file(name, filepath, data, file_obj, output_dir, category):
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
        'size': bytes_to_unit(len(data)),
        'origin_video': origin_video_path,
        'slack_info': slack_info,
        'analysis': build_analysis(origin_video_path, file_obj.info.meta)
    }

def handle_avi_file(name, filepath, data, file_obj, output_dir, category):
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
        'size': bytes_to_unit(len(data)),
        'origin_video': origin_video_path,
        'channels': channels_only,
        'analysis': build_analysis(origin_video_path, file_obj.info.meta)
    }

def extract_video_files(fs_info, output_dir, path="/", total_count=None, progress=None):
    results = []
    for entry in fs_info.open_dir(path=path):
        name = entry.info.name.name
        if name in [b'.', b'..'] or entry.info.meta is None:
            continue

        name_str = name.decode('utf-8', 'ignore')
        filepath = path.rstrip('/') + '/' + name_str

        # 하위 디렉토리는 재귀
        if entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            results += extract_video_files(fs_info, output_dir, filepath, total_count, progress)
            continue

        # 비디오 확장자만
        if not name_str.lower().endswith(VIDEO_EXTENSIONS):
            continue

        # 진행률 업데이트
        if progress:
            progress[0] += 1
            print(json.dumps({"processed": progress[0], "total": total_count}), flush=True)

        # 파일 열고 전체 데이터 읽기
        file_obj = fs_info.open(filepath)
        data = read_file_content(file_obj)
        # 최상위 디렉토리명을 카테고리로 사용 (없으면 root)
        category = path.lstrip('/').split('/', 1)[0] or "root"

        # =========================
        # MP4 처리 (인라인)
        # =========================
        if name_str.lower().endswith('.mp4'):
            # 1) 원본 저장
            orig_dir = os.path.join(output_dir, category)
            os.makedirs(orig_dir, exist_ok=True)

            original_path = os.path.join(orig_dir, name_str)
            with open(original_path, 'wb') as wf:
                wf.write(data)

            # 2) 슬랙 히든 복원 (raw + slack)
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

            # 3) 분석 및 결과 기록
            origin_video_path = slack_info.get('source_path', original_path)
            analysis = build_analysis(origin_video_path, file_obj.info.meta)

            results.append({
                'name': name_str,
                'path': filepath,
                'size': bytes_to_unit(len(data)),
                'origin_video': origin_video_path,
                'slack_info': slack_info,
                'analysis': analysis
            })
            continue  # 한 파일 처리 완료 후 다음 항목

        # =========================
        # AVI 처리 (인라인)
        # =========================
        if name_str.lower().endswith('.avi'):
            # 1) 기본 디렉토리/원본 저장
            base_dir = os.path.join(output_dir, category)
            os.makedirs(base_dir, exist_ok=True)

            original_path = os.path.join(base_dir, name_str)
            with open(original_path, 'wb') as wf:
                wf.write(data)

            # 2) 작업용 서브 디렉토리
            tmp_dir = os.path.join(base_dir, 'tmp')
            raw_dir = os.path.join(base_dir, 'raw')
            slack_dir = os.path.join(base_dir, 'slack')
            channels_dir = os.path.join(base_dir, 'channels')
            os.makedirs(tmp_dir, exist_ok=True)
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(slack_dir, exist_ok=True)
            os.makedirs(channels_dir, exist_ok=True)

            # 임시 avi 복사 (복사 실패 시 원본 그대로 사용)
            temp_avi = os.path.join(tmp_dir, name_str)
            try:
                shutil.copy2(original_path, temp_avi)
                input_avi = temp_avi
            except Exception:
                input_avi = original_path

            # 3) 슬랙 & 채널 복원
            avi_info = recover_avi_slack(
                input_avi=input_avi,
                raw_out_dir=raw_dir,
                slack_out_dir=slack_dir,
                channels_out_dir=channels_dir,
                target_format='mp4'
            )
            if not avi_info:
                # 복원 실패 시 스킵
                continue

            # 4) 분석 대상(원본) 경로 결정
            origin_video_path = avi_info.get('source_path', avi_info.get('origin_path', original_path))

            # 5) 채널 dict만 추출
            channels_only = {k: v for k, v in avi_info.items() if isinstance(v, dict)}

            # 6) 채널별 full MP4가 있으면 category/<label>/ 로 복사
            for label, info in channels_only.items():
                full_mp4 = info.get('full_path')
                if full_mp4 and os.path.exists(full_mp4):
                    chan_dir = os.path.join(base_dir, label)
                    os.makedirs(chan_dir, exist_ok=True)
                    dst = os.path.join(chan_dir, os.path.basename(full_mp4))
                    try:
                        shutil.copy2(full_mp4, dst)
                    except Exception as e:
                        logger.warning(f"채널 파일 복사 실패({label}): {e}")

            # 7) slack_rate 집계 (최대값)
            slack_rates = [info.get('slack_rate', 0.0) for info in channels_only.values() if isinstance(info, dict)]
            overall_slack_rate = max(slack_rates) if slack_rates else 0.0

            slack_info = {
                'slack_rate': overall_slack_rate,
                'channels': channels_only  # 채널별 상세 정보 포함
            }

            # 8) 분석 + slack_info 포함
            analysis = build_analysis(origin_video_path, file_obj.info.meta)
            analysis_with_slack = dict(analysis)
            analysis_with_slack['slack_info'] = slack_info

            # 9) 결과 저장
            results.append({
                'name': name_str,
                'path': filepath,
                'size': bytes_to_unit(len(data)),
                'origin_video': origin_video_path,
                'slack_info': slack_info,     # 최상위에도 포함
                'channels': channels_only,    # 채널 상세
                'analysis': analysis_with_slack
            })
            continue

        # 혹시 다른 확장자면 continue (위에서 필터링했지만 방어 코드)
        continue

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

    output_dir = tempfile.mkdtemp(prefix="Virex_", dir=temp_base)

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