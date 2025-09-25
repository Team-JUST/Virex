
import struct
import logging

logger = logging.getLogger(__name__)

MIN_BOX_SIZE = 8

def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('>I', data, offset)[0]

def read_u64(data: bytes, offset: int) -> int:
    return struct.unpack_from('>Q', data, offset)[0]

def iter_mp4_boxes(data: bytes, start: int, end: int):
    offset = start
    total = len(data)
    while offset + MIN_BOX_SIZE <= end and offset + MIN_BOX_SIZE <= total:
        size = read_u32(data, offset)
        box_type = data[offset+4:offset+8].decode('ascii', errors='ignore') or '????'

        if size == 1:
            # 64비트 largesize
            if offset + 16 > total:
                logger.warning(f"64비트 박스 크기 헤더 부족: 0x{offset:X}")
                return
            largesize = read_u64(data, offset+8)
            box_size = largesize
            header_len = 16
        else:
            box_size = size if size != 0 else (end - offset)
            header_len = 8

        if box_size < header_len or offset + box_size > total:
            logger.warning(f"비정상 박스 (size={box_size}, type={box_type}) @ 0x{offset:X}")
            return

        yield offset, box_size, box_type, header_len
        offset += box_size

def find_moov_and_mdats(data: bytes):
    total = len(data)
    top_boxes = list(iter_mp4_boxes(data, 0, total))

    moov_offset = moov_size = None
    mdats = []

    for offset, size, box_type, header_len in top_boxes:
        if box_type == 'moov':
            moov_offset, moov_size = offset, size
        elif box_type == 'mdat':
            mdats.append((offset, size, header_len))

    moov_bytes = data[moov_offset:moov_offset+moov_size] if moov_offset is not None else None
    return moov_offset, moov_size, moov_bytes, mdats

def collect_stco_co64_offsets(moov_bytes: bytes):
    if not moov_bytes:
        return []

    offsets = []
    total = len(moov_bytes)
    stack = [(0, total)]
    while stack:
        start, end = stack.pop()
        for offset, size, box_type, header_len in iter_mp4_boxes(moov_bytes, start, end):
            if box_type in ('trak', 'mdia', 'minf', 'stbl', 'edts', 'udta', 'mvex'):
                stack.append((offset + header_len, offset + size))
            elif box_type == 'stco':
                body_offset = offset + header_len
                if body_offset + 8 > total:
                    logger.warning(f"stco 헤더 부족 @ moov+0x{body_offset:X}")
                    continue
                entry_count = read_u32(moov_bytes, body_offset + 4)
                table_offset = body_offset + 8
                needed = entry_count * 4
                if table_offset + needed > total:
                    logger.warning(f"stco 테이블 부족(count={entry_count}) @ moov+0x{table_offset:X}")
                    continue
                for i in range(entry_count):
                    val = read_u32(moov_bytes, table_offset + 4*i)
                    offsets.append(val)
            elif box_type == 'co64':
                body_offset = offset + header_len
                if body_offset + 8 > total:
                    logger.warning(f"co64 헤더 부족 @ moov+0x{body_offset:X}")
                    continue
                entry_count = read_u32(moov_bytes, body_offset + 4)
                table_offset = body_offset + 8
                needed = entry_count * 8
                if table_offset + needed > total:
                    logger.warning(f"co64 테이블 부족(count={entry_count}) @ moov+0x{table_offset:X}")
                    continue
                for i in range(entry_count):
                    val = read_u64(moov_bytes, table_offset + 8*i)
                    offsets.append(val)

    offsets = sorted(set(offsets))
    return offsets

def get_slack(data: bytes):
    """
    MP4 파일에서 moov가 참조(stco/co64)하는 오프셋이 들어있는 mdat들의 끝을 계산하여
    정상 데이터의 끝을 결정하고, 슬랙 데이터를 반환합니다.
    슬랙 시작 = max(moov_end, 마지막으로 참조된 mdat의 끝)
    반환: (slack_bytes, slack_start_offset, moov_box_bytes_or_none)
    """
    total = len(data)
    moov_offset, moov_size, moov_bytes, mdats = find_moov_and_mdats(data)

    if moov_offset is None and not mdats:
        logger.info("moov/mdat 박스를 찾지 못했습니다.")
        return b"", None, None

    moov_end = (moov_offset + moov_size) if moov_offset is not None else 0
    ref_offsets = collect_stco_co64_offsets(moov_bytes) if moov_bytes else []

    last_ref_mdat_end = 0
    if ref_offsets and mdats:
        for ref in ref_offsets:
            for m_offset, m_size, m_hdr in mdats:
                m_end = m_offset + m_size
                if m_offset <= ref < m_end:
                    if m_end > last_ref_mdat_end:
                        last_ref_mdat_end = m_end
                    break
    else:
        if mdats:
            last_ref_mdat_end = max(m_offset + m_size for (m_offset, m_size, _h) in mdats)
        else:
            last_ref_mdat_end = 0

    normal_end = max(moov_end, last_ref_mdat_end)
    if normal_end <= 0 or normal_end > total:
        normal_end = moov_end if 0 < moov_end <= total else last_ref_mdat_end
        if normal_end <= 0 or normal_end > total:
            logger.warning("슬랙 추출 실패: 정상 데이터 경계가 비정상적입니다.")
            return b"", None, moov_bytes

    slack = data[normal_end:]
    return slack, normal_end, moov_bytes
