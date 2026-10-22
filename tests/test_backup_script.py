"""Runs backup_recovery_codes.sh against a fake Protect backup dir."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT, make_backup_zip

pytestmark = pytest.mark.skipif(os.name != 'posix' or not shutil.which('bash'),
                                reason='needs bash')


def run(tmp_path):
    env = dict(os.environ,
               PROTECT_BACKUP_DIR=str(tmp_path / 'protect'),
               BACKUP_DIR=str(tmp_path / 'out'),
               CSV_FILE=str(tmp_path / 'codes.csv'))
    return subprocess.run(['bash', str(ROOT / 'backup_recovery_codes.sh')],
                          env=env, capture_output=True, text=True)


def test_success_creates_private_dated_copy(tmp_path):
    (tmp_path / 'protect').mkdir()
    make_backup_zip(tmp_path / 'protect' / 'unifi_protect_backup.v6.2.0.20260521000000.zip')
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'Total devices: 5' in r.stdout
    out = tmp_path / 'out'
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o700
    dated = [p for p in out.glob('recovery_codes_2*.csv')]
    assert len(dated) == 1
    assert stat.S_IMODE(os.stat(dated[0]).st_mode) == 0o600
    latest = out / 'recovery_codes_latest.csv'
    assert latest.is_symlink() and Path(os.path.realpath(latest)) == dated[0].resolve()


def test_failed_extraction_does_not_reuse_stale_csv(tmp_path):
    """Regression: the old script copied the previous run's CSV forward and
    reported success when extraction failed."""
    (tmp_path / 'protect').mkdir()
    (tmp_path / 'protect' / 'unifi_protect_backup.v6.2.0.20260521000000.zip').write_bytes(b'corrupt')
    (tmp_path / 'codes.csv').write_text('Type,Name\nCamera,STALE\n')
    r = run(tmp_path)
    assert r.returncode == 1
    assert 'successfully' not in r.stdout
    assert not (tmp_path / 'codes.csv').exists()
    assert not list((tmp_path / 'out').glob('recovery_codes_2*.csv'))


def test_no_backups(tmp_path):
    (tmp_path / 'protect').mkdir()
    r = run(tmp_path)
    assert r.returncode == 1
    assert 'No UniFi Protect backup files found' in r.stdout
