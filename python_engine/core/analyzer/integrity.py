import os
import struct

# MP4 파일 내 특정 box(atom)의 위치와 크기 탐색
def find_all_boxes(data, box_type):
    offset = 0
    found = []
    while offset < len(data) - 8:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
            typ = data[offset + 4:offset + 8]
            if typ == box_type.encode():
                found.append((offset, size))
            offset += size if size > 0 else 8
        except Exception:
            break
    return found

def find_box(data, box_type):
    boxes = find_all_boxes(data, box_type)
    if not boxes:
        return None, None
    return boxes[0]

# 비디오 파일 무결성 검사
def get_integrity_info(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    result = {
        "damaged": False,
        "reasons": []
    }

    try:
        with open(file_path, 'rb') as f:
            data = f.read()
    except Exception as e:
        result["damaged"] = True
        result["reasons"].append(f"파일 열기 실패: {e}")
        return result
    
    # AVI 무결성 검사
    if ext == ".avi":
        # 헤더
        if not (data.startswith(b'RIFF') or data.startswith(b'RF64')):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 'RIFF/RF64' 시그니처 누락")
            return result

        # 파일 잘림 여부
        try:
            riff_size = struct.unpack('<I', data[4:8])[0] + 8
        except struct.error:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 크기 필드 파싱 실패")
            return result

        actual_size = len(data)
        if actual_size < riff_size:
            result["damaged"] = True
            result["reasons"].append(f"[파일 잘림] 선언={riff_size}, 실제={actual_size}")
            return result

        # movi 청크 존재 확인
        if b'movi' not in data:
            result["damaged"] = True
            result["reasons"].append("[필수 청크 누락] 'movi' 청크 없음")
            return result

        # 비디오 데이터 최소 존재 (00dc/00db/01dc/01db 중 하나라도 있어야 함)
        if not (b'00dc' in data or b'00db' in data or b'01dc' in data or b'01db' in data):
            result["damaged"] = True
            result["reasons"].append("[비디오 데이터 없음] 'NNdc/NNdb' 미검출")
            return result
    
    # MP4 무결성 검사
    elif ext == ".mp4":
        # ftyp 박스 검증
        ftyp_offset, ftyp_size = find_box(data, 'ftyp')
        if ftyp_size is None:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'ftyp' 없음")
            return result
        if ftyp_offset != 0:
            result["damaged"] = True
            result["reasons"].append(f"[박스 위치 이상] 'ftyp' offset={ftyp_offset}")
        if ftyp_size == 0:
            result["damaged"] = True
            result["reasons"].append("[박스 크기 이상] 'ftyp' size=0")

        # moov 박스 검증
            moov_boxes = find_all_boxes(data, 'moov')
            if not moov_boxes:
                result["damaged"] = True
                result["reasons"].append("[필수 박스 누락] 'moov' 없음")
            else:
                # 크기 0인 moov 박스가 하나라도 있으면 경고
                for moov_size in moov_boxes:
                    if moov_size == 0:
                        result["damaged"] = True
                        result["reasons"].append("[박스 크기 이상] 'moov' size=0")
        
        # mdat 박스 검증
        mdat_boxes = find_all_boxes(data, 'mdat')
        if not mdat_boxes:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'mdat' 없음")
        else:
            for mdat_offset, mdat_size in mdat_boxes:
                if mdat_size == 0:
                    result["damaged"] = True
                    result["reasons"].append(f"[박스 크기 이상] 'mdat' offset={mdat_offset} size=0")

    return result