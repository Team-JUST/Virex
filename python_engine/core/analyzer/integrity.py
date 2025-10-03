import os
import struct

MAX_REASONABLE_CHUNK_SIZE = 10 * 1024 * 1024
MIN_REASONABLE_CHUNK_SIZE = 16
UNKNOWN_GAP_MIN = 1024

TAIL_ABS = 4 * 1024 * 1024
TAIL_RATIO = 0.005

VIDEO_SIGS = (b'00dc', b'00db', b'01dc', b'01db', b'02dc', b'02db')
AUDIO_SIGS = (b'00wb', b'01wb', b'02wb')

# MP4 helpers
def find_all_boxes(data, box_type):
    offset = 0
    found = []
    end = len(data)
    btype = box_type.encode()

    while offset + 8 <= end:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
            typ = data[offset + 4:offset + 8]
            if typ == btype:
                found.append((offset, size))
            step = size if size >= 8 else 8
            offset += step
        except Exception:
            break
    return found

def find_box(data, box_type):
    boxes = find_all_boxes(data, box_type)
    if not boxes:
        return None, None
    return boxes[0]

# AVI Helpers
def _read_le32(b, off):
    return struct.unpack('<I', b[off:off+4])[0]

def _find_list(data, fourcc, start=0):
    off = start
    end = len(data)
    while off + 12 <= end:
        if data[off:off+4] == b'LIST':
            try:
                sz = _read_le32(data, off+4)
            except struct.error:
                return None
            typ = data[off+8:off+12]
            if typ == fourcc:
                return (off, sz, off + 12)
            off += sz if sz > 0 else 12
        else:
            off += 1
    return None

def _align2(x):
    return x if (x % 2) == 0 else x + 1

def _find_next_video_sig(data, start, limit):
    best = -1
    for sig in VIDEO_SIGS:
        idx = data.find(sig, start, limit)
        if idx != -1 and (best == -1 or idx < best):
            best = idx
    return best

def _consume_chunk_if_present(data, fourcc, start, limit):
    idx = data.find(fourcc, start, limit)
    if idx == -1 or idx + 8 > limit:
        return start
    try:
        size = _read_le32(data, idx + 4)
    except struct.error:
        return start
    payload_start = idx + 8
    payload_end = payload_start + size
    end_aligned = _align2(payload_end)
    if payload_end > limit or end_aligned > limit:
        return start
    return end_aligned

def _scan_mid_damage_compact(data, movi_start, scan_end):
    off = movi_start
    end = scan_end
    last_good_end = movi_start
    view = memoryview(data)

    while off + 8 <= end:
        head = view[off:off+4].tobytes()

        # LIST 블록
        if head == b'LIST':
            try:
                sz = _read_le32(view, off+4)
            except struct.error:
                return True, last_good_end
            list_end = off + sz
            if sz < 12 or list_end > end:
                return True, last_good_end
            off = list_end
            last_good_end = off
            continue

        # 일반 청크
        fourcc = head
        try:
            sz = _read_le32(view, off+4)
        except struct.error:
            return True, last_good_end

        payload_start = off + 8
        payload_end = payload_start + sz
        next_off = _align2(payload_end)

        # 경계 검사
        if sz < 0 or payload_end > end or next_off > end:
            return True, last_good_end

        # 비디오 청크 추가 검증
        if fourcc in VIDEO_SIGS:
            if sz > MAX_REASONABLE_CHUNK_SIZE or sz <= MIN_REASONABLE_CHUNK_SIZE:
                return True, last_good_end

        # 정상 청크 처리 완료
        last_good_end = next_off
        off = next_off

    if off < end:
        next_sig = _find_next_video_sig(data, off, end)
        if next_sig == -1:
            gap_len = end - off
            if gap_len >= UNKNOWN_GAP_MIN:
                return True, last_good_end

    return False, last_good_end

