import os
import struct

# MP4 파일 내 특정 box(atom)의 위치와 크기 탐색
def find_box(data, box_type):
    offset = 0
    while offset < len(data) - 8:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
            typ = data[offset + 4:offset + 8]
            if typ == box_type.encode():
                return offset, size
            offset += size if size > 0 else 8
        except Exception:
            break
    return None, None

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
        if not data.startswith(b'RIFF'):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 'RIFF' 시그니처 누락")
            return result
        
        riff_size = struct.unpack('<I', data[4:8])[0] + 8
        actual_size = len(data)
        if abs(riff_size - actual_size) > 1024:
            result["damaged"] = True
            result["reasons"].append(f"[파일 크기 불일치] RIFF={riff_size}, 실제={actual_size}")
        
        if b'movi' not in data:
            result["damaged"] = True
            result["reasons"].append("[필수 청크 누락] 'movi' 청크 없음")

        front_count = data.count(b'00dc')
        rear_count = data.count(b'01dc')
        if front_count == 0 or rear_count == 0:
            result["damaged"] = True
            result["reasons"].append("[프레임 청크 누락] '00dc' 또는 '01dc' 없음")
    
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
        moov_offset, moov_size = find_box(data, 'moov')
        if moov_offset is None:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'moov' 없음")
        elif moov_size == 0:
            result["damaged"] = True
            result["reasons"].append("[박스 크기 이상] 'moov' size=0")
        
        # mdat 박스 검증
        mdat_offset, mdat_size = find_box(data, 'mdat')
        if mdat_offset is None:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'mdat' 없음")
        elif mdat_size == 0:
            result["damaged"] = True
            result["reasons"].append("[박스 크기 이상] 'mdat' size=0")

    return result