# vol_carver.py
import os
import json
import struct
import subprocess
import logging
import mmap
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =========================================================
# 공통 유틸
# =========================================================
def _ensure_outdir(bin_path: str, out_dir: Optional[str]) -> str:
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return out_dir
    base = os.path.dirname(bin_path)
    root = os.path.dirname(base)
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
    i, L = 0, len(needle)
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
        i += L

# =========================================================
# ffmpeg / ffprobe 경로
# =========================================================
def _search_bin_upwards(start_dir: str) -> Optional[str]:
    cur = os.path.abspath(start_dir)
    for _ in range(6):
        cand = os.path.join(cur, "bin")
        if (os.path.isfile(os.path.join(cand, "ffmpeg.exe")) and
            os.path.isfile(os.path.join(cand, "ffprobe.exe"))):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur: break
        cur = parent
    return None

def _bin_dir() -> str:
    env = os.environ.get("VIREX_FFMPEG_DIR")
    if env and os.path.isfile(os.path.join(env, "ffmpeg.exe")):
        return env
    here = os.path.dirname(__file__)
    found = _search_bin_upwards(here)
    return found or ""

def _ffmpeg_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffmpeg.exe") if b else ""
    return p if os.path.isfile(p) else "ffmpeg"

def _ffprobe_path() -> str:
    b = _bin_dir()
    p = os.path.join(b, "ffprobe.exe") if b else ""
    return p if os.path.isfile(p) else "ffprobe"

