import os
import sys
import json
import shutil
from python_engine.core.image_loader.e01_parser import extract_videos_from_e01
from python_engine.core.output.download_frame import download_frames

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main(e01_path, choice=None, download_dir=None):
    # ─── 0) 다운로드 모드 & 기존 temp 폴더 재사용 분기 ───
    if choice and download_dir and os.path.isdir(e01_path) and os.path.isfile(os.path.join(e01_path, "analysis.json")):
        # e01_path가 temp 디렉터리인 경우, 분석 단계 건너뛰기
        output_dir = e01_path
        tmp_json = os.path.join(output_dir, "analysis.json")
        with open(tmp_json, "r", encoding="utf-8") as rf:
            results = json.load(rf)
        total_files = len(results)
    else:
        # ─── 1) 추출 & 복원 ───
        results, output_dir, total_files = extract_videos_from_e01(e01_path)
        if total_files == 0 or not results:
            # 결과 없음
            print(json.dumps([]), flush=True)
            return

        # ─── 1.1) 분석 결과 JSON 저장 (temp) ───
        os.makedirs(output_dir, exist_ok=True)
        tmp_json = os.path.join(output_dir, "analysis.json")
        with open(tmp_json, "w", encoding="utf-8") as wf:
            json.dump(results, wf, ensure_ascii=False, indent=2)
        print(f"▶ Temp JSON: {tmp_json}", file=sys.stderr, flush=True)

        # ─── 1.2) 분석 전용 모드: choice 미지정 시 분석 경로만 출력 ───
        if not choice or not download_dir:
            print(json.dumps({"analysisPath": tmp_json}), flush=True)
            return

    # ─── 2) 다운로드 모드: choice와 download_dir이 모두 주어졌을 때 실행 ───
    DOWNLOAD_DIR = download_dir
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # 2.1) 영상 복사/변환
    if choice in ("video", "both"):
        print("▶ 영상 저장 시작...", file=sys.stderr)
        # 전체 채널(.mp4, .avi)
        for root, _, files in os.walk(output_dir):
            if os.path.basename(root) == "slack":
                continue
            for f in files:
                if f.lower().endswith((".mp4", ".avi")):
                    src = os.path.join(root, f)
                    rel = os.path.relpath(src, output_dir)
                    dst = os.path.join(DOWNLOAD_DIR, "recovery", rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
        # Slack MP4
        for category in os.listdir(output_dir):
            slack_dir = os.path.join(output_dir, category, "slack")
            if os.path.isdir(slack_dir):
                for root, _, files in os.walk(slack_dir):
                    for fn in files:
                        if fn.lower().endswith(".mp4"):
                            src = os.path.join(root, fn)
                            dst = os.path.join(DOWNLOAD_DIR, "recovery_slack", fn)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
        print("▶ 영상 저장 완료.", file=sys.stderr)

    # 2.2) 프레임 ZIP 생성
    if choice in ("both", "frames"):
        print("▶ 프레임 ZIP 저장 시작...", file=sys.stderr)
        with open(tmp_json, 'r', encoding='utf-8') as rf:
            infos = json.load(rf)
        items = []
        for info in infos:
            # 슬랙 복구 영상
            slack_info = info.get("slack_info", {})
            output_path = slack_info.get("output_path")
            print(f"[DEBUG] 슬랙 경로: {output_path} exists: {os.path.exists(output_path) if output_path else False}")
            if output_path and os.path.exists(output_path):
                items.append({
                    "output_path": output_path,
                    "filename": f"{os.path.splitext(info['name'])[0]}_slack.mp4"
                })
        print(f"[DEBUG] items: {items}")
        download_frames(items, download_dir=DOWNLOAD_DIR)
        print("▶ 프레임 저장 완료.", file=sys.stderr)

    # ─── 3) 다운로드 모드일 때만 temp 폴더 삭제 ───
    if choice and download_dir:
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"▶ 모든 파일이 '{DOWNLOAD_DIR}'에 저장되었고, 임시 폴더를 정리했습니다.", file=sys.stderr)

if __name__ == "__main__":
    # Usage:
    # 1) 분석만: python main.py <E01_PATH>
    # 2) 다운로드: python main.py <E01_PATH> <video|frames|both> <DOWNLOAD_DIR>
    if len(sys.argv) == 2:
        main(sys.argv[1])
    elif len(sys.argv) == 4 and all(sys.argv[1:]):
        _, e01_path, choice, download_dir = sys.argv
        main(e01_path, choice, download_dir)
    else:
        sys.stderr.write(f"Invalid arguments: {sys.argv[1:]}\n")
        sys.stderr.write("Usage:\n")
        sys.stderr.write("  분석만   : python main.py <E01_PATH>\n")
        sys.stderr.write("  다운로드: python main.py <E01_PATH> <video|frames|both> <DOWNLOAD_DIR>\n")
        sys.exit(1)