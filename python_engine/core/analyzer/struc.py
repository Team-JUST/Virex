import os

def get_structure_info(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".mp4":
            with open(file_path, 'rb') as file:
                data = file.read()
            file_size = len(data)
            lines = parse_box(data, 0, file_size)
            return {"type": "mp4", "structure": lines}

        elif ext == ".avi":
            lines = []
            with open(file_path, 'rb') as file:
                binary_data = file.read()
                riff_declared_size = int.from_bytes(binary_data[4:8], 'little')
                actual_size = len(binary_data)
                lines.append(f"RIFF declared size: 0x{riff_declared_size:06X}")
                lines.append(f"Actual file size: 0x{actual_size:06X}\n")

                offset = 12
                while offset < len(binary_data):
                    chunk_id = binary_data[offset:offset + 4]
                    if len(chunk_id) < 4:
                        break

                    try:
                        chunk_size = int.from_bytes(binary_data[offset + 4:offset + 8], 'little')
                    except Exception as e:
                        lines.append(f"[ERROR] 청크 크기 파싱 실패 at offset {hex(offset)}: {e}")
                        break

                    chunk_end = offset + 8 + chunk_size
                    if chunk_end > len(binary_data):
                        lines.append(f"[WARNING] 청크 크기 초과: {chunk_id.decode(errors='replace')} at offset {hex(offset)} size={chunk_size}")
                        break

                    if chunk_id == b'stsd':
                        stsd_data = binary_data[offset + 8: offset + 8 + chunk_size]
                        codec_type = stsd_data[10:14].decode('ascii', errors='replace')
                        lines.append(f"stsd Start Offset : 0x{offset:X}")
                        lines.append(f"stsd Size : 0x{chunk_size:X}")
                        lines.append(f"Codec : {codec_type}")

                    if chunk_id == b'LIST':
                        list_subtype = binary_data[offset + 8:offset + 12]
                        label = list_subtype.decode(errors='replace')
                        lines.append(f"[LIST-{label}] offset: 0x{offset:X} size: 0x{chunk_size:X}")

                    elif chunk_id in [b'JUNK', b'idx1']:
                        lines.append(f"{chunk_id.decode(errors='replace')} start offset : 0x{offset:X}")
                        lines.append(f"{chunk_id.decode(errors='replace')} size : 0x{chunk_size:X}")

                    offset += 8 + chunk_size
                    if chunk_size % 2 == 1:
                        offset += 1
                    if offset >= len(binary_data):
                        break

            return {"type": "avi", "structure": lines}

        else:
            return {"error": f"지원하지 않는 확장자: {ext}"}
    except Exception as e:
        return {"error": f"구조 분석 중 오류 발생: {str(e)}"}
    
def parse_box(data, offset, file_size, indent_level=0):
    # MP4 박스 계층 구조 정의
    box_hierarchy = {
        "moov": ["mvhd", "trak", "udta", "mvex"],  # moov 내부 박스들
        "trak": ["tkhd", "edts", "mdia"],         # trak 내부 박스들
        "mdia": ["mdhd", "hdlr", "minf"],         # mdia 내부 박스들
        "minf": ["vmhd", "smhd", "dinf", "stbl"], # minf 내부 박스들
        "stbl": ["stsd", "stts", "ctts", "stsc", "stsz", "stz2", "stco", "co64", "stss", "sbgp", "sgpd"],  # 샘플 관련
        "dinf": ["dref"],                         # dinf 내부 박스
        "meta": ["hdlr", "ilst"],                 # meta 관련 박스
        "ilst": ["©nam", "©alb", "©art"],         # 사용자 정의 데이터
    }
    output = []  # 출력 저장

    while offset < file_size:  # 파일 끝까지 탐색
        if offset + 8 > file_size:  # 파일 끝 범위 방지
            output.append(f"[WARNING] 박스 크기 읽기 실패: offset={hex(offset)}")
            break

        # 박스 크기와 타입 읽기
        try:
            box_size = int.from_bytes(data[offset:offset + 4], byteorder='big')
            box_type = data[offset + 4:offset + 8].decode('utf-8', errors='replace')
        except Exception as e:
            output.append(f"[ERROR] 박스 파싱 실패 at offset {hex(offset)}: {e}")
            break

        if box_size < 8 or offset + box_size > file_size:
            output.append(f"[WARNING] 비정상적인 박스 크기: {box_type} at offset {hex(offset)} size={box_size}")
            break

        if box_size == 0:
            output.append(f"[WARNING] box size == 0 → 무한 루프 방지 종료 at offset {hex(offset)}")
            break

        # 박스 정보 추가
        output.append(f"{'    ' * indent_level}{box_type} box start offset: {hex(offset)}")
        output.append(f"{'    ' * indent_level}{box_type} box size: {hex(box_size)}")

        # 하위 박스가 있으면 재귀적으로 파싱
        if box_type in box_hierarchy:
            sub_box_output = parse_box(data, offset + 8, offset + box_size, indent_level + 1)
            output.extend(sub_box_output)

        offset += box_size

    return output