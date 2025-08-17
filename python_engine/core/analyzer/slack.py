import os
import struct

def get_slack_info(file_path):
    """
    파일 확장자에 따라 MP4/AVI 슬랙 분석 함수를 호출.
    """
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".mp4":
            return analyze_mp4_slack(file_path)
        elif ext == ".avi":
            return analyze_avi_slack(file_path)
        else:
            return {
                "error": f"지원하지 않은 파일 확장자: {ext}"
            }
    except Exception as e:
        return {
            "error": f"슬랙 분석 중 오류 발생: {str(e)}"
        }

def analyze_mp4_slack(file_path):
    """
    1) MP4 박스 간 빈 영역 계산
    2) mdat 페이로드 내부 padding 계산
    3) 복원된 .h264 파일 크기로 보정
    """
    # 원본 MP4 데이터 로드
    with open(file_path, 'rb') as f:
        data = f.read()
    size = len(data)

    # --- 박스 위치 찾기 함수 정의 ---
    def find_box(box_type: bytes):
        off = 0
        while off + 8 <= size:
            box_size = int.from_bytes(data[off:off+4], 'big')
            typ      = data[off+4:off+8]
            if typ == box_type:
                return off, box_size
            if box_size <= 0:
                break
            off += box_size
        return None, None

    ftyp_off, ftyp_sz = find_box(b'ftyp')
    mdat_off, mdat_sz = find_box(b'mdat')
    moov_off, moov_sz = find_box(b'moov')

    if mdat_off is None or mdat_sz is None:
        raise ValueError("MP4 구조 분석 실패: mdat 박스가 없습니다")

    # --- 1) 박스 사이 slack 계산 ---
    box_slack = 0
    last_end  = (ftyp_off or 0) + (ftyp_sz or 0)
    for off, sz in ((mdat_off, mdat_sz), (moov_off, moov_sz)):
        if off and sz and off > last_end:
            box_slack += off - last_end
        if off and sz:
            last_end = off + sz

    # --- 2) mdat 내부 padding 계산 (NAL 단위) ---
    payload = data[mdat_off+8 : mdat_off+mdat_sz]
    starts = []
    i = 0
    while i < len(payload):
        idx4 = payload.find(b'\x00\x00\x00\x01', i)
        if idx4 >= 0:
            starts.append((idx4, 4))
            i = idx4 + 4
            continue
        idx3 = payload.find(b'\x00\x00\x01', i)
        if idx3 >= 0:
            starts.append((idx3, 3))
            i = idx3 + 3
            continue
        break
    # 마지막 NAL 끝 위치 추가
    starts.append((len(payload), 0))

    internal_slack = 0
    for (pos, prefix), (next_pos, _) in zip(starts, starts[1:]):
        nal_data_end = pos + prefix
        gap = next_pos - nal_data_end
        if gap > 0:
            internal_slack += gap

    # 초기 합산
    total_slack = box_slack + internal_slack

    # --- 3) 복원된 H.264 스트림 크기로 보정 ---
    # "…/recovery_hidden/<category>/slack/XXX_hidden.mp4"
    # → "…/recovery_hidden/<category>/raw/XXX_slack.h264"
    slack_h264_path = file_path.replace(
        os.path.join("slack"), 
        os.path.join("raw")
    ).replace("_hidden.mp4", "_slack.h264")

    if os.path.exists(slack_h264_path):
        # 실제 복원된 h264 크기를 우선 사용
        slack_bytes = os.path.getsize(slack_h264_path)
        total_slack = slack_bytes
    else:
        slack_bytes = total_slack

    valid_bytes = size - slack_bytes
    slack_pct   = round(slack_bytes / size, 4)  # 0~1 범위로 반환

    return {
        "total_bytes":        size,
        "valid_data_bytes":   valid_bytes,
        "slack_bytes":        slack_bytes,
        "slack_ratio_percent": slack_pct,
        "slack_regions":      None
    }

def analyze_avi_slack(file_path):
    """
    기존 AVI 슬랙 분석 로직 (RIFF 청크 간 빈 영역 계산)
    """
    with open(file_path, 'rb') as f:
        data = f.read()

    file_size = len(data)
    if data[:4] != b'RIFF':
        raise ValueError("Invalid AVI file: Missing RIFF header")

    riff_size      = int.from_bytes(data[4:8], 'little')
    riff_end       = 8 + riff_size
    cursor         = 12
    slack_regions  = []
    last_chunk_end = cursor

    while cursor + 8 <= file_size:
        chunk_start = cursor
        chunk_id    = data[cursor:cursor+4]
        chunk_size  = struct.unpack('<I', data[cursor+4:cursor+8])[0]
        chunk_end   = cursor + 8 + chunk_size

        if chunk_end > file_size:
            break

        if chunk_start > last_chunk_end:
            slack_regions.append((last_chunk_end, chunk_start))

        last_chunk_end = chunk_end
        cursor = chunk_end
        if chunk_size % 2 == 1:
            cursor += 1
            last_chunk_end += 1

    if riff_end < file_size:
        slack_regions.append((riff_end, file_size))

    slack_bytes = sum(end - start for start, end in slack_regions)
    slack_pct   = round(slack_bytes / file_size, 4)  # 0~1 범위로 반환

    return {
        "total_bytes":        file_size,
        "valid_data_bytes":   file_size - slack_bytes,
        "slack_bytes":        slack_bytes,
        "slack_ratio_percent": slack_pct,
        "slack_regions":      slack_regions
    }