import os
import json
import tempfile
import time
from python_engine.core.recovery.mp4.extract_slack import recover_mp4_slack
from python_engine.core.recovery.avi.extract_slack import recover_avi_slack
from python_engine.core.analyzer.basic_info_parser import get_basic_info_with_meta
from python_engine.core.analyzer.integrity import get_integrity_info
from python_engine.core.analyzer.struc import get_structure_info
from python_engine.core.recovery.utils.unit import bytes_to_unit

VIDEO_EXTENSIONS = ('.mp4', '.avi', '.jdr')

def build_analysis(basic_target_path, origin_video_path, meta=None):
    return {
        'basic': get_basic_info_with_meta(basic_target_path, meta),
        'integrity': get_integrity_info(origin_video_path),
        'structure': get_structure_info(basic_target_path),
    }

def handle_single_video_file(filepath, output_dir):
    ext = os.path.splitext(filepath)[1].lower()
    name = os.path.basename(filepath)
    with open(filepath, 'rb') as rf:
        data = rf.read()

    category = "single"
    orig_dir = os.path.join(output_dir, category)
    os.makedirs(orig_dir, exist_ok=True)
    original_path = os.path.join(orig_dir, name)
    with open(original_path, 'wb') as wf:
        wf.write(data)

    # 원본 파일의 타임스탬프를 meta로 전달
    class Meta:
        crtime = os.path.getctime(filepath)
        mtime = os.path.getmtime(filepath)
        atime = os.path.getatime(filepath)
    meta = Meta()

    if ext == '.mp4':
        slack_dir = os.path.join(orig_dir, 'slack')
        os.makedirs(slack_dir, exist_ok=True)
        slack_info = recover_mp4_slack(
            filepath=original_path,
            output_h264_dir=slack_dir,
            output_video_dir=slack_dir,
            target_format="mp4",
            use_gpu=False
        )
        origin_video_path = slack_info.get('source_path', original_path)
        recovered_mp4 = slack_info.get('video_path')

        analysis_target = (
            recovered_mp4
            if (slack_info.get('recovered') and recovered_mp4 and os.path.exists(recovered_mp4))
            else origin_video_path
        )
        
        result = {
            'name': name,
            'path': filepath,
            'size': bytes_to_unit(len(data)),
            'origin_video': origin_video_path,
            'slack_info': slack_info,
            'analysis': build_analysis(analysis_target, origin_video_path, meta)
        }
    elif ext == '.avi':
        avi_info = recover_avi_slack(
            input_avi=original_path,
            base_dir=orig_dir,
            target_format="mp4",
            use_gpu=False
        )
        origin_video_path = avi_info.get('source_path', avi_info.get('origin_path', original_path))
        channels_only = {k: v for k, v in avi_info.items() if isinstance(v, dict)}
        result = {
            'name': name,
            'path': filepath,
            'size': bytes_to_unit(len(data)),
            'origin_video': origin_video_path,
            'channels': channels_only,
            'analysis': build_analysis(origin_video_path, origin_video_path, meta)
        }
    elif ext == '.jdr':
        result = {
            'name': name,
            'path': filepath,
            'size': bytes_to_unit(len(data)),
            'origin_video': original_path,
            'analysis': build_analysis(original_path, original_path, meta)
        }
    else:
        return None

    return result

def extract_from_single_video(video_path):
    temp_base = tempfile.gettempdir()
    output_dir = tempfile.mkdtemp(prefix="Virex_", dir=temp_base)
    result = handle_single_video_file(video_path, output_dir)
    print(json.dumps({"tempDir": output_dir}), flush=True)
    return [result] if result else [], output_dir, 1 if result else 0