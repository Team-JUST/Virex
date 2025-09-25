import os
import json
import struct
import subprocess
import logging
import mmap
import sys
import shutil
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 공통 유틸
def _nonempty_file(p: Optional[str]) -> Optional[str]:
    try:
        if p and os.path.isfile(p) and os.path.getsize(p) > 0:
            return p
        if p and os.path.isfile(p):
            try: os.remove(p)
            except: pass
    except:
        pass
    return None

def _ensure_outdir(bin_path: str, out_dir: Optional[str]) -> str:
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return out_dir
    base = os.path.dirname(bin_path)
    root = os.path.dirname(base)
    carved_dir = os.path.join(root, "carved")
    os.makedirs(carved_dir, exist_ok=True)
    return carved_dir

def _open_mmap(path: str):
    f = open(path, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    return f, mm

# ffmpeg / ffprobe
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

    try:
      meipass = getattr(sys, "_MEIPASS", None)
      if meipass:
          cand = os.path.join(meipass, "bin")
          if (os.path.isfile(os.path.join(cand, "ffmpeg.exe")) and
              os.path.isfile(os.path.join(cand, "ffprobe.exe"))):
              return cand
    except Exception:
      pass

    try:
      exe_dir = os.path.dirname(sys.executable)
      cand = os.path.join(exe_dir, "bin")
      if (os.path.isfile(os.path.join(cand, "ffmpeg.exe")) and
          os.path.isfile(os.path.join(cand, "ffprobe.exe"))):
          return cand
    except Exception:
      pass

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
    code, out, _ = _run(cmd)
    if code != 0: return None
    try: return json.loads(out)
    except: return None

# AVI utils & carver (정확성 우선)
def _read_u32_le(mm, off: int, N: int | None = None):
    if N is None: N = len(mm)
    if off < 0 or off + 4 > N: return None
    return struct.unpack_from("<I", mm, off)[0]

def _read_fourcc(mm, off: int, N: int | None = None):
    if N is None: N = len(mm)
    if off < 0 or off + 4 > N: return None
    return bytes(mm[off:off+4])

def _iter_riff_avi_hits(mm):
    N = len(mm); pos = 0
    while True:
        hit = mm.find(b"RIFF", pos)
        if hit == -1: break
        if hit + 12 <= N and _read_fourcc(mm, hit+8, N) == b"AVI ":
            yield hit
        pos = hit + 1

def _find_list_chunk(mm, start: int, end: int, target: bytes):
    N = len(mm)
    if start < 0: start = 0
    if end is None or end > N: end = N
    pos = start
    while True:
        hit = mm.find(b"LIST", pos, end)
        if hit == -1 or hit + 12 > end: return (None, None)
        size = _read_u32_le(mm, hit+4, end)
        if size is None: return (None, None)
        list_type = _read_fourcc(mm, hit+8, end)
        logical_end = hit + 8 + size
        if logical_end > end:
            pos = hit + 1; continue
        if list_type == target:
            return (hit, logical_end - hit)
        pos = max(hit + 1, logical_end)

def carve_avi_from_bin(bin_path: str, out_dir: Optional[str] = None,
                        max_files: int = 1000,
                        max_total_len: int = 2_000_000_000,
                        require_movi: bool = True,
                        require_hdrl: bool = True) -> List[Dict]:
    out = []
    out_dir = _ensure_outdir(bin_path, out_dir)
    f, mm = _open_mmap(bin_path)
    try:
        N = len(mm); count = 0
        for riff_off in _iter_riff_avi_hits(mm):
            if count >= max_files: break
            if riff_off + 12 > N: continue
            riff_size = _read_u32_le(mm, riff_off+4, N)
            if riff_size is None or riff_size < 4: continue

            logical_end = riff_off + 8 + riff_size
            if logical_end > N: logical_end = N
            total_len = logical_end - riff_off
            if total_len <= 12: continue
            if total_len > max_total_len: total_len = max_total_len

            ok = True
            avi_payload_base = riff_off + 12
            avi_payload_end  = riff_off + total_len
            if require_hdrl:
                hdrl_off, _ = _find_list_chunk(mm, avi_payload_base, avi_payload_end, b"hdrl")
                if hdrl_off is None: ok = False
            if require_movi:
                movi_off, _ = _find_list_chunk(mm, avi_payload_base, avi_payload_end, b"movi")
                if movi_off is None: ok = False
            if not ok: continue

            count += 1
            out_name = os.path.join(out_dir, f"carved_fixed_{count:04d}.avi")
            with open(out_name, "wb") as wf:
                wf.write(mm[riff_off: riff_off + total_len])
            out.append({"offset": riff_off, "length": total_len, "path": out_name})

            print(json.dumps({
                "event": "carved_file",
                "kind": "avi",
                "path": out_name,
                "bytes": int(total_len)
            }), flush=True)
    finally:
        mm.close(); f.close()
    return out

# MP4 utils & carver (정확성 우선)
def _read_u32_be(mm, off: int, N: int):
    if off < 0 or off + 4 > N: return None
    return struct.unpack(">I", mm[off:off+4])[0]

def _read_u64_be(mm, off: int, N: int):
    if off < 0 or off + 8 > N: return None
    return struct.unpack(">Q", mm[off:off+8])[0]

def _iter_ftyp_hits(mm):
    N = len(mm); pos = 0
    while True:
        hit = mm.find(b"ftyp", pos)
        if hit == -1: break
        box_start = hit - 4
        if box_start >= 0 and box_start + 8 <= N:
            yield box_start
        pos = hit + 1

def _read_box_be(mm, off: int, N: int):
    if off + 8 > N: return (None, None, None)
    size = _read_u32_be(mm, off, N); typ = mm[off+4:off+8]
    if size is None: return (None, None, None)
    if size == 0:
        end = N; size = end - off
    elif size == 1:
        largesize = _read_u64_be(mm, off+8, N)
        if largesize is None or largesize < 16: return (None, None, None)
        size = int(largesize); end = off + size
    else:
        if size < 8: return (None, None, None)
        end = off + size
    if end > N: return (None, None, None)
    return (typ, size, end)

def _mp4_header_is_faststart(path: str) -> bool:
    try:
        with open(path, "rb") as rf:
            head = rf.read(4 * 1024 * 1024)
        moov = head.find(b"moov"); mdat = head.find(b"mdat")
        return (moov != -1) and (mdat == -1 or moov < mdat)
    except Exception:
        return False

def _looks_playable(path: str) -> bool:
    meta = ffprobe_json(path)
    if not meta: return False
    streams = meta.get("streams") or []
    return any(s.get("codec_type") == "video" for s in streams)

def carve_mp4_from_bin(bin_path: str, out_dir: Optional[str] = None,
                        max_files: int = 1000,
                        max_total_len: int = 1_500_000_000,
                        require_moov: bool = True,
                        allow_fragmented: bool = True) -> List[Dict]:
    out: List[Dict] = []
    out_dir = _ensure_outdir(bin_path, out_dir)
    f, mm = _open_mmap(bin_path)
    try:
        N = len(mm); count = 0
        for box_start in _iter_ftyp_hits(mm):
            if count >= max_files: break
            typ, size, end = _read_box_be(mm, box_start, N)
            if typ != b"ftyp" or size is None or size < 16: continue
            major = mm[box_start+8:box_start+12]
            if any(b < 0x20 or b > 0x7E for b in major): continue

            cur = end; last_good_end = end; total = size
            saw_moov = saw_mdat = saw_moof = False

            while cur + 8 <= N and total <= max_total_len:
                btype, bsize, nxt = _read_box_be(mm, cur, N)
                if not btype or not bsize: break
                if bsize > max_total_len: break
                if btype == b"moov": saw_moov = True
                elif btype == b"mdat": saw_mdat = True
                elif btype == b"moof": saw_moof = True
                total += bsize; last_good_end = nxt; cur = nxt
                if total > max_total_len: break

            frag_ok = (saw_moof and saw_mdat)
            ok = saw_moov and (saw_mdat or (allow_fragmented and frag_ok)) if require_moov \
                else (saw_mdat or frag_ok or saw_moov)
            if not ok or last_good_end is None: continue

            dump_end = min(last_good_end, box_start + max_total_len, N)
            if dump_end <= box_start: continue

            count += 1
            out_name = os.path.join(out_dir, f"carved_fixed_{count:04d}.mp4")
            with open(out_name, "wb") as wf:
                wf.write(mm[box_start:dump_end])

            out.append({
                "offset": box_start,
                "length": dump_end - box_start,
                "path": out_name,
                "saw_moov": saw_moov,
                "saw_mdat": saw_mdat,
                "saw_moof": saw_moof
            })

            print(json.dumps({
                "event": "carved_file",
                "kind": "mp4",
                "path": out_name,
                "bytes": int(dump_end - box_start)
            }), flush=True)
    finally:
        mm.close(); f.close()
    return out

# JDR(Annex-B H.264/H.265) ES 카버 + remux
START3, START4 = b"\x00\x00\x01", b"\x00\x00\x00\x01"

def _iter_startcodes_mm(mm) -> int:
    N = len(mm); pos = 0
    while True:
        hit = mm.find(START3, pos)
        if hit == -1: return
        sc_off = hit - 1 if hit > 0 and mm[hit-1] == 0x00 else hit
        yield (sc_off + 4) if (sc_off + 4 <= N and mm[sc_off:sc_off+4] == START4) else (sc_off + 3)
        pos = hit + 1

def _next_start_off_mm(mm, from_payload: int) -> int:
    N = len(mm); pos = from_payload
    while True:
        hit = mm.find(START3, pos)
        if hit == -1: return N
        sc_off = hit - 1 if hit > 0 and mm[hit-1] == 0x00 else hit
        return (sc_off + 4) if (sc_off + 4 <= N and mm[sc_off:sc_off+4] == START4) else (sc_off + 3)

def _nal_type_h264(nal_first_byte: int) -> int:
    return nal_first_byte & 0x1F

def _nal_type_hevc(b0: int, b1: int) -> int:
    return (b0 & 0x7E) >> 1

def _classify_codec(mm, nal_off: int) -> str:
    if nal_off + 2 > len(mm): return "h264"
    b0 = mm[nal_off]; b1 = mm[nal_off+1]
    nal_h265 = ((b0 & 0x80) == 0) and ((b1 & 0x07) >= 1)
    return "hevc" if nal_h265 else "h264"

def _remux_es_to_mp4(es_path: str, codec: str, out_dir: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(es_path))[0]
    out_path = os.path.join(out_dir, f"{stem}.mp4")
    fmt = "h264" if codec == "h264" else "hevc"
    cmd = [_ffmpeg_path(), "-y", "-loglevel", "warning", "-f", fmt, "-i", es_path,
            "-c", "copy", "-movflags", "+faststart", out_path]
    code, _, _ = _run(cmd)
    return _nonempty_file(out_path) if code == 0 else None

def carve_jdr_from_bin(
    bin_path: str,
    out_dir: Optional[str] = None,
    max_files: int = 2000,
    max_total_len: int = 800_000_000,
    require_pps: bool = False,
    codec: str = "auto",
) -> List[Dict]:
    out: List[Dict] = []
    carved_dir = _ensure_outdir(bin_path, out_dir)
    f, mm_raw = _open_mmap(bin_path)
    mm = memoryview(mm_raw)
    try:
        N = len(mm_raw)
        count = 0
        have_sps = False
        have_pps = False
        last_sps_off: Optional[int] = None
        last_pps_off: Optional[int] = None

        cur_start: Optional[int] = None
        cur_codec = "h264"
        idr_count = 0

        for nal_off in _iter_startcodes_mm(mm_raw):
            if count >= max_files or nal_off >= N:
                break
            next_off = _next_start_off_mm(mm_raw, nal_off + 1)
            if next_off <= nal_off or (next_off - nal_off) < 2:
                continue

            detected = codec if codec in ("h264", "hevc") else _classify_codec(mm_raw, nal_off)
            if detected == "h264":
                ntype = mm_raw[nal_off] & 0x1F
                is_sps = (ntype == 7)
                is_pps = (ntype == 8)
                is_idr = (ntype == 5)
            else:
                if nal_off + 2 > N:
                    continue
                ntype = ((mm_raw[nal_off] & 0x7E) >> 1)
                is_sps = (ntype == 33)
                is_pps = (ntype == 34)
                is_idr = (ntype in (19, 20))

            if is_sps:
                have_sps = True
                last_sps_off = nal_off
            if is_pps:
                have_pps = True

            ready = have_sps and (have_pps or not require_pps)

            if cur_start is None and is_idr:
                if ready:
                    start_off = last_sps_off if last_sps_off is not None else nal_off
                    if require_pps and last_pps_off is not None:
                        start_off = min(start_off, last_pps_off)
                    cur_start = start_off
                else:
                    cur_start = nal_off
                cur_codec = "h264" if detected == "h264" else "hevc"
                idr_count = 1
                continue

            if is_idr and cur_start is not None:
                if (next_off - cur_start) >= max_total_len:
                    es_ext = ".h264" if cur_codec == "h264" else ".h265"
                    es_path = os.path.join(carved_dir, f"carved_es_{count+1:04d}{es_ext}")
                    with open(es_path, "wb") as wf:
                        wf.write(mm[cur_start:next_off])
                    mp4_path = _remux_es_to_mp4(es_path, "h264" if cur_codec == "h264" else "hevc", carved_dir)
                    out.append({
                        "offset": cur_start,
                        "length": next_off - cur_start,
                        "es": es_path,
                        "rebuilt": mp4_path,
                        "ok": mp4_path is not None,
                        "codec": cur_codec
                    })
                    count += 1
                    cur_start = None
                    idr_count = 0

        if cur_start is not None:
            end = min(cur_start + max_total_len, N)
            es_ext = ".h264" if cur_codec == "h264" else ".h265"
            es_path = os.path.join(carved_dir, f"carved_es_{count+1:04d}{es_ext}")
            with open(es_path, "wb") as wf:
                wf.write(mm[cur_start:end])
            mp4_path = _remux_es_to_mp4(es_path, "h264" if cur_codec == "h264" else "hevc", carved_dir)
            out.append({
                "offset": cur_start,
                "length": end - cur_start,
                "es": es_path,
                "rebuilt": mp4_path,
                "ok": mp4_path is not None,
                "codec": cur_codec
            })
    finally:
        try: mm.release()
        except: pass
        try: mm_raw.close()
        except: pass
        try: f.close()
        except: pass

    return out

# Remux/Fix 파이프라인
def remux_avi_to_mp4(input_path,out_dir):
    stem=os.path.splitext(os.path.basename(input_path))[0]
    out_path=os.path.join(out_dir,f"{stem}.mp4")
    cmd=[_ffmpeg_path(),"-y","-loglevel","warning","-i",input_path,
        "-c:v","copy","-c:a","copy","-movflags","+faststart",out_path]
    code,_,_= _run(cmd)
    return _nonempty_file(out_path) if code==0 else None

def fix_or_remux_mp4(input_path,out_dir):
    stem=os.path.splitext(os.path.basename(input_path))[0]
    out_path=os.path.join(out_dir,f"{stem}_fixed.mp4")
    cmd=[_ffmpeg_path(),"-y","-loglevel","warning","-err_detect","ignore_err",
        "-fflags","+genpts","-i",input_path,
        "-c:v","copy","-c:a","copy","-movflags","+faststart",out_path]
    code,_,_= _run(cmd)
    return _nonempty_file(out_path) if code==0 else None

def _mp4_faststart_ok(path: str) -> bool:
    return _mp4_header_is_faststart(path)

def _looks_playable_or_probe(path: str) -> bool:
    return _looks_playable(path)

def rebuild_carved_videos(bin_path, carved_list, force_fix: bool = False, fixed_dir: Optional[str] = None):
    if not carved_list:
        return []
    if not fixed_dir:
        fixed_dir = os.path.dirname(carved_list[0]["path"]) if carved_list else os.path.dirname(bin_path)
    os.makedirs(fixed_dir, exist_ok=True)

    results = []
    for item in carved_list:
        raw = item.get("path")
        if not raw or not os.path.isfile(raw):
            continue
        ext = os.path.splitext(raw)[1].lower()
        rebuilt = None

        if not force_fix and _looks_playable_or_probe(raw):
            rebuilt = raw
        else:
            if ext == ".avi":
                rebuilt = remux_avi_to_mp4(raw, fixed_dir)
            elif ext == ".mp4":
                if force_fix or not _mp4_faststart_ok(raw):
                    rebuilt = fix_or_remux_mp4(raw, fixed_dir)
                else:
                    rebuilt = raw

        if not rebuilt:
            continue

        probe = ffprobe_json(rebuilt)
        results.append({
            "offset": item.get("offset"),
            "length": item.get("length"),
            "raw": raw,
            "rebuilt": rebuilt,
            "ok": (probe is not None),
            "probe": probe,
        })
    return results

# Auto pipelines
def _dir_is_carvable(d: str) -> bool:
    if not os.path.isdir(d): return False
    if os.path.isfile(os.path.join(d, "partition_slack.json")): return True
    if os.path.isfile(os.path.join(d, "volume_slack.json")): return True
    if os.path.isfile(os.path.join(d, "unallocated_index.json")): return True
    for n in os.listdir(d):
        if n.lower().endswith(".bin"):
            return True
    return False

def auto_carve_from_dir(bin_dir: str, max_files_per_bin=1000) -> Dict:
    print(f"[VOL_CARVER] auto_carve_from_dir bin_dir={bin_dir}", file=sys.stderr, flush=True)
    items, carved_total, rebuilt_total = [], 0, 0

    # 강제 리빌드 여부
    force_fix = ("--fix" in sys.argv) or (str(os.environ.get("VIREX_FORCE_FIX", "")).lower() in ("1","true","yes"))

    root = os.path.dirname(bin_dir)
    carved_dir = os.path.join(root, "carved")
    fixed_dir  = os.path.join(root, "carved_fixed")

    if os.path.abspath(carved_dir) == os.path.abspath(fixed_dir):
        raise RuntimeError("carved_dir and fixed_dir are identical; check your assignments.")

    print(f"[VOL_CARVER] output dirs => carved_dir={carved_dir} , fixed_dir={fixed_dir}", file=sys.stderr, flush=True)
    os.makedirs(carved_dir, exist_ok=True)
    if force_fix and fixed_dir != carved_dir:
        os.makedirs(fixed_dir, exist_ok=True)

    print(json.dumps({
        "event": "carve_dirs",
        "carved_dir": carved_dir,
        "fixed_dir": (fixed_dir if force_fix and fixed_dir != carved_dir else carved_dir)
    }), flush=True)

    # bin 목록 구성
    bin_list: List[str] = []
    meta = None
    for meta_name in ("partition_slack.json","volume_slack.json","unallocated_index.json"):
        meta_path = os.path.join(bin_dir, meta_name)
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as rf:
                    meta = json.load(rf)
                break
            except Exception:
                meta = None
    if meta:
        entries = meta.get("entries", [])
        for ent in entries:
            fp = ent.get("file") or ent.get("path") or ""
            if fp and os.path.isfile(fp):
                bin_list.append(fp)
    if not bin_list:
        for n in sorted(os.listdir(bin_dir)):
            if n.lower().endswith(".bin"):
                bin_list.append(os.path.join(bin_dir, n))

    # 각 bin 처리
    for i, bin_path in enumerate(bin_list):
        print(json.dumps({"event": "carve_start", "bin": bin_path}), flush=True)

        avi = carve_avi_from_bin(bin_path, carved_dir, max_files_per_bin)
        mp4 = carve_mp4_from_bin(bin_path, carved_dir, max_files_per_bin)
        jdr = carve_jdr_from_bin(bin_path, carved_dir, max_files=max_files_per_bin, require_pps=False)

        print(json.dumps({
            "event": "carve_counts",
            "bin": bin_path,
            "avi": len(avi),
            "mp4": len(mp4),
            "jdr": len(jdr)
        }), flush=True)

        carved_all = avi + mp4
        carved_total += len(carved_all) + len(jdr)

        if force_fix:
            rebuilt = rebuild_carved_videos(bin_path, carved_all, force_fix=True, fixed_dir=fixed_dir)
        else:
            # 빠른 채택: 원본이 playable이면 그대로
            rebuilt = rebuild_carved_videos(bin_path, carved_all, force_fix=False, fixed_dir=carved_dir)

        created_cnt = len([x for x in rebuilt if x.get("rebuilt") or x.get("raw")])
        if created_cnt > 0:
            print(json.dumps({
                "event": "carved_nonempty",
                "bin": bin_path,
                "count": created_cnt
            }), flush=True)

        rebuilt_ok = sum(1 for x in rebuilt if x.get("ok"))
        rebuilt_total += rebuilt_ok

        print(json.dumps({
            "event": "rebuild_result",
            "bin": bin_path,
            "rebuilt_ok": rebuilt_ok,
            "rebuilt_total": len(rebuilt)
        }), flush=True)

        items.append({
            "bin_index": i,
            "bin": bin_path,
            "carved_count": len(carved_all) + len(jdr),
            "rebuilt_ok": rebuilt_ok,
            "rebuilt": rebuilt,
            "jdr": jdr
        })

        if carved_total == 0 and os.path.isdir(carved_dir):
            try:
                shutil.rmtree(carved_dir)
            except Exception as e:
                logger.warning(f"carved 폴더 삭제 실패: {e}")

    return {
        "ok": True,
        "inputs": len(bin_list),
        "carved_total": carved_total,
        "rebuilt_total": rebuilt_total,
        "outputs": {
            "carved_dir": carved_dir,
            "fixed_dir": (fixed_dir if force_fix and fixed_dir != carved_dir else carved_dir)
        },
        "items": items
    }

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

# 실행 진입점
if __name__=="__main__":
    print(f"[VOL_CARVER] __file__={__file__}", file=sys.stderr, flush=True)
    print(f"[VOL_CARVER] argv: {sys.argv}", file=sys.stderr, flush=True)

    if len(sys.argv)<2:
        print(json.dumps({"event":"usage","msg":"python vol_carver.py <base_dir> [--ffmpeg-dir <dir>]"}), file=sys.stderr, flush=True)
        sys.exit(1)

    base_dir = sys.argv[1]
    print(f"[VOL_CARVER] base_dir={base_dir}", file=sys.stderr, flush=True)

    if os.path.isfile(base_dir):
        base_dir = os.path.dirname(base_dir)
    print(f"[VOL_CARVER] normalized base_dir={base_dir}", file=sys.stderr, flush=True)

    ffmpeg_dir = None
    if "--ffmpeg-dir" in sys.argv:
        i = sys.argv.index("--ffmpeg-dir")
        if i+1 < len(sys.argv): ffmpeg_dir = sys.argv[i+1]
        if ffmpeg_dir and ffmpeg_dir.lower().endswith("ffmpeg.exe"):
            ffmpeg_dir = os.path.dirname(ffmpeg_dir)

    result = carve_everything(base_dir, ffmpeg_dir_override=ffmpeg_dir)
    final_line = json.dumps(result, ensure_ascii=False)

    index_path = os.path.join(base_dir, "carved_index.json")
    try:
        with open(index_path, "w", encoding="utf-8") as wf:
            json.dump(result, wf, ensure_ascii=False, indent=2)
        print(json.dumps({"event":"index_written","path":index_path}), flush=True)
        print(json.dumps({"event":"carved_ready","index": index_path}), flush=True)
    except Exception as e:
        print(json.dumps({"event":"write_index_failed","error": str(e)}), flush=True)

    print(json.dumps({"event":"carve_done"}), flush=True)
    print(final_line, flush=True)
