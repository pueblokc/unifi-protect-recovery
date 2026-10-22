"""Shared fixtures. No NVR, network or display is needed: SSH/SFTP are faked
and tkinter is stubbed when the interpreter was built without it."""
import io
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub_tkinter():
    tk = types.ModuleType('tkinter')
    for name in ('Tk', 'StringVar', 'BooleanVar', 'Text'):
        setattr(tk, name, type(name, (), {'__init__': lambda self, *a, **k: None}))
    ttk = types.ModuleType('tkinter.ttk')
    filedialog = types.ModuleType('tkinter.filedialog')
    messagebox = types.ModuleType('tkinter.messagebox')
    for fn in ('showinfo', 'showwarning', 'showerror'):
        setattr(messagebox, fn, lambda *a, **k: None)
    tk.ttk, tk.filedialog, tk.messagebox = ttk, filedialog, messagebox
    sys.modules.update({'tkinter': tk, 'tkinter.ttk': ttk,
                        'tkinter.filedialog': filedialog,
                        'tkinter.messagebox': messagebox})


try:
    import tkinter  # noqa: F401
except ImportError:
    _stub_tkinter()


# Fake but realistic Protect data. RFC 5737 IPs, locally-administered MACs,
# obviously fake codes.
SAMPLE = {
    'cameras.json': [
        {'name': 'Front Door', 'type': 'UVC G4 Bullet', 'mac': '02005E100001',
         'host': '192.0.2.11', 'password': 'EXAMPLE_CODE_aaaaaaaa'},
        {'name': 'Driveway', 'type': 'UVC G6 Bullet', 'mac': '02005E100002',
         'host': '192.0.2.12', 'password': 'EXAMPLE_CODE_bbbbbbbb'},
    ],
    'bridges.json': [
        {'name': 'Garage', 'type': 'UFP-UAP-B', 'mac': '02005E100003',
         'host': '', 'password': 'EXAMPLE_CODE_cccccccc'},
    ],
    'lights.json': [
        {'name': '', 'type': 'UP FloodLight', 'mac': '02005E100004',
         'host': '192.0.2.14', 'password': ''},
    ],
    'viewers.json': [
        {'name': 'Lobby', 'type': 'UP Viewport', 'mac': '02005E100005',
         'host': '192.0.2.15', 'password': 'EXAMPLE_CODE_dddddddd'},
    ],
    'nvr.json': {'name': 'not a device'},
}


def make_backup_zip(path, files=None, prefix=''):
    files = SAMPLE if files is None else files
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            payload = data if isinstance(data, (bytes, str)) else json.dumps(data)
            z.writestr(prefix + name, payload)
    return path


@pytest.fixture
def backup_zip(tmp_path):
    return make_backup_zip(tmp_path / 'unifi_protect_backup.v6.2.0.20260521000000.zip')


@pytest.fixture
def capture():
    return io.StringIO()
