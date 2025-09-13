import os
import json
import struct
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
import mmap

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

def _open_mmap(path: str):
    f = open(path, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    return f, mm

def _find_all_mm(mm: mmap.mmap, needle: bytes):
    i, L = 0, len(needle)
    while True:
        i = mm.find(needle, i)
        if i == -1:
            return
        yield i
        i += len(needle)


# -----------------------------
# ffmpeg / ffprobe 경로
# -----------------------------
def _search_bin_upwards(start_dir: str) -> Optional[str]:
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

# 1) 환경변수 지원 + 명시 로그 + 실패시 이벤트
def _bin_dir() -> str:
    # 우선순위: 환경변수 → 상향탐색
    env = os.environ.get("VIREX_FFMPEG_DIR")
    if env and os.path.isfile(os.path.join(env, "ffmpeg.exe")) and os.path.isfile(os.path.join(env, "ffprobe.exe")):
        return env
    here = os.path.dirname(__file__)
    found = _search_bin_upwards(here)
    return found or ""

def _ffmpeg_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffmpeg.exe") if b else ""
    if not p or not os.path.isfile(p):
        logger.error("[ffmpeg] not found (set VIREX_FFMPEG_DIR or place bin/ffmpeg.exe)")
        # 콘솔 이벤트로도 찍어두면 메인에서 사용자 경고 가능
        print(json.dumps({"event":"ffmpeg_missing"}), flush=True)
        return "ffmpeg"  # 그대로 두되 상위에서 실패시 원인 떠주게
    return p

def _ffprobe_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffprobe.exe") if b else ""
    if not p or not os.path.isfile(p):
        logger.error("[ffprobe] not found (set VIREX_FFMPEG_DIR or place bin/ffprobe.exe)")
        print(json.dumps({"event":"ffprobe_missing"}), flush=True)
        return "ffprobe"
    return p


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
# 1) AVI carving
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
# 2) MP4 carving
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
    f, mm = _open_mmap(bin_path)
    try:
        count = 0
        N = len(mm)

        def _read_mp4_box_mm(off: int):
            if off + 8 > N: return None, None, None
            size = struct.unpack(">I", mm[off:off+4])[0]
            typ  = mm[off+4:off+8]
            if size == 0: return None, None, None
            if size == 1:
                if off + 16 > N: return None, None, None
                box_size = struct.unpack(">Q", mm[off+8:off+16])[0]
                header = 16
            else:
                box_size = size
                header = 8
            if box_size < header or off + box_size > N: return None, None, None
            try: box_type = typ.decode("ascii")
            except: box_type = "????"
            return box_type, box_size, off + box_size

        for ftyp_idx in _find_all_mm(mm, b"ftyp"):
            if count >= max_files: break
            box_start = ftyp_idx - 4
            if box_start < 0 or box_start + 8 > N: continue
            sz = struct.unpack(">I", mm[box_start:box_start+4])[0]
            typ = mm[box_start+4:box_start+8]
            if typ != b"ftyp" or sz < 8: continue

            cur = box_start
            last_good_end = None
            total = 0
            saw_moov = False
            saw_mdat = False

            while True:
                btype, bsize, nxt = _read_mp4_box_mm(cur)
                if not btype: break
                total += bsize
                if btype == "moov": saw_moov = True
                if btype == "mdat": saw_mdat = True
                if total > max_total_len:
                    last_good_end = cur + bsize
                    break
                last_good_end = cur + bsize
                cur = nxt

            # 최소 조건: ftyp + (moov 또는 mdat 중 하나는 반드시)
            if not last_good_end or last_good_end <= box_start: 
                continue
            if not (saw_moov or saw_mdat):
                continue

            count += 1
            out_name = os.path.join(out_dir, f"carved_{count:04d}.mp4")
            with open(out_name, "wb") as wf:
                wf.write(mm[box_start:last_good_end])
            out.append({"offset": box_start, "length": last_good_end - box_start, "path": out_name})
    finally:
        mm.close(); f.close()
    return out


# -----------------------------
# 3) JDR carving (AnnexB)
# -----------------------------
START3 = b"\x00\x00\x01"
START4 = b"\x00\x00\x00\x01"

def _iter_startcodes(buf: bytes):
    i, L = 0, len(buf)
    while i < L-3:
        if buf[i:i+4] == START4:
            yield i; i += 4
        elif buf[i:i+3] == START3:
            yield i; i += 3
        else:
            i += 1

def _h264_type(b0: int) -> int: return b0 & 0x1F
def _h265_type(b0: int, b1: int) -> int: return (b0 & 0x7E) >> 1

def _sniff_codec(buf: bytes) -> str:
    la = buf[:2_000_000]
    for off in _iter_startcodes(la):
        sc = 4 if la[off:off+4] == START4 else 3
        if off+sc >= len(la): continue
        b0 = la[off+sc]; b1 = la[off+sc+1] if off+sc+1 < len(la) else 0
        if _h264_type(b0) in (5,7,8): return "h264"
        if _h265_type(b0,b1) in (19,20,32,33,34): return "h265"
    return "unknown"

def _carve_annexb_segments(buf: bytes, min_bytes: int = 200_000):
    starts = list(_iter_startcodes(buf))
    if not starts: return []
    segs, cur_start = [], None
    seen_sps, seen_pps = False, False
    for i, off in enumerate(starts):
        nxt = starts[i+1] if i+1 < len(starts) else len(buf)
        sc = 4 if buf[off:off+4] == START4 else 3
        b0 = buf[off+sc] if off+sc < len(buf) else 0
        b1 = buf[off+sc+1] if off+sc+1 < len(buf) else 0
        is_idr = (_h264_type(b0) == 5) or (_h265_type(b0,b1) in (19,20))
        is_sps = (_h264_type(b0) == 7) or (_h265_type(b0,b1) in (32,33))
        is_pps = (_h264_type(b0) == 8) or (_h265_type(b0,b1) == 34)
        if is_sps: seen_sps = True
        if is_pps: seen_pps = True
        if is_idr and seen_sps and seen_pps:
            if cur_start is not None and (off - cur_start) >= min_bytes:
                segs.append((cur_start, off))
            cur_start, seen_sps, seen_pps = off, False, False
    if cur_start is not None and (len(buf) - cur_start) >= min_bytes:
        segs.append((cur_start, len(buf)))
    return segs

def _remux_es_to_mp4(es_path: str, codec: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(es_path))[0]
    out_path = os.path.join(out_dir, f"{stem}.mp4")
    fmt = "h264" if codec=="h264" else "hevc"
    cmd = [_ffmpeg_path(), "-y", "-loglevel", "warning",
           "-f", fmt, "-i", es_path,
           "-c", "copy", "-movflags", "+faststart", out_path]
    code, out, err = _run(cmd)
    if code != 0 or not os.path.isfile(out_path):
        logger.warning("ES remux failed: %s", err.strip())
        return None
    return out_path

def carve_jdr_from_bin(bin_path: str, out_dir: Optional[str] = None, max_segments: int = 1000) -> List[Dict]:
    out: List[Dict] = []
    out_dir = _ensure_outdir(bin_path, out_dir)
    fixed_dir = _ensure_sibling_dir(bin_path, "carved_fixed")
    f, mm = _open_mmap(bin_path)
    try:
        buf = mm  # mmap은 bytes-like
        codec = _sniff_codec(bytes(buf[:2_000_000]))  # sniff만 일부 복사
        if codec not in ("h264","h265"): return out
        segs = _carve_annexb_segments(bytes(buf))     # 필요시 청크 기반으로 개선 가능
        for i,(s,e) in enumerate(segs[:max_segments]):
            es_ext = ".h264" if codec=="h264" else ".h265"
            es_path = os.path.join(out_dir, f"jdr_seg_{i:04d}{es_ext}")
            with open(es_path,"wb") as wf: wf.write(buf[s:e])
            mp4_path = _remux_es_to_mp4(es_path, codec, fixed_dir)
            out.append({"offset":s,"length":e-s,"es":es_path,"rebuilt":mp4_path,
                        "ok": mp4_path is not None,"codec":codec})
    finally:
        mm.close(); f.close()
    return out


# -----------------------------
# 4) Remux/fix
# -----------------------------
def remux_avi_to_mp4(input_path: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, f"{stem}.mp4")
    cmd = [_ffmpeg_path(), "-y","-loglevel","warning",
           "-analyzeduration","2147483647","-probesize","2147483647",
           "-fflags","+genpts","-i",input_path,
           "-c:v","copy","-c:a","copy","-movflags","+faststart",out_path]
    code, out, err = _run(cmd)
    if code!=0 or not os.path.isfile(out_path): return None
    return out_path

def fix_or_remux_mp4(input_path: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_fixed.mp4")
    cmd = [_ffmpeg_path(), "-y","-loglevel","warning",
           "-analyzeduration","2147483647","-probesize","2147483647",
           "-err_detect","ignore_err","-fflags","+genpts",
           "-i",input_path,"-c:v","copy","-c:a","copy",
           "-movflags","+faststart",out_path]
    code, out, err = _run(cmd)
    if code!=0 or not os.path.isfile(out_path): return None
    return out_path if ffprobe_json(out_path) else None

def rebuild_carved_videos(bin_path: str, carved_list: List[Dict]) -> List[Dict]:
    fixed_dir = _ensure_sibling_dir(bin_path, "carved_fixed")
    results: List[Dict] = []
    for item in carved_list:
        raw_path = item.get("path")
        if not raw_path or not os.path.isfile(raw_path): continue
        ext = os.path.splitext(raw_path)[1].lower()
        rebuilt = remux_avi_to_mp4(raw_path,fixed_dir) if ext==".avi" else \
            fix_or_remux_mp4(raw_path,fixed_dir) if ext==".mp4" else None
        probe = ffprobe_json(rebuilt) if rebuilt and os.path.isfile(rebuilt) else None
        results.append({"offset":item.get("offset"),"length":item.get("length"),
                        "raw":raw_path,"rebuilt":rebuilt,
                        "ok":rebuilt is not None and probe is not None,"probe":probe})
    return results

# -----------------------------
# 5) Auto pipeline
# -----------------------------
def auto_carve_and_rebuild_from_vol_slack(vol_slack_dir: str, max_files_per_bin: int = 1000) -> Dict:
    meta_path = os.path.join(vol_slack_dir, "volume_slack.json")
    if not os.path.isfile(meta_path):
        return {"ok":False,"reason":"no_volume_slack_json","dir":vol_slack_dir}
    with open(meta_path,"r",encoding="utf-8") as rf:
        meta = json.load(rf)

    entries = meta.get("entries", [])
    if not entries:
        return {"ok":True,"entries":0,"carved_total":0,"rebuilt_total":0,"items":[]}

    root = os.path.dirname(vol_slack_dir)
    carved_dir = os.path.join(root,"carved")
    fixed_dir  = os.path.join(root,"carved_fixed")
    os.makedirs(carved_dir,exist_ok=True)
    os.makedirs(fixed_dir, exist_ok=True)

    items, carved_total, rebuilt_total = [], 0, 0
    for ent in entries:
        bin_path = ent.get("file")
        if not bin_path or not os.path.isfile(bin_path): continue

        avi_carved = carve_avi_from_bin(bin_path,out_dir=carved_dir,max_files=max_files_per_bin)
        mp4_carved = carve_mp4_from_bin(bin_path,out_dir=carved_dir,max_files=max_files_per_bin)
        jdr_carved = carve_jdr_from_bin(bin_path,out_dir=carved_dir,max_segments=max_files_per_bin)

        carved_all = avi_carved + mp4_carved
        carved_total += len(carved_all) + len(jdr_carved)

        rebuilt = rebuild_carved_videos(bin_path, carved_all)
        rebuilt_ok = sum(1 for x in rebuilt if x.get("ok")) + sum(1 for x in jdr_carved if x.get("ok"))
        rebuilt_total += rebuilt_ok

        items.append({
            "entry_index": ent.get("index"),
            "entry_type": ent.get("type"),
            "bin": bin_path,
            "carved_count": len(carved_all)+len(jdr_carved),
            "rebuilt_ok": rebuilt_ok,
            "rebuilt": rebuilt,
            "jdr": jdr_carved,
        })

    if carved_total==0:
        print(json.dumps({"event":"carve_none","dir":vol_slack_dir,
                          "message":"No AVI/MP4/JDR signatures found"}), flush=True)

    summary = {"ok":True,
               "image_path":meta.get("image_path"),
               "media_size":meta.get("media_size"),
               "sector_size":meta.get("sector_size"),
               "entries":len(entries),
               "carved_total":carved_total,
               "rebuilt_total":rebuilt_total,
               "outputs":{"carved_dir":carved_dir,"fixed_dir":fixed_dir},
               "items":items}

    index_path = os.path.join(root,"carved_index.json")
    with open(index_path, "w", encoding="utf-8") as wf:
        json.dump(summary, wf, ensure_ascii=False, indent=2)

    return summary
