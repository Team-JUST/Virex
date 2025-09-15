import os
import pyewf
import pytsk3
import logging
import tempfile
import shutil
import json
import time
import struct
import subprocess
import sys
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
    except Exception as e:
        logger.error(f"이미지 열기 실패: {e}")
        return [], None, 0

    # 임시 출력 디렉토리 준비 + 여유 공간 확인
    temp_base = tempfile.gettempdir()
    e01_size = os.stat(e01_path).st_size
    needed = int(e01_size * 1.2) + 1_000_000_000
    free = shutil.disk_usage(temp_base).free
    if free < needed:
        print(json.dumps({"event": "disk_full", "free": free, "needed": needed}), flush=True)
        return [], None, 0

    output_dir = tempfile.mkdtemp(prefix="Virex_", dir=temp_base)
    print(json.dumps({"tempDir": output_dir}), flush=True)

    all_results, all_total = [], 0

    for partition in volume:
        if partition.flags == pytsk3.TSK_VS_PART_FLAG_UNALLOC or partition.start == 0:
            logger.info(f"건너뜀: Unallocated 파티션 (offset: {partition.start})")
            continue

        try:
            fs_info = pytsk3.FS_Info(img_info, offset=partition.start * 512)
        except Exception as e:
            logger.warning(f"FS mount 실패 (offset={partition.start*512}): {e}")
            continue

        fat_res = dump_unalloc_fat32(
            img_info,
            part_start_sector=partition.start,
            sector_size=512,
            out_dir=output_dir,
            label=f"p{partition.addr}_fs_unalloc"
        )
        if fat_res.get("ok"):
            print(json.dumps({
                "event": "fs_unalloc_done",
                "chunks": fat_res["chunks"],
                "bytes": fat_res["bytes"]
            }), flush=True)

            try:
                ffmpeg_dir = os.environ.get("VIREX_FFMPEG_DIR")  # Electron main에서 세팅해주면 좋음
                cmd = [sys.executable,  # 현재 파이썬으로 vol_carver.py 실행
                       os.path.join(os.path.dirname(__file__), "tools", "vol_carver.py"),
                       os.path.join(output_dir, f"p{partition.addr}_fs_unalloc")]
                if ffmpeg_dir:
                    cmd += ["--ffmpeg-dir", ffmpeg_dir]
                # 블로킹 호출(완료 후 파일 생성됨). 로그 필요시 text=True로 Popen 사용 가능
                subprocess.run(cmd, check=True)
            except Exception as e:
                logger.warning(f"vol_carver run failed: {e}")

        else:
            print(json.dumps({
                "event": "fs_unalloc_skip",
                "reason": fat_res.get("reason", "unknown")
            }), flush=True)

        total = count_video_files(fs_info)
        all_total += total
        print(json.dumps({"processed": 0, "total": total}), flush=True)

        part_results = extract_video_files(
            fs_info, output_dir, path="/", total_count=total, progress=[0]
        )
        all_results.extend(part_results)

    elapsed = int(time.time() - start_time)
    h, m = divmod(elapsed, 60)
    logger.info(f"소요 시간: {h // 60}시간 {m % 60}분 {m}초")

    return all_results, output_dir, all_total



def _b_u8(b, o):  return b[o]
def _b_u16(b, o): return struct.unpack_from("<H", b, o)[0]
def _b_u32(b, o): return struct.unpack_from("<I", b, o)[0]

def _fat32_looks_like_bpb(bpb: bytes) -> bool:
    if not bpb or len(bpb) < 512:
        return False
    if bpb[510] != 0x55 or bpb[511] != 0xAA:
        return False
    if bpb[3:11] == b"EXFAT   ":
        return False
    return True

def _fat32_parse_layout(bpb: bytes):
    bps = _b_u16(bpb, 11)
    spc = _b_u8(bpb, 13)
    rsv = _b_u16(bpb, 14)
    nf  = _b_u8(bpb, 16)
    fatsz16 = _b_u16(bpb, 22)
    fatsz32 = _b_u32(bpb, 36)
    fatsz = fatsz32 if fatsz16 == 0 else fatsz16

    fat_start_bytes  = rsv * bps
    fat_bytes        = fatsz * bps
    data_start_bytes = (rsv + nf * fatsz) * bps
    cluster_bytes    = bps * spc
    return fat_start_bytes, fat_bytes, data_start_bytes, cluster_bytes

def dump_unalloc_fat32(img_info, part_start_sector, sector_size, out_dir, label="fs_unalloc_fat32"):
    part_off = part_start_sector * sector_size
    bpb = img_info.read(part_off, 512)
    if not _fat32_looks_like_bpb(bpb):
        return {"ok": False, "reason": "not_fat32"}

    fat_off_rel, fat_bytes, data_off_rel, cluster_bytes = _fat32_parse_layout(bpb)
    fat = img_info.read(part_off + fat_off_rel, fat_bytes)
    if not fat:
        return {"ok": False, "reason": "fat_read_fail"}

    total_entries = len(fat) // 4
    out_path = os.path.join(out_dir, label)
    os.makedirs(out_path, exist_ok=True)

    idx, total_bytes, items = 1, 0, []
    cl = 2
    while cl < total_entries:
        val = _b_u32(fat, cl * 4) & 0x0FFFFFFF
        if val == 0:
            start = cl
            while cl < total_entries and (_b_u32(fat, cl * 4) & 0x0FFFFFFF) == 0:
                cl += 1
            length = cl - start

            run_off_abs = part_off + data_off_rel + (start - 2) * cluster_bytes
            run_size    = length * cluster_bytes

            fn = os.path.join(out_path, f"{idx:03d}.bin")
            with open(fn, "wb") as wf:
                remain, cur = run_size, run_off_abs
                CHUNK = 8 * 1024 * 1024
                while remain > 0:
                    to_read = min(remain, CHUNK)
                    buf = img_info.read(cur, to_read)
                    if not buf:
                        break
                    wf.write(buf)
                    cur += len(buf)
                    remain -= len(buf)

            wrote = run_size - remain
            total_bytes += wrote
            items.append({
                "index": idx,
                "file": fn,
                "clusters": [int(start), int(start+length-1)],
                "byte_len": wrote
            })
            print(json.dumps({
                "event": "fat32_run",
                "file": fn,
                "clusters": [int(start), int(start+length-1)],
                "bytes": wrote
            }), flush=True)
            idx += 1
        else:
            cl += 1

    return {"ok": idx > 1, "chunks": len(items), "bytes": total_bytes, "items": items}