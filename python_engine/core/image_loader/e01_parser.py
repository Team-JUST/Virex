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

logger = logging.getLogger(__name__)

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

VIDEO_EXTENSIONS = ('.mp4', '.avi')

class EWFImgInfo(pytsk3.Img_Info):
    def __init__(self, ewf_handle):
        self._ewf_handle = ewf_handle
        super().__init__("", pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def read(self, offset, size):
        # 1) read_random 지원하는 경우
        fn = getattr(self._ewf_handle, "read_random", None)
        if callable(fn):
            return fn(offset, size)

        # 2) seek + read 조합
        seek = getattr(self._ewf_handle, "seek", None) or getattr(self._ewf_handle, "seek_offset", None)
        read = getattr(self._ewf_handle, "read", None) or getattr(self._ewf_handle, "read_buffer", None)
        if callable(seek) and callable(read):
            try:
                # pyewf.seek(offset, whence) → whence=0(SET)
                seek(offset, 0)
            except TypeError:
                # 일부 구현은 whence 인자 없음
                seek(offset)
            return read(size)

        # 3) 최종 안전망
        raise AttributeError("pyewf handle has no compatible read method")

    def get_size(self):
        # get_media_size() 우선
        gm = getattr(self._ewf_handle, "get_media_size", None)
        if callable(gm):
            return int(gm())
        # media_size() 또는 size 속성도 대응
        ms = getattr(self._ewf_handle, "media_size", None)
        if callable(ms):
            return int(ms())
        val = getattr(self._ewf_handle, "size", None)
        if isinstance(val, int):
            return val
        raise AttributeError("pyewf handle has no media size getter")


def open_image_file(img_path):
    ext = os.path.splitext(img_path)[1].lower()
    if ext in ('.e01', '.ex01'):
        ewf_paths = pyewf.glob(img_path)
        if not ewf_paths:
            raise RuntimeError(f"EWF segments not found for {img_path}")
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

    origin_video_path = original_path
    channels_only = None
    if isinstance(avi_info, dict):
        origin_video_path = avi_info.get('source_path', avi_info.get('origin_path', original_path))
        channels_only = {k: v for k, v in avi_info.items() if isinstance(v, dict)}

    return {
        'name': name,
        'path': filepath,
        'size': bytes_to_unit(len(data)),
        'origin_video': origin_video_path,
        **({'channels': channels_only} if channels_only else {}),
        'analysis': build_analysis(origin_video_path, file_obj.info.meta)
    }

def _safe_carve(vol_slack_dir: str):
    """vol_carver 호출이 어떤 이유로든 실패해도 전체 파이프라인을 중단시키지 않도록 보호."""
    try:
        meta_json = os.path.join(vol_slack_dir, "volume_slack.json")
        if not os.path.isfile(meta_json):
            print(json.dumps({"event": "carve_skip", "reason": "no_vol_slack_meta"}), flush=True)
            return None

        try:
            from python_engine.core.vol_carver import auto_carve_and_rebuild_from_vol_slack
        except Exception as ie:
            print(json.dumps({"event": "carve_import_error", "error": str(ie)}), flush=True)
            return None

        print(json.dumps({"event": "carve_start", "dir": vol_slack_dir}), flush=True)

        try:
            summary = auto_carve_and_rebuild_from_vol_slack(vol_slack_dir)
        except Exception as ce:
            print(json.dumps({"event": "carve_runtime_error", "error": str(ce)}), flush=True)
            return None

        if not isinstance(summary, dict):
            print(json.dumps({"event": "carve_done", "ok": False, "reason": "invalid_summary_type"}), flush=True)
            return None

        print(json.dumps({"event": "carve_done", **summary}), flush=True)
        return summary

    except Exception as e:
        print(json.dumps({"event": "carve_fatal_swallowed", "error": str(e)}), flush=True)
        return None
    

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
            print(json.dumps({
                "processed": progress[0],
                "total": total_count
            }), flush=True)

        file_obj = fs_info.open(filepath)
        data = read_file_content(file_obj)
        category = path.lstrip('/').split('/', 1)[0] or "root"

        if name_str.lower().endswith('.mp4'):
            result = handle_mp4_file(
                name_str, filepath, data, file_obj, output_dir, category
            )
        else:
            result = handle_avi_file(
                name_str, filepath, data, file_obj, output_dir, category
            )

        if result:
            results.append(result)

    return results


def extract_videos_from_e01(e01_path):

    logger.info(f"▶ 분석용 E01 파일: {e01_path}")
    start_time = time.time()

    # --- 이미지 열기 & 파티션 테이블 확인 ---
    try:
        img_info = open_image_file(e01_path)
        try:
            volume = pytsk3.Volume_Info(img_info)
            has_volume = True
        except Exception:
            volume = None
            has_volume = False
            print(json.dumps({"event": "no_partition_table",
                              "note": "Treating image as a single filesystem"}), flush=True)
    except Exception as e:
        logger.error(f"이미지 열기 실패: {e}")
        return [], None, 0

    # 섹터 크기
    sector_size = _detect_sector_size(img_info, volume) if has_volume else SECTOR_SIZE_DEFAULT

    # --- 작업 디렉토리 & 디스크 여유 확인 ---
    temp_base = tempfile.gettempdir()
    free = shutil.disk_usage(temp_base).free
    needed = int(img_info.get_size() * 0.2) + 1_000_000_000  # 이미지의 20% + 1GB
    if free < needed:
        print(json.dumps({"event": "disk_full", "free": free, "needed": needed}), flush=True)
        return [], None, 0

    output_dir = tempfile.mkdtemp(prefix="Virex_", dir=temp_base)
    print(json.dumps({"event": "temp_ready", "tempDir": output_dir}), flush=True)

    carved_path = os.path.join(output_dir, "carved_index.json")
    try:
        with open(carved_path, "w", encoding="utf-8") as f:
            json.dump({"items": []}, f, ensure_ascii=False, indent=2)
        print(json.dumps({
            "event": "carved_index_bootstrap",
            "path": carved_path
        }), flush=True)
    except Exception as e:
        print(json.dumps({
            "event": "carved_index_bootstrap_error",
            "error": str(e)
        }), flush=True)

    # ================================
    # 1) 볼륨 레벨 슬랙(vol_slack)
    # ================================
    if has_volume:
        media_size = img_info.get_size()
        allocated = _collect_allocated_ranges(volume, sector_size)         # [(start,end), ...] bytes
        gaps = _subtract_reserved(                                         # [(off,len), ...]
            _compute_gaps(allocated, media_size),
            [(0, sector_size), (media_size - sector_size, media_size)]
        )

        slack_dir = os.path.join(output_dir, "vol_slack")
        os.makedirs(slack_dir, exist_ok=True)

        meta = {
            "image_path": e01_path,
            "media_size": media_size,
            "sector_size": sector_size,
            "partitions": [{"start": s, "end": e} for (s, e) in allocated],
            "partition_count": len(allocated),
            "entries": [],
            "allocated_total": _sum_ranges(allocated),
            "slack_total": sum(length for (_, length) in gaps),
        }

        for idx, (off, length) in enumerate(gaps):
            gap_file = _dump_gap(img_info, off, length, slack_dir, idx)
            meta["entries"].append({
                "index": idx,
                "type": "gap",
                "offset": off,
                "length": length,
                "file": gap_file
            })

        meta_path = os.path.join(slack_dir, "volume_slack.json")
        with open(meta_path, "w", encoding="utf-8") as wf:
            json.dump(meta, wf, ensure_ascii=False, indent=2)

        print(json.dumps({"event": "vol_done",
                          "entries": len(meta["entries"]),
                          "meta": meta_path}), flush=True)

        summary = _safe_carve(slack_dir)

        try:
            if isinstance(summary, dict):
                with open(os.path.join(output_dir, "carved_index.json"), "w", encoding="utf-8") as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)
                print(json.dumps({
                    "event": "carved_index_written",
                    "path": os.path.join(output_dir, "carved_index.json"),
                    "items": len(summary.get("items", []))
                }), flush=True)
            else:
                # 실패/스킵이면 그냥 부팅한 빈 파일 그대로 둠
                print(json.dumps({
                    "event": "carved_index_empty_keep"
                }), flush=True)
        except Exception as e:
            print(json.dumps({"event": "carved_index_error", "error": str(e)}), flush=True)

    # ==========================================
    # 2) FS 내부 비할당(fs_unalloc) 덤프 (파티션별)
    # ==========================================
    if has_volume:
        fs_unalloc_root = os.path.join(output_dir, "fs_unalloc")
        os.makedirs(fs_unalloc_root, exist_ok=True)
        fs_unalloc_report = []
        print(json.dumps({"event": "volume_detect", "has_volume": has_volume}), flush=True)


        for pidx, part in enumerate(volume):
            if getattr(part, "flags", 0) & pytsk3.TSK_VS_PART_FLAG_ALLOC == 0:
                continue
            if int(part.len) == 0:
                continue

            # 파일시스템 존재 여부와 무관하게 시도하고, 실패하면 스킵
            try:
                res = dump_fs_unallocated(
                    img_info=img_info,
                    part_start_sector=int(part.start),
                    sector_size=sector_size,
                    out_dir=output_dir,
                    label=f"p{pidx}_fs_unalloc"
                )
            except Exception as e:
                res = {"ok": False, "reason": f"exception:{e}"}

            # 요약 기록
            try:
                desc = (part.desc or b"").decode("utf-8", "ignore")
            except Exception:
                desc = ""
            fs_unalloc_report.append({
                "index": pidx,
                "start_sector": int(part.start),
                "len_sector": int(part.len),
                "desc": desc,
                "result": res
            })

        fs_meta_path = os.path.join(fs_unalloc_root, "fs_unalloc_report.json")
        with open(fs_meta_path, "w", encoding="utf-8") as wf:
            json.dump(fs_unalloc_report, wf, ensure_ascii=False, indent=2)
        print(json.dumps({"event": "fs_unalloc_done", "report": fs_meta_path}), flush=True)

    # ================================
    # 3) 파일시스템에서 비디오 추출
    # ================================
    all_results, all_total = [], 0
    if has_volume:
        for part in volume:
            if getattr(part, "flags", 0) & pytsk3.TSK_VS_PART_FLAG_ALLOC == 0:
                continue
            if int(part.len) == 0:
                continue

            try:
                fs_info = pytsk3.FS_Info(img_info, offset=int(part.start) * sector_size)
            except Exception as e:
                print(json.dumps({
                    "event": "fs_mount_fail",
                    "start": int(part.start),
                    "len": int(part.len),
                    "error": str(e)
                }), flush=True)
                continue

            total = count_video_files(fs_info)
            all_total += total
            print(json.dumps({"event": "scan_begin",
                              "processed": 0, "total": total,
                              "part_start": int(part.start)}), flush=True)

            all_results.extend(
                extract_video_files(fs_info, output_dir, path="/", total_count=total, progress=[0])
            )
    else:
        # 파티션 테이블이 없고, 이미지 전체가 단일 FS인 경우
        try:
            fs_info = pytsk3.FS_Info(img_info)
        except Exception as e:
            print(json.dumps({"event": "fs_mount_fail_single", "error": str(e)}), flush=True)
            return [], output_dir, 0
        
        try:
            dump_fs_unallocated_single(fs_info, output_dir)
        except Exception as e:
                print(json.dumps({"event": "fs_unalloc_single_error", "error": str(e)}), flush=True)

        total = count_video_files(fs_info)
        all_total += total
        print(json.dumps({"event": "scan_begin",
                          "processed": 0, "total": total,
                          "part_start": 0}), flush=True)

        all_results.extend(
            extract_video_files(fs_info, output_dir, path="/", total_count=total, progress=[0])
        )

    # --- 종료 ---
    elapsed = int(time.time() - start_time)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    logger.info(f"소요 시간: {h}시간 {m}분 {s}초")

    print(json.dumps({"event": "extract_count", "n": len(all_results)}), flush=True)

    print(json.dumps({
        "event": "extract_done",
        "results": all_results,
        "output_dir": output_dir,
        "total": all_total
    }, ensure_ascii=False), flush=True)

    return all_results, output_dir, all_total


