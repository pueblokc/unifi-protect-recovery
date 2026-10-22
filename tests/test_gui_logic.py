import csv
import os
import shutil
import stat
import types

import paramiko
import pytest

import extract_recovery_codes as cli
import unifi_protect_backup_gui as gui
from conftest import make_backup_zip


# ---------------------------------------------------------------- fakes --

class Attr:
    def __init__(self, filename, mtime=0, is_dir=False):
        self.filename = filename
        self.st_mtime = mtime
        self.st_mode = (stat.S_IFDIR if is_dir else stat.S_IFREG) | 0o644


class FakeSFTP:
    def __init__(self, tree, source_zip=None, fail_get=False):
        self.tree, self.source_zip, self.fail_get = tree, source_zip, fail_get
        self.closed = False
        self.downloaded_to = None

    def listdir_attr(self, path):
        if path not in self.tree:
            raise IOError(2, 'No such file')
        return self.tree[path]

    def get(self, remote, local):
        self.downloaded_to = local
        if self.fail_get:
            with open(local, 'wb') as f:
                f.write(b'partial')
            raise IOError('connection reset during download')
        shutil.copy(self.source_zip, local)

    def close(self):
        self.closed = True


class FakeSSH:
    def __init__(self, sftp=None, connect_exc=None):
        self.sftp, self.connect_exc = sftp, connect_exc
        self.closed = False

    def connect(self, host, **kw):
        if self.connect_exc:
            raise self.connect_exc

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


class Var:
    def __init__(self, v=''):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


@pytest.fixture
def app(monkeypatch, tmp_path):
    """A GUI instance with no Tk: after() runs callbacks immediately and
    widgets/dialogs are recorders."""
    a = gui.UniFiProtectBackupGUI.__new__(gui.UniFiProtectBackupGUI)
    a.root = types.SimpleNamespace(after=lambda ms, f: f(), update_idletasks=lambda: None)
    a.is_running = True
    a.devices_found = {k: 0 for k in gui.DEVICE_FILES}
    a.backup_path = Var('/srv/unifi-protect/backups')
    a.logs, a.statuses = [], []
    a.log_message = a.logs.append
    a.update_status = lambda msg, color='black': a.statuses.append((msg, color))
    a.set_ui_state = lambda enabled: None
    a.summary_label = Recorder()
    box = Recorder()
    monkeypatch.setattr(gui, 'messagebox', box)
    a.box = box
    return a


def params(tmp_path, **over):
    p = {'host': '192.0.2.40', 'username': 'root', 'password': 'pw',
         'backup_path': '/srv/unifi-protect/backups',
         'save_location': str(tmp_path / 'out')}
    p.update(over)
    return p



# ------------------------------------------------------------- parity --

def test_device_tables_match_cli():
    assert gui.DEVICE_FILES == cli.DEVICE_FILES
    d = {'name': '', 'type': 'X', 'mac': None, 'host': '', 'password': 'P'}
    assert gui.device_record(d) == cli.device_record(d)
    assert gui.backup_sort_key('a.v1.20260101.zip', 5) == cli.backup_sort_key('a.v1.20260101.zip', 5)


def test_extract_devices_matches_cli(backup_zip):
    assert gui.extract_devices(str(backup_zip)) == cli.extract_recovery_codes(str(backup_zip))


# ------------------------------------------------------ backup finding --

def test_candidate_paths_dedupes_and_orders():
    paths = gui.candidate_paths('/data/unifi-core/backups')
    assert paths[0] == '/data/unifi-core/backups'
    assert len(paths) == len(set(paths)) == len(gui.CANDIDATE_BACKUP_PATHS)
    assert gui.candidate_paths('') == gui.CANDIDATE_BACKUP_PATHS


