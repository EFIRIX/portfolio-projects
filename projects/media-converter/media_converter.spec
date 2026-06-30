# media_converter.spec
block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.icns', '.')],
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Media Converter',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.icns',
)

app = BUNDLE(
    exe,
    name='Media Converter.app',
    icon='icon.icns',
    bundle_identifier='com.vibe.media_converter',
)
