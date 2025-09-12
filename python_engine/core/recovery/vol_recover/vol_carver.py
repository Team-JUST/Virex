import os
import json
import struct
import subprocess
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# -----------------------------
# 경로/폴더 유틸
# -----------------------------
def _ensure_outdir(bin_path: str, out_dir: Optional[str]) -> str:
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return out_dir
    base = os.path.dirname(bin_path)     # ...\vol_slack
    root = os.path.dirname(base)         # ...\Virex_xxxx
    out_dir = os.path.join(root, "carved")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def _ensure_sibling_dir(bin_path: str, name: str) -> str:
    base = os.path.dirname(bin_path)
    root = os.path.dirname(base)
    out_dir = os.path.join(root, name)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def _find_all(data: bytes, needle: bytes):
    i = 0
    L = len(needle)
    while True:
        i = data.find(needle, i)
        if i == -1:
            return
        yield i
        i += L

# -----------------------------
# ffmpeg / ffprobe 경로
# -----------------------------
def _search_bin_upwards(start_dir: str) -> Optional[str]:
    """
    core/ 에서 시작해 상위로 올라가며 bin/ffmpeg.exe 있는 bin 경로를 찾음.
    """
    cur = os.path.abspath(start_dir)
    for _ in range(6):
        cand = os.path.join(cur, "bin")
        if os.path.isfile(os.path.join(cand, "ffmpeg.exe")) and os.path.isfile(os.path.join(cand, "ffprobe.exe")):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None

def _bin_dir() -> str:
    here = os.path.dirname(__file__)  # .../python_engine/core
    found = _search_bin_upwards(here)
    return found if found else ""

def _ffmpeg_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffmpeg.exe") if b else ""
    return p if p and os.path.isfile(p) else "ffmpeg"

def _ffprobe_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffprobe.exe") if b else ""
    return p if p and os.path.isfile(p) else "ffprobe"