def test_find_backup_dir_falls_back_and_sorts_newest_last():
    sftp = FakeSFTP({
        '/srv/unifi-protect/backups': [],  # exists, empty
        '/data/unifi-core/backups': [
            Attr('unifi_protect_backup.v6.10.0.20260301000000.zip', 1),
            Attr('unifi_protect_backup.v6.9.0.20260101000000.zip', 9),
            Attr('readme.txt'),
            Attr('weird.zip', is_dir=True),
        ],
    })
    path, zips = gui.find_backup_dir(sftp, '/srv/unifi-protect/backups')
    assert path == '/data/unifi-core/backups'
    assert zips[-1] == 'unifi_protect_backup.v6.10.0.20260301000000.zip'
    assert 'weird.zip' not in zips


def test_find_backup_dir_mtime_breaks_ties_for_unparseable_names():
    sftp = FakeSFTP({'/x': [Attr('b.zip', 100), Attr('a.zip', 200)]})
    assert gui.find_backup_dir(sftp, '/x')[1][-1] == 'a.zip'


def test_find_backup_dir_states():
    assert gui.find_backup_dir(FakeSFTP({}), '/x') == (None, [])
    assert gui.find_backup_dir(FakeSFTP({'/etc/unifi-protect/backups': []}), '/x') == \
        ('/etc/unifi-protect/backups', [])


# ------------------------------------------------------------- backup --

def test_backup_success_writes_csv_and_removes_temp(app, tmp_path, backup_zip, monkeypatch):
    sftp = FakeSFTP({'/srv/unifi-protect/backups': [Attr(backup_zip.name)]}, backup_zip)
    ssh = FakeSSH(sftp)
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: ssh)

    app._backup_thread(params(tmp_path))

    out = list((tmp_path / 'out').glob('recovery_codes_*.csv'))  # dir auto-created
    assert len(out) == 1
    rows = list(csv.DictReader(out[0].open(encoding='utf-8')))
    assert len(rows) == 5
    if os.name == 'posix':
        assert stat.S_IMODE(os.stat(out[0]).st_mode) == 0o600
    assert not os.path.exists(sftp.downloaded_to)
    assert sftp.closed and ssh.closed
    assert app.statuses[-1][1] == 'green'
    assert app.box.calls[-1][0] == 'showinfo'
    assert app.is_running is False


def test_backup_download_failure_shows_error_and_cleans_up(app, tmp_path, monkeypatch):
    """Regression: the except handler's lambdas referenced `e`, which Python 3
    unbinds after the except block -> NameError instead of an error dialog."""
    sftp = FakeSFTP({'/srv/unifi-protect/backups': [Attr('x.zip')]}, fail_get=True)
    ssh = FakeSSH(sftp)
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: ssh)

    app._backup_thread(params(tmp_path))

    name, args, _ = app.box.calls[-1]
    assert name == 'showerror'
    assert 'connection reset during download' in args[1]
    assert any('connection reset' in m for m in app.logs)
    # partial ZIP (recovery codes + TLS key) must not be left in %TEMP%
    assert not os.path.exists(sftp.downloaded_to)
    assert sftp.closed and ssh.closed
    assert app.is_running is False


def test_backup_corrupt_zip_reports_and_cleans_up(app, tmp_path, monkeypatch):
    bad = tmp_path / 'bad.zip'
    bad.write_bytes(b'not a zip')
    sftp = FakeSFTP({'/srv/unifi-protect/backups': [Attr('bad.zip')]}, bad)
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(sftp))
    app._backup_thread(params(tmp_path))
    assert app.box.calls[-1][0] == 'showerror'
    assert not os.path.exists(sftp.downloaded_to)
    assert not (tmp_path / 'out').exists() or not list((tmp_path / 'out').iterdir())


def test_backup_no_zips(app, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(FakeSFTP({})))
    app._backup_thread(params(tmp_path))
    name, args, _ = app.box.calls[-1]
    assert name == 'showerror' and 'No backup ZIP files found' in args[1]


def test_backup_auth_failure(app, tmp_path, monkeypatch):
    ssh = FakeSSH(connect_exc=paramiko.AuthenticationException('bad'))
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: ssh)
    app._backup_thread(params(tmp_path))
    assert 'Authentication failed' in app.box.calls[-1][1][1]
    assert ssh.closed


