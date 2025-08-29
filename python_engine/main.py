import os
import sys
import json
import shutil
from python_engine.core.image_loader.e01_parser import extract_videos_from_e01
from python_engine.core.output.download_frame import download_frames

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main(e01_path, choice=None, download_dir=None):
    is_cached_analysis = (
        choice and download_dir and os.path.isdir(e01_path)
        and os.path.isfile(os.path.join(e01_path, "analysis.json"))
    )

    if is_cached_analysis:
        output_dir = e01_path
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
        print(json.dumps({"analysisPath": tmp_json_path}), flush=True)

        if not choice or not download_dir:
            return

    os.makedirs(download_dir, exist_ok=True)
    tmp_json_path = os.path.join(output_dir, "analysis.json")

    if choice in ("video", "both"):
        print("영상 저장 시작", file=sys.stderr)

        for root, _, files in os.walk(output_dir):
            if os.path.basename(root) == "slack":
                continue
            for f in files:
                if f.lower().endswith((".mp4", ".avi")):
                    src = os.path.join(root, f)
                    rel_path = os.path.relpath(src, output_dir)
                    dst = os.path.join(download_dir, "recovery", rel_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

        for category in os.listdir(output_dir):
            slack_dir = os.path.join(output_dir, category, "slack")
            if os.path.isdir(slack_dir):
                for root, _, files in os.walk(slack_dir):
                    for fn in files:
                        if fn.lower().endswith(".mp4"):
                            src = os.path.join(root, fn)
                            dst = os.path.join(download_dir, "recovery_slack", fn)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)

        print("영상 저장 완료.", file=sys.stderr)

    if choice in ("frames", "both"):
        print("프레임 ZIP 저장 시작", file=sys.stderr)

        with open(tmp_json_path, 'r', encoding='utf-8') as rf:
            infos = json.load(rf)

        items = [
            {
                "output_path": info["slack_info"]["output_path"],
                "filename": f"{os.path.splitext(info['name'])[0]}_slack.mp4"
            }
            for info in infos
            if info.get("slack_info", {}).get("output_path") and os.path.exists(info["slack_info"]["output_path"])
        ]

        download_frames(items, download_dir=download_dir)
        print("프레임 저장 완료", file=sys.stderr)
        
    if choice and download_dir:
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"모든 파일이 '{download_dir}'에 저장되었고, 임시 폴더를 정리했습니다.", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(sys.argv[1])
    elif len(sys.argv) == 4 and all(sys.argv[1:]):
        _, e01_path, choice, download_dir = sys.argv
        main(e01_path, choice, download_dir)
    else:
        sys.exit(1)