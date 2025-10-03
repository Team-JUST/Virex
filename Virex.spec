import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

binaries = [
    ('bin/ffmpeg.exe', 'bin'),
    ('bin/ffprobe.exe', 'bin'),
]

# 필요하면 데이터/아이콘 추가
datas = [
    # ('dist/titleIcon.ico', 'dist'),
]

hiddenimports = collect_submodules('python_engine')

a = Analysis(
    ['python_engine/main.py'],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    name='Virex',
    console=False,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='Virex'
)