def test_backup_bad_host_key(app, tmp_path, monkeypatch):
    k1, k2 = paramiko.RSAKey.generate(1024), paramiko.RSAKey.generate(1024)
    ssh = FakeSSH(connect_exc=paramiko.BadHostKeyException('192.0.2.40', k2, k1))
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: ssh)
    app._backup_thread(params(tmp_path))
    assert app.box.calls[-1][1][0] == 'Host key mismatch'


def test_backup_zero_devices_warns(app, tmp_path, monkeypatch):
    empty = make_backup_zip(tmp_path / 'e.zip', {'nvr.json': {}})
    sftp = FakeSFTP({'/srv/unifi-protect/backups': [Attr('e.zip')]}, empty)
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(sftp))
    app._backup_thread(params(tmp_path))
    assert app.box.calls[-1][0] == 'showwarning'


def test_backup_updates_path_when_found_elsewhere(app, tmp_path, backup_zip, monkeypatch):
    sftp = FakeSFTP({'/data/unifi-core/backups': [Attr(backup_zip.name)]}, backup_zip)
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(sftp))
    app._backup_thread(params(tmp_path))
    assert app.backup_path.get() == '/data/unifi-core/backups'


# ---------------------------------------------------- test connection --

def test_connection_success_and_error_dialog(app, tmp_path, monkeypatch):
    sftp = FakeSFTP({'/srv/unifi-protect/backups': [Attr('a.v1.20260101.zip'), Attr('a.v1.20260102.zip')]})
    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(sftp))
    app._test_connection_thread(params(tmp_path))
    assert app.box.calls[-1][0] == 'showinfo'
    assert 'a.v1.20260102.zip' in app.box.calls[-1][1][1]

    monkeypatch.setattr(gui, 'make_ssh_client', lambda: FakeSSH(connect_exc=OSError('timed out')))
    app._test_connection_thread(params(tmp_path))
    name, args, _ = app.box.calls[-1]
    assert name == 'showerror' and 'timed out' in args[1]
    assert app.is_running is False


def test_connection_no_backups_warning(app, tmp_path, monkeypatch):
    monkeypatch.setattr(gui, 'make_ssh_client',
                        lambda: FakeSSH(FakeSFTP({'/srv/unifi-protect/backups': []})))
    app._test_connection_thread(params(tmp_path))
    assert app.box.calls[-1][0] == 'showwarning'


# ------------------------------------------------------- host keys --

def test_make_ssh_client_remembers_first_key_and_flags_change(tmp_path, monkeypatch):
    monkeypatch.setattr(paramiko.SSHClient, 'load_system_host_keys', lambda self, *a: None)
    kh = tmp_path / 'known_hosts'
    key = paramiko.RSAKey.generate(1024)

    c1 = gui.make_ssh_client(kh)
    c1._transport = types.SimpleNamespace(_log=lambda *a: None)  # policy logs via transport
    c1._policy.missing_host_key(c1, '192.0.2.40', key)
    if os.name == 'posix':
        assert stat.S_IMODE(os.stat(kh).st_mode) == 0o600

    c2 = gui.make_ssh_client(kh)
    stored = c2.get_host_keys().lookup('192.0.2.40')
    assert stored is not None
    assert stored[key.get_name()] == key
    other = paramiko.RSAKey.generate(1024)
    assert stored[key.get_name()] != other  # paramiko raises BadHostKeyException on this


def test_make_ssh_client_survives_unwritable_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paramiko.SSHClient, 'load_system_host_keys', lambda self, *a: None)
    c = gui.make_ssh_client(tmp_path / 'missing-dir' / 'known_hosts')
    assert isinstance(c._policy, paramiko.AutoAddPolicy)


def test_csv_safe():
    assert gui.csv_safe('=1+1') == "'=1+1"
    assert gui.csv_safe('@SUM') == "'@SUM"
    assert gui.csv_safe('Front Door') == 'Front Door'
    assert gui.csv_safe('') == ''
