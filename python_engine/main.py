
import os
import sys
import json
import shutil
from typing import Optional, List, Iterable, Set
from python_engine.core.image_loader.e01_parser import extract_videos_from_e01
from python_engine.core.output.download_frame import download_frames
from python_engine.core.image_loader.single_video_parser import extract_from_single_video
from python_engine.core.recovery.vol_recover.vol_carver import auto_carve_from_dir

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ffmpeg, ffprobe 경로
ffmpeg_path = resource_path("bin/ffmpeg.exe")
ffprobe_path = resource_path("bin/ffprobe.exe")

def _load_selected_names(json_path: str) -> Set[str]:
    with open(json_path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    return {str(x).strip().lower() for x in arr if str(x).strip()}

def _to_selected_set(selected: Optional[object]) -> Optional[Set[str]]:
    if not selected:
        return None
    if isinstance(selected, str) and os.path.exists(selected):
        try:
            return _load_selected_names(selected)
        except Exception as e:
            print(f"[ERR] failed to read selected list: {e}", file=sys.stderr, flush=True)
            return None
    if isinstance(selected, Iterable) and not isinstance(selected, (str, bytes)):
        return {os.path.basename(str(x)).strip().lower() for x in selected if str(x).strip()}
    return None

def main(e01_path: str,
        choice: str = 'video',
        download_dir: Optional[str] = None,
        selected: Optional[List[str]] = None):

    selected_set = _to_selected_set(selected)

    tmp_json_path: Optional[str] = None
    output_dir: Optional[str] = None

    ext = os.path.splitext(e01_path)[1].lower()
    is_cached_analysis = (
        os.path.isdir(e01_path) and
        os.path.isfile(os.path.join(e01_path, "analysis.json"))
    )

    if is_cached_analysis:
        output_dir = e01_path
        tmp_json_path = os.path.join(output_dir, "analysis.json")
        with open(tmp_json_path, "r", encoding="utf-8") as rf:
            results = json.load(rf)
        total_files = len(results)
    elif ext in ('.mp4', '.avi', '.jdr'):
        results, output_dir, total_files = extract_from_single_video(e01_path)
        if total_files == 0 or not results:
            print(json.dumps([]), flush=True)
            return
        os.makedirs(output_dir, exist_ok=True)
        tmp_json_path = os.path.join(output_dir, "analysis.json")
        with open(tmp_json_path, "w", encoding="utf-8") as wf:
            json.dump(results, wf, ensure_ascii=False, indent=2)
    else:
        results, output_dir, total_files = extract_videos_from_e01(e01_path)
        if total_files == 0 or not results:
            print(json.dumps([]), flush=True)
            return
        os.makedirs(output_dir, exist_ok=True)
        tmp_json_path = os.path.join(output_dir, "analysis.json")
        with open(tmp_json_path, "w", encoding="utf-8") as wf:
            json.dump(results, wf, ensure_ascii=False, indent=2)

    if download_dir:
        os.makedirs(download_dir, exist_ok=True)

    print(json.dumps({"analysisPath": tmp_json_path}), flush=True)
    if not choice or not download_dir:
        return

    if choice in ("video", "both"):
        print("영상 저장 시작", file=sys.stderr)

        with open(tmp_json_path, 'r', encoding='utf-8') as rf:
            infos = json.load(rf)

        def _lower(s: str) -> str:
            return s.lower() if isinstance(s, str) else ""

        def _isfile(p: Optional[str]) -> bool:
            try:
                return bool(p) and os.path.isfile(p)
            except Exception:
                return False

        def _get_orig_src(info: dict, base_dir: str) -> Optional[str]:
            candidates: List[str] = []

            for k in ["recoveredPath", "recovered_path", "path", "video_path", "src", "source", "output_path"]:
                v = info.get(k)
                if isinstance(v, str) and v:
                    candidates.append(v)

            rb = info.get("rebuilt") or []
            if isinstance(rb, list):
                for x in rb:
                    if isinstance(x, dict):
                        p = x.get("rebuilt") or x.get("raw")
                        if isinstance(p, str) and p:
                            candidates.append(p)

            jdr = info.get("jdr") or []
            if isinstance(jdr, list):
                for x in jdr:
                    if isinstance(x, dict):
                        p = x.get("rebuilt") or x.get("path")
                        if isinstance(p, str) and p:
                            candidates.append(p)

            name = os.path.basename(info.get("name", "") or "")
            cat  = (info.get("category") or info.get("group") or "").strip()
            if name:
                if cat:
                    candidates.append(os.path.join(base_dir, cat, name))
                candidates.append(os.path.join(base_dir, name))

            for c in candidates:
                if _isfile(c):
                    return c
                abs2 = os.path.join(base_dir, c)
                if _isfile(abs2):
                    return abs2

            if name:
                for root, _, files in os.walk(base_dir):
                    if name in files:
                        return os.path.join(root, name)

            return None

        def _get_slack_src(sinfo: dict) -> Optional[str]:
            return (
                sinfo.get("video_path")
                or sinfo.get("video")
                or sinfo.get("path")
                or sinfo.get("slack_video_path")
            )

        copied = 0
        copied_slack = 0

        for info in infos:
            name_orig = os.path.basename(info.get("name", ""))
            name_key  = _lower(name_orig)
            if selected_set is not None and name_key not in selected_set:
                continue

            category = (info.get("category") or info.get("group") or "").strip()

            src_video = _get_orig_src(info, output_dir)
            if src_video:
                dst_video = (
                    os.path.join(download_dir, "recovery", category, name_orig)
                    if category else os.path.join(download_dir, "recovery", name_orig)
                )
                os.makedirs(os.path.dirname(dst_video), exist_ok=True)
                shutil.copy2(src_video, dst_video)
                copied += 1

            s_info = info.get("slack_info") or {}
            s_src = _get_slack_src(s_info)
            if s_src and os.path.isfile(s_src):
                root, ext = os.path.splitext(name_orig)
                slack_name = f"{root}_slack{ext}"
                dst_slack = (
                    os.path.join(download_dir, "recovery_slack", category, slack_name)
                    if category else os.path.join(download_dir, "recovery_slack", slack_name)
                )
                os.makedirs(os.path.dirname(dst_slack), exist_ok=True
                )
                shutil.copy2(s_src, dst_slack)
                copied_slack += 1

        print(json.dumps(
            {"event": "download_stats", "copied": copied, "copied_slack": copied_slack},
            ensure_ascii=False
        ), flush=True)

        print("영상 저장 완료.", file=sys.stderr)

    if choice in ("frames", "both"):
        print("프레임 ZIP 저장 시작", file=sys.stderr)

        with open(tmp_json_path, 'r', encoding='utf-8') as rf:
            infos = json.load(rf)

        items = []
        for info in infos:
            nm = os.path.basename(info.get("name", "")).lower()
            if selected_set is not None and nm not in selected_set:
                continue
            slack_info = info.get("slack_info", {})
            output_path = slack_info.get("output_path")
            if output_path and os.path.exists(output_path):
                items.append({
                    "output_path": output_path,
                    "filename": f"{os.path.splitext(info['name'])[0]}_hidden.mp4"
                })

        download_frames(items, download_dir=download_dir)
        print("프레임 저장 완료.", file=sys.stderr)

    if (choice and download_dir) and (not is_cached_analysis):
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"모든 파일이 '{download_dir}'에 저장되었고, 임시 폴더를 정리했습니다.", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(sys.argv[1])
    elif len(sys.argv) == 4:
        _, e01_path, choice, download_dir = sys.argv
        main(e01_path, choice, download_dir, None)
    elif len(sys.argv) == 5:
        _, e01_path, choice, download_dir, selected_json = sys.argv
        main(e01_path, choice, download_dir, selected_json)
    else:
        sys.exit(1)