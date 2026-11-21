"""Choose native capture without importing another platform's frameworks."""
import sys


def backend():
    if sys.platform == 'darwin':
        from . import mac_capture
        return mac_capture
    if sys.platform.startswith('linux'):
        from . import linux_capture
        return linux_capture
    raise RuntimeError('Live capture supports macOS and Linux. Use replay or Agent Lab on this platform.')


def controls():
    if sys.platform == 'darwin':
        return dict(supported=True, portal=False, label='Mac screen', platform='macOS',
                    help='Capture the window you select. Preview and recordings stay on this computer.',
                    permissionLabel='Allow Screen Recording', refreshLabel='Refresh Mac windows',
                    startLabel='Start selected window')
    if sys.platform.startswith('linux'):
        from .linux_capture import is_wayland
        portal = is_wayland()
        return dict(supported=True, portal=portal, label='Linux screen', platform='Linux',
                    help=('Wayland uses your desktop sharing picker. Choose a window if offered, or a screen containing only the table.' if portal else
                          'X11 captures the window you select. Preview and recordings stay on this computer.'),
                    permissionLabel='Check capture access',
                    refreshLabel='Find sharing source' if portal else 'Refresh X11 windows',
                    startLabel='Choose in desktop picker' if portal else 'Start selected window')
    return dict(supported=False, portal=False, label='Screen recording', platform='Desktop',
                help='Live capture supports macOS and Linux. Images and replays work here.',
                permissionLabel='Capture unavailable', refreshLabel='Refresh sources', startLabel='Start capture')
