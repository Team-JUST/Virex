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
from python_engine.core.analyzer.basic_info_parser import get_basic_info_with_meta
from python_engine.core.analyzer.integrity import get_integrity_info
from python_engine.core.analyzer.struc import get_structure_info
from python_engine.core.recovery.utils.unit import bytes_to_unit

SECTOR_SIZE_DEFAULT = 512

def _detect_sector_size(img_info, volume):
    try:
        bs = getattr(volume.info, "block_size", None)
        if bs and bs > 0:
            return int(bs)
    except Exception:
        pass
    try:
        ewf = getattr(img_info, "_ewf_handle", None)
        if ewf:
            s = getattr(ewf, "get_bytes_per_sector", None)
            if callable(s):
                v = s()
                if v and v > 0:
                    return int(v)
    except Exception:
        pass
    return SECTOR_SIZE_DEFAULT

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

    slack_dir = os.path.join(orig_dir, 'slack')
    os.makedirs(slack_dir, exist_ok=True)

    slack_info = recover_mp4_slack(
        filepath=original_path,
        output_h264_dir=slack_dir,
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
    video_stem = os.path.splitext(name)[0]
    orig_dir = os.path.join(output_dir, category, video_stem)
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
        category = path.lstrip('/').split('/', 1)[0] or "root"

        if name_str.lower().endswith('.mp4'):
            result = handle_mp4_file(name_str, filepath, data, file_obj, output_dir, category)
        else: 
            result = handle_avi_file(name_str, filepath, data, file_obj, output_dir, category)

        if result:
            results.append(result)
    return results

def extract_videos_from_e01(e01_path):
    logger.info(f"▶ 분석용 E01 파일: {e01_path}")
    start_time = time.time()

    try:
        img_info = open_image_file(e01_path)
        volume = pytsk3.Volume_Info(img_info)

        sector_size = _detect_sector_size(img_info, volume)

    except Exception as e:
        logger.error(f"이미지 열기 실패: {e}")
        return [], None, 0

    temp_base = tempfile.gettempdir()
    free = shutil.disk_usage(temp_base).free
    needed = int(img_info.get_size() * 0.2) + 1_000_000_000

    if free < needed:
        print(json.dumps({"event": "disk_full", "free": free, "needed": needed}), flush=True)
        return [], None, 0

    output_dir = tempfile.mkdtemp(prefix="Virex_", dir=temp_base)
    print(json.dumps({"tempDir": output_dir}), flush=True)

    # --- 볼륨 슬랙 계산/저장 섹션 (교체본) ---
    media_size = img_info.get_size()
    allocated = _collect_allocated_ranges(volume, sector_size)
    # 보호 영역 제외: 처음/끝 1 섹터(보호/백업 GPT 등) 제거
    gaps = _subtract_reserved(
        _compute_gaps(allocated, media_size),
        [(0, sector_size), (media_size - sector_size, media_size)]
    )


    # 크기 일관성 검증 이벤트
    allocated_total = _sum_ranges(allocated)
    expected_slack = max(0, media_size - allocated_total)
    actual_slack = sum(length for (_, length) in gaps)
    print(json.dumps({
        "event": "vol_check",
        "media_size": media_size,
        "allocated_total": allocated_total,
        "expected_slack": expected_slack,
        "actual_slack": actual_slack
    }), flush=True)
    if actual_slack != expected_slack:
        print(json.dumps({
            "event": "vol_mismatch",
            "reason": "size_mismatch",
            "expected_slack": expected_slack,
            "actual_slack": actual_slack
        }), flush=True)

    print(json.dumps({"event": "vol_start", "output_dir": output_dir, "total": len(gaps)}), flush=True)

    if actual_slack > 0 and len(gaps) > 0:
        slack_dir = os.path.join(output_dir, "vol_slack")
        os.makedirs(slack_dir, exist_ok=True)

        meta = {
            "image_path": e01_path,
            "media_size": media_size,
            "sector_size": sector_size,
            "partitions": [{"start": s, "end": e} for (s, e) in allocated],
            "partition_count": len(allocated),
            "gaps": [],
            "allocated_total": allocated_total,
            "slack_total": actual_slack
        }

        for idx, (off, length) in enumerate(gaps):
            gap_file = _dump_gap(img_info, off, length, slack_dir, idx)  # 001.bin, 002.bin...
            meta["gaps"].append({
                "index": idx, "offset": off, "length": length, "file": gap_file
            })
            print(json.dumps({
                "event": "vol_gap", "index": idx, "offset": off, "length": length
            }), flush=True)

        meta_path = os.path.join(slack_dir, "volume_slack.json")
        with open(meta_path, "w", encoding="utf-8") as wf:
            json.dump(meta, wf, ensure_ascii=False, indent=2)

        print(json.dumps({"event": "vol_done", "gaps": len(gaps), "meta": meta_path}), flush=True)
    else:
        # 갭이 없으면 폴더/메타 생성 안 함
        print(json.dumps({"event": "vol_done", "gaps": 0, "meta": None}), flush=True)
    # --- 볼륨 슬랙 섹션 끝 ---

    try:
        vol_slack_dir = os.path.join(output_dir, "vol_slack")
        meta_json = os.path.join(vol_slack_dir, "volume_slack.json")
        if os.path.isfile(meta_json):
            print(json.dumps({"event": "carve_start", "dir": vol_slack_dir}), flush=True)
            from python_engine.core.vol_carver import auto_carve_and_rebuild_from_vol_slack
            carve_summary = auto_carve_and_rebuild_from_vol_slack(vol_slack_dir)
            print(json.dumps({"event": "carve_done", **carve_summary}), flush=True)
        else:
            print(json.dumps({"event": "carve_skip", "reason": "no_vol_slack_meta"}), flush=True)
    except Exception as e:
        print(json.dumps({"event": "carve_error", "error": str(e)}), flush=True)


    all_results = []
    all_total = 0

    for partition in volume:
        if partition.flags == pytsk3.TSK_VS_PART_FLAG_UNALLOC:
            logger.info(f"건너뜀: Unallocated 파티션 (offset: {partition.start})")
            continue

        try:
            fs_info = pytsk3.FS_Info(img_info, offset=partition.start * sector_size)
        except Exception as e:
            print(json.dumps({
                "event": "fs_mount_fail",
                "start": partition.start,
                "len": partition.len,
                "error": str(e)
            }), flush=True)
            continue

        total = count_video_files(fs_info)
        all_total += total
        print(json.dumps({"processed": 0, "total": total, "part_start": partition.start}), flush=True)

        part_results = extract_video_files(fs_info, output_dir, path="/", total_count=total, progress=[0])
        all_results.extend(part_results)

    elapsed = int(time.time() - start_time)
    h, m = divmod(elapsed, 60)
    logger.info(f"소요 시간: {h // 60}시간 {m % 60}분 {m}초")

    return all_results, output_dir, all_total


# 볼륨 슬랙 

def _collect_allocated_ranges(volume, sector_size):
    """할당된 파티션 범위를 (start_byte, end_byte) 리스트로 반환하고 병합한다."""
    ranges = []
    for part in volume:
        if part.flags == pytsk3.TSK_VS_PART_FLAG_UNALLOC:
            continue
        if part.len == 0:
            continue
        s = part.start * sector_size
        e = (part.start + part.len) * sector_size
        ranges.append((s, e))
    ranges.sort()
    merged = []
    for s, e in ranges:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            ps, pe = merged[-1]
            merged[-1] = (ps, max(pe, e))
    return merged


def _compute_gaps(allocated_ranges, media_size):
    """[0, media_size)에서 allocated_ranges의 빈 공간들을 (offset, length)로 반환."""
    gaps = []
    cursor = 0
    for s, e in allocated_ranges:
        if cursor < s:
            gaps.append((cursor, s - cursor))
        cursor = max(cursor, e)
    if cursor < media_size:
        gaps.append((cursor, media_size - cursor))
    return gaps

def _sum_ranges(ranges):
    return sum(e - s for (s, e) in ranges)

def _subtract_reserved(gaps, reserved_ranges):
    def subtract(seg, cut):
        s, l = seg
        e = s + l
        cs, ce = cut
        # 겹침 없으면 그대로
        if ce <= s or e <= cs:
            return [seg]
        out = []
        if s < cs:
            out.append((s, max(0, cs - s)))
        if ce < e:
            out.append((ce, max(0, e - ce)))
        return [(ss, ll) for (ss, ll) in out if ll > 0]

    out = []
    for g in gaps:
        frags = [g]
        for r in reserved_ranges:
            nxt = []
            for f in frags:
                nxt.extend(subtract(f, r))
            frags = nxt
        out.extend(frags)
    return out


def _dump_gap(img_info, offset, length, outdir, index, chunk_size=4*1024*1024):
    """갭을 chunk로 읽어 001.bin 같은 이름으로 저장하고 파일 경로를 반환."""
    fn = os.path.join(outdir, f"{index+1:03d}.bin")
    remaining = length
    cur = offset
    with open(fn, "wb") as wf:
        while remaining > 0:
            n = min(remaining, chunk_size)
            data = img_info.read(cur, n)
            if not data:
                break
            wf.write(data)
            cur += len(data)
            remaining -= len(data)
    return fn