# 볼륨 슬랙 

def _collect_allocated_ranges(volume, sector_size):
    """할당된 파티션 범위를 (start_byte, end_byte) 리스트로 반환하고 병합한다."""
    ranges = []
    for part in volume:
        if (getattr(part, "flags", 0) & pytsk3.TSK_VS_PART_FLAG_ALLOC) == 0:
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


def _collect_fs_unalloc_runs(fs_info: pytsk3.FS_Info):
    UNALLOC = pytsk3.TSK_FS_BLOCK_FLAG_UNALLOC
    runs = []
    cur_start, prev = None, None
    for blk_addr, flags in fs_info.block_walk(0, fs_info.info.block_count - 1, UNALLOC):
        if (flags & UNALLOC) == 0:
            continue
        if cur_start is None:
            cur_start, prev = blk_addr, blk_addr
        elif blk_addr == prev + 1:
            prev = blk_addr
        else:
            runs.append((cur_start, prev))
            cur_start, prev = blk_addr, blk_addr
    if cur_start is not None:
        runs.append((cur_start, prev))
    return runs

def _dump_fs_unalloc_runs(fs_info, out_dir, start_index, part_index, max_chunk_blocks=4096):
    os.makedirs(out_dir, exist_ok=True)
    bs = fs_info.info.block_size
    runs = _collect_fs_unalloc_runs(fs_info)
    meta, index = [], start_index

    for rs, re in runs:
        total = re - rs + 1
        left, cur = total, rs
        while left > 0:
            take = min(left, max_chunk_blocks)
            off, ln = cur * bs, take * bs
            blob = fs_info.read_random(off, ln)

            fn = os.path.join(out_dir, f"{index+1:03d}.bin")
            with open(fn, "wb") as wf:
                wf.write(blob)

            meta.append({
                "index": index,
                "type": "fs_unalloc",
                "part_index": part_index,
                "fs_block_start": int(cur),
                "fs_block_count": int(take),
                "block_size": int(bs),
                "file": fn,
                "byte_offset_in_fs": int(off),
                "byte_length": int(ln),
            })
            index += 1
            cur += take
            left -= take
    return meta, index

