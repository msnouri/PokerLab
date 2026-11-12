# PyInstaller recipe:  pyinstaller packaging/pokerlab.spec --noconfirm
# Produces dist/PokerLab (folder) everywhere and dist/PokerLab.app on macOS.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / 'poker_lab'))

datas = [
    (str(ROOT / 'desktop' / 'qml'), 'desktop/qml'),
    (str(ROOT / 'desktop' / 'assets'), 'desktop/assets'),
    (str(ROOT / 'desktop' / 'mac_compatibility.json'), 'desktop'),
    (str(ROOT / 'poker_lab' / 'pokerlab' / 'preflop.json'), 'pokerlab'),
    (str(ROOT / 'poker_lab' / 'pokerlab' / 'research' / 'blueprints.json'), 'pokerlab/research'),
    (str(ROOT / 'poker_lab' / 'pokerlab' / 'library' / 'pushfold.json'), 'pokerlab/library'),
]
# Policies are loaded by name at run time, so list every module explicitly.
hidden = (collect_submodules('desktop') + collect_submodules('pokerlab') + collect_submodules('eval7')
          + ['pokerkit', 'numpy', 'platformdirs'])

a = Analysis(
    [str(ROOT / 'packaging' / 'pokerlab_app.py')],
    pathex=[str(ROOT), str(ROOT / 'poker_lab')],
    datas=datas,
    hiddenimports=hidden,
    excludes=['matplotlib', 'scipy', 'tkinter'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PokerLab', console=False,
          target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, name='PokerLab')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='PokerLab.app', bundle_identifier='io.github.msnouri.pokerlab',
                 info_plist={
                     'CFBundleShortVersionString': '0.2.0',
                     'NSHighResolutionCapable': True,
                     'LSMinimumSystemVersion': '13.0',
                     'NSScreenCaptureUsageDescription':
                         'Vision Studio reads the table window you choose. Nothing leaves this Mac.',
                 })
