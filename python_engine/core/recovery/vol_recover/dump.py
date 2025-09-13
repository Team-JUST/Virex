# python_engine/core/recovery/fs_unalloc/dump.py

import os, json
import pytsk3

def dump_fs_unalloc(img_info, fs_info, out_dir, max_file_bytes=128*1024*1024, overlap=0):
    """
    img_info: pyewf.opened 이미지 or TSK Img_Info
    fs_info:  pytsk3.FS_Info
    out_dir:  .../fs_unalloc 폴더 경로
    max_file_bytes: 한 덤프 파일 최대 용량(회전 분할)
    overlap: 파일 분할 저장 시 오버랩 바이트 (시그니처 경계 대비)
    """
    os.makedirs(out_dir, exist_ok=True)

    bs = int(fs_info.info.block_size)           # FS 블록/섹터 크기
    fs_off = int(fs_info.info.offset)           # FS 시작 오프셋(바이트)
    items = []
    chunks = 0
    written_total = 0

    # 1) 비할당 블록 걷어서 "연속 구간"으로 합치기
    ranges = []
    cur = None
    for blk in fs_info.block_walk(flags=pytsk3.TSK_FS_BLOCK_FLAG_UNALLOC):
        baddr = int(blk.addr)  # 블록 인덱스
        if cur and baddr == cur["end"]:
            cur["end"] += 1
        else:
            if cur:
                ranges.append(cur)
            cur = {"start": baddr, "end": baddr+1}
    if cur:
        ranges.append(cur)

    # 2) 각 연속 구간을 바이트 오프셋으로 변환 → 덤프
    def read_abs(off, size):
        return img_info.read(off, size)

    file_index = 0
    for r in ranges:
        abs_off = fs_off + r["start"] * bs
        size = (r["end"] - r["start"]) * bs
        remaining = size
        ptr = 0

        while remaining > 0:
            take = min(remaining, max_file_bytes)
            path = os.path.join(out_dir, f"{file_index:06d}.bin")
            with open(path, "wb") as f:
                buf = read_abs(abs_off + ptr, take)
                f.write(buf)
            items.append({
                "name": os.path.basename(path),
                "abs_offset": abs_off + ptr,
                "size": take
            })
            file_index += 1
            chunks += 1
            written_total += take
            ptr += take
            remaining -= take
            if overlap and remaining > 0:
                back = min(overlap, ptr)
                ptr -= back
                remaining += back

    # 3) 매니페스트/리포트 기록
    fs_manifest = {
        "block_size": bs,
        "fs_offset": fs_off,
        "chunks": chunks,
        "items": items
    }
    with open(os.path.join(out_dir, "fs_unalloc.json"), "w", encoding="utf-8") as f:
        json.dump(fs_manifest, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "fs_unalloc_report.json"), "w", encoding="utf-8") as f:
        json.dump({
            "block_size": bs,
            "chunks": chunks,
            "bytes": written_total,
            "items": items[:20]  # 미리보기
        }, f, ensure_ascii=False, indent=2)

    return {
        "chunks": chunks,
        "bytes": written_total,
        "meta": os.path.join(out_dir, "fs_unalloc.json")
    }