def _run(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out, err

def ffprobe_json(path: str) -> Optional[Dict]:
    cmd = [_ffprobe_path(), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    code, out, err = _run(cmd)
    if code != 0: return None
    try: return json.loads(out)
    except: return None

# =========================================================
# AVI 카버
# =========================================================
def carve_avi_from_bin(bin_path: str, out_dir: Optional[str] = None,
                       max_files: int = 1000) -> List[Dict]:
    out, out_dir = [], _ensure_outdir(bin_path, out_dir)
    data = open(bin_path, "rb").read()
    count = 0
    for idx in _find_all(data, b"RIFF"):
        if count >= max_files or idx + 12 > len(data): continue
        size = struct.unpack("<I", data[idx+4:idx+8])[0]
        if data[idx+8:idx+12] != b"AVI ": continue
        total_len = 8 + size
        if total_len <= 0 or idx + total_len > len(data): continue
        count += 1
        out_name = os.path.join(out_dir, f"carved_{count:04d}.avi")
        with open(out_name, "wb") as wf: wf.write(data[idx:idx+total_len])
        out.append({"offset": idx, "length": total_len, "path": out_name})
    return out

# =========================================================
# MP4 카버
# =========================================================
def carve_mp4_from_bin(bin_path: str, out_dir: Optional[str] = None,
                       max_files: int = 1000,
                       max_total_len: int = 1_500_000_000) -> List[Dict]:
    out, out_dir = [], _ensure_outdir(bin_path, out_dir)
    f, mm = _open_mmap(bin_path)
    try:
        N, count = len(mm), 0
        def _read_box(off: int):
            if off+8 > N: return None, None, None
            size = struct.unpack(">I", mm[off:off+4])[0]
            typ = mm[off+4:off+8]
            if size < 8: return None, None, None
            end = off + size
            if end > N: return None, None, None
            try: t = typ.decode("ascii")
            except: t = "????"
            return t, size, end

        for ftyp_idx in _find_all_mm(mm, b"ftyp"):
            if count >= max_files: break
            box_start = ftyp_idx - 4
            if box_start < 0: continue
            sz = struct.unpack(">I", mm[box_start:box_start+4])[0]
            if mm[box_start+4:box_start+8] != b"ftyp": continue

            cur, total, last_end, saw_moov, saw_mdat = box_start, 0, None, False, False
            while True:
                btype, bsize, nxt = _read_box(cur)
                if not btype: break
                total += bsize
                if btype == "moov": saw_moov = True
                if btype == "mdat": saw_mdat = True
                if total > max_total_len: break
                last_end = nxt; cur = nxt

            if not last_end or not (saw_moov or saw_mdat): continue
            count += 1
            out_name = os.path.join(out_dir, f"carved_{count:04d}.mp4")
            with open(out_name, "wb") as wf: wf.write(mm[box_start:last_end])
            out.append({"offset": box_start, "length": last_end-box_start, "path": out_name})
    finally:
        mm.close(); f.close()
    return out

# =========================================================
# JDR(H.264/H.265 ES) 카버
# =========================================================
START3, START4 = b"\x00\x00\x01", b"\x00\x00\x00\x01"

def _iter_startcodes(buf: bytes):
    i = 0
    while i < len(buf)-3:
        if buf[i:i+4] == START4: yield i; i+=4
        elif buf[i:i+3] == START3: yield i; i+=3
        else: i+=1

def _h264_type(b0): return b0 & 0x1F
def _h265_type(b0,b1): return (b0 & 0x7E)>>1

def _sniff_codec(buf: bytes) -> str:
    for off in _iter_startcodes(buf[:2_000_000]):
        sc = 4 if buf[off:off+4]==START4 else 3
        if off+sc >= len(buf): continue
        b0, b1 = buf[off+sc], buf[off+sc+1] if off+sc+1<len(buf) else 0
        if _h264_type(b0) in (5,7,8): return "h264"
        if _h265_type(b0,b1) in (19,20,32,33,34): return "h265"
    return "unknown"

def _carve_annexb_segments(buf: bytes, min_bytes=200_000):
    segs, cur = [], None
    seen_sps=seen_pps=False
    for off in _iter_startcodes(buf):
        sc = 4 if buf[off:off+4]==START4 else 3
        b0, b1 = buf[off+sc], buf[off+sc+1] if off+sc+1<len(buf) else 0
        is_idr = (_h264_type(b0)==5) or (_h265_type(b0,b1) in (19,20))
        is_sps = (_h264_type(b0)==7) or (_h265_type(b0,b1) in (32,33))
        is_pps = (_h264_type(b0)==8) or (_h265_type(b0,b1)==34)
        if is_sps: seen_sps=True
        if is_pps: seen_pps=True
        if is_idr and seen_sps and seen_pps:
            if cur is not None and off-cur>=min_bytes: segs.append((cur,off))
            cur, seen_sps, seen_pps = off, False, False
    if cur is not None and len(buf)-cur>=min_bytes: segs.append((cur,len(buf)))
    return segs

def _remux_es_to_mp4(es_path, codec, out_dir):
    stem=os.path.splitext(os.path.basename(es_path))[0]
    out_path=os.path.join(out_dir,f"{stem}.mp4")
    fmt="h264" if codec=="h264" else "hevc"
    cmd=[_ffmpeg_path(),"-y","-loglevel","warning","-f",fmt,"-i",es_path,
         "-c","copy","-movflags","+faststart",out_path]
    code,_,_= _run(cmd)
    return out_path if code==0 and os.path.isfile(out_path) else None

def carve_jdr_from_bin(bin_path, out_dir=None, max_segments=1000):
    out, out_dir = [], _ensure_outdir(bin_path,out_dir)
    fixed_dir=_ensure_sibling_dir(bin_path,"carved_fixed")
    f,mm=_open_mmap(bin_path)
    try:
        codec=_sniff_codec(bytes(mm[:2_000_000]))
        if codec not in ("h264","h265"): return out
        segs=_carve_annexb_segments(bytes(mm))
        for i,(s,e) in enumerate(segs[:max_segments]):
            es_ext=".h264" if codec=="h264" else ".h265"
            es_path=os.path.join(out_dir,f"jdr_seg_{i:04d}{es_ext}")
            with open(es_path,"wb") as wf: wf.write(mm[s:e])
            mp4_path=_remux_es_to_mp4(es_path,codec,fixed_dir)
            out.append({"offset":s,"length":e-s,"es":es_path,
                        "rebuilt":mp4_path,"ok":mp4_path is not None,
                        "codec":codec})
    finally:
        mm.close();f.close()
    return out

# =========================================================
# Remux/Fix
# =========================================================
def remux_avi_to_mp4(input_path,out_dir):
    stem=os.path.splitext(os.path.basename(input_path))[0]
    out_path=os.path.join(out_dir,f"{stem}.mp4")
    cmd=[_ffmpeg_path(),"-y","-loglevel","warning","-i",input_path,
         "-c:v","copy","-c:a","copy","-movflags","+faststart",out_path]
    code,_,_= _run(cmd)
    return out_path if code==0 and os.path.isfile(out_path) else None

def fix_or_remux_mp4(input_path,out_dir):
    stem=os.path.splitext(os.path.basename(input_path))[0]
    out_path=os.path.join(out_dir,f"{stem}_fixed.mp4")
    cmd=[_ffmpeg_path(),"-y","-loglevel","warning","-err_detect","ignore_err",
         "-fflags","+genpts","-i",input_path,
         "-c:v","copy","-c:a","copy","-movflags","+faststart",out_path]
    code,_,_= _run(cmd)
    return out_path if code==0 and os.path.isfile(out_path) else None

def rebuild_carved_videos(bin_path,carved_list):
    fixed_dir=_ensure_sibling_dir(bin_path,"carved_fixed")
    results=[]
    for item in carved_list:
        raw=item.get("path")
        if not raw or not os.path.isfile(raw): continue
        ext=os.path.splitext(raw)[1].lower()
        rebuilt = remux_avi_to_mp4(raw,fixed_dir) if ext==".avi" else \
                  fix_or_remux_mp4(raw,fixed_dir) if ext==".mp4" else None
        probe=ffprobe_json(rebuilt) if rebuilt else None
        results.append({"offset":item.get("offset"),"length":item.get("length"),
                        "raw":raw,"rebuilt":rebuilt,
                        "ok":rebuilt is not None and probe is not None})
    return results

# =========================================================
# Auto pipelines
# =========================================================
def auto_carve_from_dir(bin_dir: str, max_files_per_bin=1000) -> Dict:
    items, carved_total, rebuilt_total = [],0,0
    root=os.path.dirname(bin_dir)
    carved_dir, fixed_dir = os.path.join(root,"carved"), os.path.join(root,"carved_fixed")
    os.makedirs(carved_dir,exist_ok=True); os.makedirs(fixed_dir,exist_ok=True)

    bin_list=[]
    meta_path=os.path.join(bin_dir,"volume_slack.json")
    if os.path.isfile(meta_path):
        meta=json.load(open(meta_path,"r",encoding="utf-8"))
        entries=meta.get("entries",[])
        bin_list=[ent["file"] for ent in entries if os.path.isfile(ent.get("file",""))]
    else:
        for n in sorted(os.listdir(bin_dir)):
            if n.lower().endswith(".bin"): bin_list.append(os.path.join(bin_dir,n))

    for i,bin_path in enumerate(bin_list):
        avi=carve_avi_from_bin(bin_path,carved_dir,max_files_per_bin)
        mp4=carve_mp4_from_bin(bin_path,carved_dir,max_files_per_bin)
        jdr=carve_jdr_from_bin(bin_path,carved_dir,max_files_per_bin)
        carved_all=avi+mp4
        carved_total+=len(carved_all)+len(jdr)
        rebuilt=rebuild_carved_videos(bin_path,carved_all)
        rebuilt_ok=sum(1 for x in rebuilt if x["ok"])+sum(1 for x in jdr if x["ok"])
        rebuilt_total+=rebuilt_ok
        items.append({"bin_index":i,"bin":bin_path,
                      "carved_count":len(carved_all)+len(jdr),
                      "rebuilt_ok":rebuilt_ok,
                      "rebuilt":rebuilt,"jdr":jdr})

    return {"ok":True,"inputs":len(bin_list),
            "carved_total":carved_total,"rebuilt_total":rebuilt_total,
            "outputs":{"carved_dir":carved_dir,"fixed_dir":fixed_dir},
            "items":items}

# =========================================================
# Folder walker
# =========================================================
def _dir_is_carvable(d: str) -> bool:
    if not os.path.isdir(d): return False
    if os.path.isfile(os.path.join(d, "volume_slack.json")):
        return True
    for n in os.listdir(d):
        if n.lower().endswith(".bin"):
            return True
    return False

def carve_everything(base_dir: str,
                     max_files_per_bin: int = 1000,
                     ffmpeg_dir_override: Optional[str] = None) -> Dict:
    if ffmpeg_dir_override:
        os.environ["VIREX_FFMPEG_DIR"] = ffmpeg_dir_override

    base_dir = os.path.abspath(base_dir)
    results = {"ok": True, "base_dir": base_dir,
               "visited_dirs": 0, "targets": [],
               "summary": {"inputs": 0,"carved_total": 0,"rebuilt_total": 0}}

    for cur, dirs, files in os.walk(base_dir):
        results["visited_dirs"] += 1
        if _dir_is_carvable(cur):
            try:
                r = auto_carve_from_dir(cur, max_files_per_bin=max_files_per_bin)
                results["targets"].append(r)
                results["summary"]["inputs"] += r.get("inputs", 0)
                results["summary"]["carved_total"] += r.get("carved_total", 0)
                results["summary"]["rebuilt_total"] += r.get("rebuilt_total", 0)
            except Exception as e:
                logger.exception("auto_carve_from_dir failed on %s", cur)
                results["targets"].append({"ok": False,"dir": cur,"error": str(e)})
    return results

# =========================================================
# 실행 진입점
# =========================================================
if __name__=="__main__":
    import sys
    if len(sys.argv)<2:
        print("Usage: python vol_carver.py <base_dir> [--ffmpeg-dir <dir>]")
        sys.exit(1)

    base_dir=sys.argv[1]
    ffmpeg_dir=None
    if "--ffmpeg-dir" in sys.argv:
        i=sys.argv.index("--ffmpeg-dir")
        if i+1 < len(sys.argv): ffmpeg_dir=sys.argv[i+1]
        if ffmpeg_dir and ffmpeg_dir.lower().endswith("ffmpeg.exe"):
            ffmpeg_dir=os.path.dirname(ffmpeg_dir)

    result=carve_everything(base_dir, ffmpeg_dir_override=ffmpeg_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 인덱스 파일 저장
    index_path = os.path.join(base_dir, "carved_index.json")
    try:
        with open(index_path, "w", encoding="utf-8") as wf:
            json.dump(result, wf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(json.dumps({"error": f"write_index_failed: {e}"}))