def dump_fs_unallocated(img_info, part_start_sector, sector_size, out_dir, label="fs_unalloc"):
    """
    파티션 내부(FS 레벨)의 비할당 블록을 bin으로 저장한다.
    - img_info: pyewf.Img_Info 또는 pytsk3.Img_Info
    - part_start_sector: 파티션 시작 섹터(정수)
    - sector_size: 섹터 크기(byte)
    - out_dir: 출력 루트 폴더 (…/Virex_xxxx)
    """
    part_off = part_start_sector * sector_size
    try:
        fs = pytsk3.FS_Info(img_info, offset=part_off)
    except Exception as e:
        logger.warning(f"[FS] FS_Info open 실패 (offset={part_off}): {e}")
        return {"ok": False, "reason": str(e), "chunks": 0, "bytes": 0}

    block_size = int(getattr(fs.info, "block_size", 0)) or 4096  # 안전장치
    block_last = int(getattr(fs.info, "block_count", 0)) - 1
    flags = pytsk3.TSK_FS_BLOCK_FLAG_UNALLOC

    # 출력 폴더 준비
    fs_out = os.path.join(out_dir, "fs_unalloc")
    os.makedirs(fs_out, exist_ok=True)

    meta = []
    total_bytes = 0
    idx = 1

    def flush_span(start_blk, end_blk):
        nonlocal idx, total_bytes
        if start_blk is None or end_blk is None or end_blk < start_blk:
            return
        blk_cnt = (end_blk - start_blk + 1)
        byte_off_in_fs = start_blk * block_size
        byte_len = blk_cnt * block_size

        # FS 기준 오프셋으로 읽기
        try:
            data = fs.read_random(byte_off_in_fs, byte_len)
        except Exception as e:
            logger.warning(f"[FS] read_random 실패 off={byte_off_in_fs} len={byte_len}: {e}")
            return

        # 저장
        name = f"{idx:03d}.bin"
        out_path = os.path.join(fs_out, name)
        with open(out_path, "wb") as f:
            f.write(data)

        total_bytes += len(data)
        meta.append({
            "index": idx,
            "file": out_path,
            "fs_block_start": int(start_blk),
            "fs_block_end": int(end_blk),
            "fs_block_size": block_size,
            "byte_len": len(data),
            # 물리(이미지) 기준 바이트 오프셋도 기록(검증용)
            "img_byte_offset": int(part_off + byte_off_in_fs),
        })
        idx += 1

    # UNALLOC 연속 구간 수집
    span_start = None
    prev = None
    try:
        for blk in fs.block_walk(0, block_last, flags):
            baddr = int(blk.addr)
            # 연속 구간 병합
            if span_start is None:
                span_start = prev = baddr
            elif baddr == prev + 1:
                prev = baddr
            else:
                flush_span(span_start, prev)
                span_start, prev = baddr, baddr
        # 마지막 꼬리 처리
        flush_span(span_start, prev)
    except Exception as e:
        logger.warning(f"[FS] block_walk 실패: {e}")

    # 메타 저장
    meta_path = os.path.join(fs_out, "fs_unalloc.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"block_size": block_size, "chunks": len(meta), "items": meta}, f, ensure_ascii=False, indent=2)

    logger.info(f"[FS] UNALLOC 추출 완료: chunks={len(meta)}, bytes={total_bytes}")
    return {"ok": True, "chunks": len(meta), "bytes": total_bytes, "meta": meta_path}

def dump_fs_unallocated_single(fs_info, out_dir):
    """파티션 테이블이 없는 '단일 FS' 이미지에서 UNALLOC 블록 덤프."""
    fs_out = os.path.join(out_dir, "fs_unalloc")
    os.makedirs(fs_out, exist_ok=True)

    block_size = int(getattr(fs_info.info, "block_size", 0)) or 4096
    block_last = int(getattr(fs_info.info, "block_count", 0)) - 1
    flags = pytsk3.TSK_FS_BLOCK_FLAG_UNALLOC

    meta = []
    total_bytes = 0
    idx = 1

    def flush_span(start_blk, end_blk):
        nonlocal idx, total_bytes
        if start_blk is None or end_blk is None or end_blk < start_blk:
            return
        blk_cnt = (end_blk - start_blk + 1)
        byte_off_in_fs = start_blk * block_size
        byte_len = blk_cnt * block_size
        try:
            data = fs_info.read_random(byte_off_in_fs, byte_len)
        except Exception as e:
            logger.warning(f"[FS(single)] read_random 실패 off={byte_off_in_fs} len={byte_len}: {e}")
            return
        out_path = os.path.join(fs_out, f"{idx:03d}.bin")
        with open(out_path, "wb") as f:
            f.write(data)
        total_bytes += len(data)
        meta.append({
            "index": idx,
            "file": out_path,
            "fs_block_start": int(start_blk),
            "fs_block_end": int(end_blk),
            "fs_block_size": block_size,
            "byte_len": len(data),
        })
        idx += 1

    span_start = None
    prev = None
    try:
        for blk in fs_info.block_walk(0, block_last, flags):
            baddr = int(blk.addr)
            if span_start is None:
                span_start = prev = baddr
            elif baddr == prev + 1:
                prev = baddr
            else:
                flush_span(span_start, prev)
                span_start, prev = baddr, baddr
        flush_span(span_start, prev)
    except Exception as e:
        logger.warning(f"[FS(single)] block_walk 실패: {e}")

    meta_path = os.path.join(fs_out, "fs_unalloc.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"block_size": block_size, "chunks": len(meta), "items": meta}, f, ensure_ascii=False, indent=2)

