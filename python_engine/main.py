import os
import sys

import json
import shutil
from typing import Optional, List, Iterable, Set

from python_engine.core.image_loader.e01_parser import extract_videos_from_e01
from python_engine.core.output.download_frame import download_frames

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    is_cached_analysis = (
        os.path.isdir(e01_path) and
        os.path.isfile(os.path.join(e01_path, "analysis.json"))
    )

    # 1) 분석 결과 확보 (cache or fresh)
    if is_cached_analysis:
        output_dir = e01_path
        tmp_json_path = os.path.join(output_dir, "analysis.json")
        with open(os.path.join(output_dir, "analysis.json"), "r", encoding="utf-8") as rf:
            results = json.load(rf)
        total_files = len(results)
    else:
        results, output_dir, total_files = extract_videos_from_e01(e01_path)

        if total_files == 0 or not results:
            print(json.dumps([]), flush=True)
            return
        os.makedirs(output_dir, exist_ok=True)
        tmp_json_path = os.path.join(output_dir, "analysis.json")
        with open(tmp_json_path, "w", encoding="utf-8") as wf:
            json.dump(results, wf, ensure_ascii=False, indent=2)

    # 4) 다운로드 준비
    print(json.dumps({"analysisPath": tmp_json_path}), flush=True)

    if not choice or not download_dir:
        return

    os.makedirs(download_dir, exist_ok=True)

    # 프론트로 경로 전달
    print(json.dumps({"analysisPath": tmp_json_path}), flush=True)
    if not choice or not download_dir:
        return


    if choice in ("video", "both"):

        print("영상 저장 시작...", file=sys.stderr)

        # 원본/복구 영상
        for root, _, files in os.walk(output_dir):
            if os.path.basename(root) == "slack":
                continue
            for f in files:
                if f.lower().endswith((".mp4", ".avi")):
                    base = os.path.basename(f).lower()
                    if selected_set is not None and base not in selected_set:
                        continue
                    src = os.path.join(root, f)
                    rel_path = os.path.relpath(src, output_dir)
                    dst = os.path.join(download_dir, "recovery", rel_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

        # slack 폴더 안의 숨김 영상
        for category in os.listdir(output_dir):
            slack_dir = os.path.join(output_dir, category, "slack")
            if os.path.isdir(slack_dir):
                for root, _, files in os.walk(slack_dir):
                    for fn in files:
                        if fn.lower().endswith(".mp4"):
                            base = os.path.basename(fn).lower()
                            if selected_set is not None and base not in selected_set:
                                continue
                            src = os.path.join(root, fn)
                            dst = os.path.join(download_dir, "recovery_slack", fn)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)

        print("영상 저장 완료.", file=sys.stderr)

    # 2.2) 프레임 ZIP
    if choice in ("frames", "both"):
        print("프레임 ZIP 저장 시작...", file=sys.stderr)

        with open(tmp_json_path, 'r', encoding='utf-8') as rf:
            infos = json.load(rf)

        # (선택 목록 필터 반영)
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

    # 임시폴더 정리: 캐시가 아닐 때만 삭제
    if (choice and download_dir) and (not is_cached_analysis):
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"모든 파일이 '{download_dir}'에 저장되었고, 임시 폴더를 정리했습니다.", file=sys.stderr)



if __name__ == "__main__":

    # Usage:
    # 1) 분석만: python main.py <E01_PATH>
    # 2) 다운로드: python main.py <E01_PATH> <video|frames|both> <DOWNLOAD_DIR> [SELECTED_JSON]

    if len(sys.argv) == 2:
        main(sys.argv[1])
    elif len(sys.argv) == 4:
        _, e01_path, choice, download_dir = sys.argv
        main(e01_path, choice, download_dir, None)
    elif len(sys.argv) == 5:
        _, e01_path, choice, download_dir, selected_json = sys.argv
        main(e01_path, choice, download_dir, selected_json)
    else:

        sys.stderr.write(f"Invalid arguments: {sys.argv[1:]}\n")
        sys.stderr.write("Usage:\n")
        sys.stderr.write("  분석만   : python main.py <E01_PATH>\n")
        sys.stderr.write("  다운로드: python main.py <E01_PATH> <video|frames|both> <DOWNLOAD_DIR> [SELECTED_JSON]\n")

        sys.exit(1)