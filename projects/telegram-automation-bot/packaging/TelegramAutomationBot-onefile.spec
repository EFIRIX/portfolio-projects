# Build on Windows from the project root:
#   pyinstaller --clean packaging\TelegramAutomationBot-onefile.spec
#
# This target intentionally does not bundle .env files. First-run setup stores
# secrets in the current Windows user's DPAPI-protected profile config.
from pathlib import Path

SPEC_BASE = Path(SPECPATH).resolve()
if (SPEC_BASE / "app" / "__main__.py").exists():
    ROOT = SPEC_BASE
elif (SPEC_BASE.parent / "app" / "__main__.py").exists():
    ROOT = SPEC_BASE.parent
else:
    ROOT = Path.cwd().resolve()
block_cipher = None

a = Analysis(
    [str(ROOT / "app" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "aiohttp_socks",
        "telethon",
        "services.archive",
        "services.network",
        "services.secure_config",
        "services.socks_feed",
        "services.mtproxy_feed",
        "services.mtproxy_runtime",
        "app.secure_setup",
        "app.config_import",
        "app.gui",
        "tkinter",
        "tkinter.ttk",
    ],
    hookspath=[],
    hooksconfig={},
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
    name="TelegramAutomationBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
