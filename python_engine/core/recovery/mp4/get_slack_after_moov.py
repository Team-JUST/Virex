import struct
import logging

logger = logging.getLogger(__name__)

MIN_BOX_SIZE = 8

def get_slack_after_moov(data):
    """MP4 파일에서 moov 박스 이후의 슬랙 공간을 찾습니다."""
    offset = 0
    total_size = len(data)

    while offset + MIN_BOX_SIZE <= total_size:
        try:
            size = struct.unpack('>I', data[offset:offset + 4])[0]
        except struct.error:
            logger.error(f"size 언팩 실패 @ offset=0x{offset:X}")
            break

        box_type = data[offset + 4:offset + 8].decode("utf-8", errors="ignore")
        if box_type == "moov":
            slack = data[offset + size:]
            return slack, offset + size, data[offset:offset + size]

        if size < MIN_BOX_SIZE:
            logger.warning(f"비정상적인 박스 크기(size={size}) → 루프 종료 @ offset=0x{offset:X}")
            break

        offset += size

    return b'', None, None