def _run(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out, err

def ffprobe_json(path: str) -> Optional[Dict]:
    cmd = [
        _ffprobe_path(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path
    ]
    code, out, err = _run(cmd)
    if code != 0:
        logger.debug("ffprobe failed for %s: %s", path, err.strip())
        return None
    try:
        return json.loads(out)
    except Exception:
        return None

# -----------------------------
# 1) AVI 카빙
# -----------------------------
def carve_avi_from_bin(bin_path: str, out_dir: Optional[str] = None, max_files: int = 1000) -> List[Dict]:
    out: List[Dict] = []
    out_dir = _ensure_outdir(bin_path, out_dir)

    with open(bin_path, "rb") as f:
        data = f.read()

    count = 0
    for idx in _find_all(data, b"RIFF"):
        if count >= max_files:
            break
        if idx + 12 > len(data):
            continue
        size = struct.unpack("<I", data[idx+4:idx+8])[0]
        form = data[idx+8:idx+12]
        if form != b"AVI ":
            continue

        total_len = 8 + size
        end = idx + total_len
        if total_len <= 0 or end > len(data):
            logger.debug("Truncated AVI at %d (declared=%d)", idx, total_len)
            continue

        count += 1
        out_name = os.path.join(out_dir, f"carved_{count:04d}.avi")
        with open(out_name, "wb") as wf:
            wf.write(data[idx:end])
        out.append({"offset": idx, "length": total_len, "path": out_name})
    return out

# -----------------------------
# 2) MP4 카빙
# -----------------------------
def _read_mp4_box(data: bytes, off: int):
    if off + 8 > len(data):
        return None, None, None
    size = struct.unpack(">I", data[off:off+4])[0]
    typ = data[off+4:off+8]

    if size == 0:
        return None, None, None

    if size == 1:
        if off + 16 > len(data):
            return None, None, None
        largesize = struct.unpack(">Q", data[off+8:off+16])[0]
        box_size = largesize
        header = 16
    else:
        box_size = size
        header = 8

    if box_size < header:
        return None, None, None
    if off + box_size > len(data):
        return None, None, None

    try:
        box_type = typ.decode("ascii")
    except Exception:
        box_type = "????"
    return box_type, box_size, off + box_size

def carve_mp4_from_bin(bin_path: str,
                       out_dir: Optional[str] = None,
                       max_files: int = 1000,
                       max_total_len: int = 1_500_000_000) -> List[Dict]:
    out: List[Dict] = []
    out_dir = _ensure_outdir(bin_path, out_dir)

    with open(bin_path, "rb") as f:
        data = f.read()

    count = 0
    for ftyp_idx in _find_all(data, b"ftyp"):
        if count >= max_files:
            break
        box_start = ftyp_idx - 4
        if box_start < 0 or box_start + 8 > len(data):
            continue
        sz = struct.unpack(">I", data[box_start:box_start+4])[0]
        typ = data[box_start+4:box_start+8]
        if typ != b"ftyp" or sz < 8:
            continue

        cur = box_start
        last_good_end = None
        total = 0
        while True:
            btype, bsize, nxt = _read_mp4_box(data, cur)
            if not btype:
                break
            total += bsize
            if total > max_total_len:
                last_good_end = cur + bsize
                break
            last_good_end = cur + bsize
            cur = nxt

        if not last_good_end or last_good_end <= box_start:
            continue

        count += 1
        out_name = os.path.join(out_dir, f"carved_{count:04d}.mp4")
        with open(out_name, "wb") as wf:
            wf.write(data[box_start:last_good_end])
        out.append({"offset": box_start, "length": last_good_end - box_start, "path": out_name})
    return out

# -----------------------------
# 3) 재조립 (ffmpeg)
# -----------------------------
def remux_avi_to_mp4(input_path: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, f"{stem}.mp4")
    cmd = [
        _ffmpeg_path(), "-y", "-loglevel", "warning",
        "-analyzeduration", "2147483647",
        "-probesize", "2147483647",
        "-fflags", "+genpts",
        "-i", input_path,
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        out_path
    ]
    code, out, err = _run(cmd)
    if code != 0 or not os.path.isfile(out_path):
        logger.warning("AVI remux failed: %s", err.strip())
        return None
    return out_path

def fix_or_remux_mp4(input_path: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_fixed.mp4")
    cmd = [
        _ffmpeg_path(), "-y", "-loglevel", "warning",
        "-analyzeduration", "2147483647",
        "-probesize", "2147483647",
        "-err_detect", "ignore_err",
        "-fflags", "+genpts",
        "-i", input_path,
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        out_path
    ]
    code, out, err = _run(cmd)
    if code != 0 or not os.path.isfile(out_path):
        logger.warning("MP4 remux failed: %s", err.strip())
        return None
    # 간단 검증
    _ = ffprobe_json(out_path)
    return out_path

def rebuild_carved_videos(bin_path: str, carved_list: List[Dict]) -> List[Dict]:
    fixed_dir = _ensure_sibling_dir(bin_path, "carved_fixed")
    results: List[Dict] = []
    for item in carved_list:
        raw_path = item.get("path")
        if not raw_path or not os.path.isfile(raw_path):
            continue
        ext = os.path.splitext(raw_path)[1].lower()
        rebuilt = None
        if ext == ".avi":
            rebuilt = remux_avi_to_mp4(raw_path, fixed_dir)
        elif ext == ".mp4":
            rebuilt = fix_or_remux_mp4(raw_path, fixed_dir)
        probe = ffprobe_json(rebuilt) if rebuilt and os.path.isfile(rebuilt) else None
        results.append({
            "offset": item.get("offset"),
            "length": item.get("length"),
            "raw": raw_path,
            "rebuilt": rebuilt,
            "ok": rebuilt is not None and probe is not None,
            "probe": probe
        })
    return results

# -----------------------------
# 4) 자동 파이프라인 (vol_slack 디렉토리 단위)
# -----------------------------
def auto_carve_and_rebuild_from_vol_slack(vol_slack_dir: str, max_files_per_gap: int = 1000) -> Dict:
    meta_path = os.path.join(vol_slack_dir, "volume_slack.json")
    if not os.path.isfile(meta_path):
        return {"ok": False, "reason": "no_volume_slack_json", "dir": vol_slack_dir}

    with open(meta_path, "r", encoding="utf-8") as rf:
        meta = json.load(rf)

    gaps = meta.get("gaps", [])
    if not gaps:
        return {"ok": True, "gaps": 0, "carved_total": 0, "rebuilt_total": 0, "items": []}

    root = os.path.dirname(vol_slack_dir)
    carved_dir = os.path.join(root, "carved")
    fixed_dir  = os.path.join(root, "carved_fixed")
    os.makedirs(carved_dir, exist_ok=True)
    os.makedirs(fixed_dir,  exist_ok=True)

    items: List[Dict] = []
    carved_total = 0
    rebuilt_total = 0

    for g in gaps:
        bin_path = g.get("file")
        if not bin_path or not os.path.isfile(bin_path):
            continue

        avi_carved = carve_avi_from_bin(bin_path, out_dir=carved_dir, max_files=max_files_per_gap)
        mp4_carved = carve_mp4_from_bin(bin_path, out_dir=carved_dir, max_files=max_files_per_gap)
        carved_all = avi_carved + mp4_carved
        carved_total += len(carved_all)

        rebuilt = rebuild_carved_videos(bin_path, carved_all)
        rebuilt_ok = sum(1 for x in rebuilt if x.get("ok"))
        rebuilt_total += rebuilt_ok

        items.append({
            "gap_index": g.get("index"),
            "gap_offset": g.get("offset"),
            "gap_length": g.get("length"),
            "bin": bin_path,
            "carved_count": len(carved_all),
            "rebuilt_ok": rebuilt_ok,
            "rebuilt": rebuilt,
        })

    summary = {
        "ok": True,
        "image_path": meta.get("image_path"),
        "media_size": meta.get("media_size"),
        "sector_size": meta.get("sector_size"),
        "gaps": len(gaps),
        "carved_total": carved_total,
        "rebuilt_total": rebuilt_total,
        "outputs": {"carved_dir": carved_dir, "fixed_dir": fixed_dir},
        "items": items,
    }

    index_path = os.path.join(root, "carved_index.json")
    with open(index_path, "w", encoding="utf-8") as wf:
        json.dump(summary, wf, ensure_ascii=False, indent=2)

        summary = {
        "ok": True,
        "image_path": meta.get("image_path"),
        "media_size": meta.get("media_size"),
        "sector_size": meta.get("sector_size"),
        "gaps": len(gaps),
        "carved_total": carved_total,
        "rebuilt_total": rebuilt_total,
        "outputs": {"carved_dir": carved_dir, "fixed_dir": fixed_dir},
        "items": items,
    }

    if carved_total == 0:
        print(json.dumps({
            "event": "carve_none",
            "dir": vol_slack_dir,
            "gaps": len(gaps),
            "message": "No AVI/MP4 signature found in slack bins"
        }), flush=True)

    index_path = os.path.join(root, "carved_index.json")
    with open(index_path, "w", encoding="utf-8") as wf:
        json.dump(summary, wf, ensure_ascii=False, indent=2)

    return summary