def _scan_chunk_overflow_like_structure(data, start, end):
    offset = start
    while offset + 8 <= end:
        try:
            chunk_id = data[offset:offset+4]
            size = int.from_bytes(data[offset+4:offset+8], 'little', signed=False)
        except Exception:
            return True, f"[경고] 청크 크기 파싱 실패 at offset 0x{offset:X}"

        chunk_end = offset + 8 + size
        if chunk_end > end:
            try:
                name = chunk_id.decode(errors='replace')
            except Exception:
                name = '????'
            return True, f"[WARNING] 청크 크기 초과: {name} at offset 0x{offset:X} size={size}"

        offset = chunk_end + (1 if (size % 2) == 1 else 0)

    return False, None

def _big_gap(gap, total):
    return gap >= TAIL_ABS and gap >= int(total * TAIL_RATIO)

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

    if ext == ".avi":
        # 헤더 검사
        if not (data.startswith(b'RIFF') or data.startswith(b'RF64')):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 'RIFF/RF64' 시그니처 누락")
            return result

        try:
            riff_size = _read_le32(data, 4) + 8
        except struct.error:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 크기 필드 파싱 실패")
            return result

        actual_size = len(data)

        # 파일 절단(푸터) 판정
        if actual_size < riff_size:
            result["damaged"] = True
            result["reasons"].append(f"[푸터 손상] 파일 잘림(선언 크기 > 실제 크기) 선언={riff_size}, 실제={actual_size}")
            return result

        # movi 존재 확인
        movi_info = _find_list(data, b'movi')
        if not movi_info:
            result["damaged"] = True
            result["reasons"].append("[필수 청크 누락] 'movi' 청크 없음")
            return result

        _, movi_list_size, movi_payload = movi_info
        if movi_list_size == 0:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] LIST('movi') size=0")
            return result

        # 최소 비디오 시그니처 존재
        if not any(sig in data for sig in VIDEO_SIGS):
            result["damaged"] = True
            result["reasons"].append("[비디오 데이터 없음] 'NNdc/NNdb' 미검출")
            return result

        # 중간 손상 판정
        scan_end = min(riff_size, actual_size)
        mid_bad, last_good_end = _scan_mid_damage_compact(data, movi_payload, scan_end)
        if mid_bad:
            result["damaged"] = True
            result["reasons"].append("[중간 손상] 비디오 데이터 이상")

        # idx1, JUNK 청크 스킵
        scan_pos = last_good_end if last_good_end else 0
        limit = riff_size
        for _ in range(6):
            advanced = False
            new_pos = _consume_chunk_if_present(data, b'idx1', scan_pos, limit)
            if new_pos > scan_pos:
                scan_pos = new_pos
                advanced = True
            new_pos = _consume_chunk_if_present(data, b'JUNK', scan_pos, limit)
            if new_pos > scan_pos:
                scan_pos = new_pos
                advanced = True
            if not advanced:
                break
        if scan_pos > (last_good_end or 0):
            last_good_end = scan_pos

        # 푸터 잔여/갭: 남은 구간이 모두 정상 청크(JUNK, idx1, LIST)면 손상 아님
        if last_good_end:
            gap_within_riff = riff_size - last_good_end
            if _big_gap(gap_within_riff, riff_size):
                # 남은 구간 스캔
                footer_ok = True
                off = last_good_end
                while off + 8 <= riff_size:
                    chunk_id = data[off:off+4]
                    try:
                        chunk_size = _read_le32(data, off+4)
                    except struct.error:
                        footer_ok = False
                        break
                    chunk_end = off + 8 + chunk_size
                    if chunk_end > riff_size:
                        footer_ok = False
                        break
                    if chunk_id not in [b'JUNK', b'idx1', b'LIST']:
                        footer_ok = False
                        break
                    off = chunk_end
                    if chunk_size % 2 == 1:
                        off += 1
                if not footer_ok:
                    result["damaged"] = True
                    result["reasons"].append("[푸터 손상] 파일 끝단 이상(잔여/갭 발생)")

        # 상위 레벨 청크 크기 초과 검사
        overflow, msg = _scan_chunk_overflow_like_structure(data, 12, riff_size)
        if overflow and msg:
            result["damaged"] = True
            result["reasons"].append("[중간 손상] 본문 청크 크기 초과")
            return result

        # RIFF 외부(슬랙)에서의 초과 → 푸터 손상
        if len(data) > riff_size:
            overflow2, msg2 = _scan_chunk_overflow_like_structure(data, riff_size, len(data))
            if overflow2 and msg2:
                result["damaged"] = True
                result["reasons"].append("[푸터 손상] RIFF 외부 슬랙 청크 크기 초과")
                return result

        return result

    elif ext == ".mp4":
        # ftyp 박스
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

        # moov 박스
        moov_boxes = find_all_boxes(data, 'moov')
        moov_present = bool(moov_boxes)
        moov_size_zero = any(size == 0 for _, size in moov_boxes)

        # 보조: raw 검색으로 moov 흔적만이라도 확인
        raw_idx = data.find(b'moov')
        raw_found = raw_idx != -1 and raw_idx >= 4

        if not moov_present and raw_found:
            # 구조 탐색으로는 못 읽었지만 시그니처는 있음 → 손상으로 간주
            result["damaged"] = True
            result["reasons"].append("[손상] 'moov' 있음(구조 파싱 실패)")
        elif not moov_present:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'moov' 없음")
        elif moov_size_zero:
            result["damaged"] = True
            result["reasons"].append("[박스 크기 이상] 'moov' size=0")

        # mdat 박스
        mdat_boxes = find_all_boxes(data, 'mdat')
        if not mdat_boxes:
            result["damaged"] = True
            result["reasons"].append("[필수 박스 누락] 'mdat' 없음")
        else:
            for mdat_offset, mdat_size in mdat_boxes:
                if mdat_size == 0:
                    result["damaged"] = True
                    result["reasons"].append(f"[박스 크기 이상] 'mdat' offset={mdat_offset} size=0")
                    break

        return result
    
    elif ext == ".jdr":
        # JDR 파일 무결성 간단 체크: 시그니처 및 구조
        # 1. 최소 길이, 2. 1VEJ 시그니처, 3. 블록 테이블, 4. 슬랙 offset 등
        if len(data) < 64:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 파일 길이 부족")
            return result
        sig_offset = data.find(b'1VEJ')
        if sig_offset == -1:
            result["damaged"] = True
            result["reasons"].append("[시그니처 손상] 1VEJ 시그니처 없음")
            return result
        count_offset = sig_offset + 4
        if count_offset + 4 > len(data):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 블록 개수 위치가 데이터 범위를 벗어남")
            return result
        import struct
        try:
            total_blocks = struct.unpack('<I', data[count_offset:count_offset+4])[0]
        except Exception:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 블록 개수 파싱 실패")
            return result
        block_table_offset = count_offset + 4 + 0x14 * (total_blocks - 1)
        if block_table_offset + 4 > len(data):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 마지막 블록 오프셋 위치가 데이터 범위를 벗어남")
            return result
        try:
            last_block_offset_raw = struct.unpack('<I', data[block_table_offset:block_table_offset+4])[0]
            last_block_offset = last_block_offset_raw >> 4
        except Exception:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 마지막 블록 오프셋 파싱 실패")
            return result
        slack_offset_ptr = last_block_offset + 0xC8
        if slack_offset_ptr + 4 > len(data):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 슬랙 offset 위치가 데이터 범위를 벗어남")
            return result
        try:
            slack_offset = struct.unpack('<I', data[slack_offset_ptr:slack_offset_ptr+4])[0]
        except Exception:
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 슬랙 offset 파싱 실패")
            return result
        if slack_offset > len(data):
            result["damaged"] = True
            result["reasons"].append("[헤더 손상] 슬랙 시작 offset이 데이터 범위를 벗어남")
            return result
        return result

    return result
    