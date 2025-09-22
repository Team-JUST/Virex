import struct
import logging

logger = logging.getLogger(__name__)

MIN_BOX_SIZE = 8

def _read_u32(b: bytes, off: int) -> int:
    return struct.unpack_from(">I", b, off)[0]

def _read_u64(b: bytes, off: int) -> int:
    return struct.unpack_from(">Q", b, off)[0]

def _iter_boxes(buf: bytes, start: int, end: int):
    off = start
    total = len(buf)
    while off + MIN_BOX_SIZE <= end and off + MIN_BOX_SIZE <= total:
        size = _read_u32(buf, off)
        btyp = buf[off+4:off+8]
        typ = (btyp.decode("ascii", errors="ignore") or "????")

        if size == 1:
            # 64-bit largesize
            if off + 16 > total:
                logger.warning("64-bit size 헤더 부족 @ 0x%X", off)
                return
            largesize = _read_u64(buf, off+8)
            box_size = largesize
            header_len = 16
        else:
            box_size = size if size != 0 else (end - off)  # size==0 → 컨테이너 끝까지
            header_len = 8

        if box_size < header_len or off + box_size > total:
            logger.warning("비정상 박스(size=%d, type=%s) @ 0x%X", box_size, typ, off)
            return

        yield off, box_size, typ, header_len
        off += box_size

def _find_moov_and_mdats(data: bytes):
    total = len(data)
    top_boxes = list(_iter_boxes(data, 0, total))

    moov_off = moov_size = None
    mdats = []

    for off, size, typ, header_len in top_boxes:
        if typ == "moov":
            # 여러 개면 '가장 마지막 moov'를 채택 (일반적으로 최신/유효)
            moov_off, moov_size = off, size
        elif typ == "mdat":
            mdats.append((off, size, header_len))

    moov_bytes = data[moov_off:moov_off+moov_size] if moov_off is not None else None
    return moov_off, moov_size, moov_bytes, mdats

def _collect_stco_co64_offsets(moov_bytes: bytes):
    if not moov_bytes:
        return []

    offsets = []
    total = len(moov_bytes)

    # moov 내부도 일반적인 ISO BMFF 구조이므로, 재귀 대신 평면 순회로 충분
    stack = [(0, total)]  # (start, end) 구간을 스택으로 탐색
    while stack:
        start, end = stack.pop()
        for off, size, typ, header_len in _iter_boxes(moov_bytes, start, end):
            # 컨테이너 박스면 내부도 순회하도록 푸시
            if typ in ("trak", "mdia", "minf", "stbl", "edts", "udta", "mvex"):
                stack.append((off + header_len, off + size))
            elif typ == "stco":
                # 최소 헤더: version(1)+flags(3)+entry_count(4) = 8
                body_off = off + header_len
                if body_off + 8 > total:
                    logger.warning("stco 헤더 부족 @ moov+0x%X", body_off)
                    continue
                entry_count = _read_u32(moov_bytes, body_off + 4)
                table_off = body_off + 8
                needed = entry_count * 4
                if table_off + needed > total:
                    logger.warning("stco 테이블 부족(count=%d) @ moov+0x%X", entry_count, table_off)
                    continue
                for i in range(entry_count):
                    val = _read_u32(moov_bytes, table_off + 4*i)
                    offsets.append(val)
            elif typ == "co64":
                body_off = off + header_len
                if body_off + 8 > total:
                    logger.warning("co64 헤더 부족 @ moov+0x%X", body_off)
                    continue
                entry_count = _read_u32(moov_bytes, body_off + 4)
                table_off = body_off + 8
                needed = entry_count * 8
                if table_off + needed > total:
                    logger.warning("co64 테이블 부족(count=%d) @ moov+0x%X", entry_count, table_off)
                    continue
                for i in range(entry_count):
                    val = _read_u64(moov_bytes, table_off + 8*i)
                    offsets.append(val)

    # 중복 제거 + 정렬(선택)
    offsets = sorted(set(offsets))
    return offsets

def get_slack(data: bytes):
    """
    moov가 참조(stco/co64)하는 오프셋이 들어있는 mdat들의 끝을 계산하여,
    원본(정상) 데이터의 끝을 결정한다.
    슬랙 시작 = max(moov_end, 마지막으로 '참조된' mdat의 끝).
    반환: (slack_bytes, slack_start_offset, moov_box_bytes_or_none)
    """
    total = len(data)

    moov_off, moov_size, moov_bytes, mdats = _find_moov_and_mdats(data)

    # moov/mdat가 하나도 없으면 실패
    if moov_off is None and not mdats:
        logger.info("moov/mdat를 찾지 못함")
        return b"", None, None

    # 기본 경계 후보: moov 끝
    moov_end = (moov_off + moov_size) if moov_off is not None else 0

    # moov가 참조하는 모든 오프셋 수집
    ref_offsets = _collect_stco_co64_offsets(moov_bytes) if moov_bytes else []

    # mdat의 끝 후보: moov가 참조한 오프셋이 포함된 mdat의 (off+size)
    last_ref_mdat_end = 0
    if ref_offsets and mdats:
        # mdat 범위를 미리 구성
        # offsets는 'mdat payload 내부'를 가리키는 절대 오프셋.
        # 보수적으로 mdat [off, off+size) 범위로 포함 판정 (헤더 포함)
        for ref in ref_offsets:
            for m_off, m_size, m_hdr in mdats:
                m_end = m_off + m_size
                if m_off <= ref < m_end:
                    if m_end > last_ref_mdat_end:
                        last_ref_mdat_end = m_end
                    break  # 해당 ref는 어떤 mdat 하나에만 포함되면 충분
    else:
        # 참조 오프셋을 못 읽은 경우: 보수적으로 '가장 마지막 mdat 끝' 사용
        if mdats:
            last_ref_mdat_end = max(m_off + m_size for (m_off, m_size, _h) in mdats)
        else:
            last_ref_mdat_end = 0

    # 정상 데이터의 끝 = 둘 중 큰 값
    normal_end = max(moov_end, last_ref_mdat_end)
    if normal_end <= 0 or normal_end > total:
        # 방어적 처리
        normal_end = moov_end if 0 < moov_end <= total else last_ref_mdat_end
        if normal_end <= 0 or normal_end > total:
            # 그래도 이상하면 슬랙 없음 판정
            return b"", None, moov_bytes

    slack = data[normal_end:]
    return slack, normal_end, moov_bytes
