import csv
import json
import os
import stat
import sys

import pytest

import extract_recovery_codes as cli
from conftest import make_backup_zip


def test_extracts_every_device_type(backup_zip):
    devices = cli.extract_recovery_codes(str(backup_zip))
    assert set(devices) == set(cli.DEVICE_FILES)
    assert [d['name'] for d in devices['cameras']] == ['Front Door', 'Driveway']
    assert devices['viewers'][0]['recovery_code'] == 'EXAMPLE_CODE_dddddddd'
    assert devices['speakers'] == []  # absent file -> empty, not an error


def test_empty_strings_fall_back(backup_zip):
    devices = cli.extract_recovery_codes(str(backup_zip))
    assert devices['bridges'][0]['ip'] == 'N/A'
    light = devices['lights'][0]
    assert light['name'] == 'Unknown'
    assert light['recovery_code'] == 'N/A'


def test_nested_json_members_are_found(tmp_path):
    z = make_backup_zip(tmp_path / 'b.zip', prefix='backup/')
    devices = cli.extract_recovery_codes(str(z))
    assert len(devices['cameras']) == 2


def test_corrupt_backup_returns_none(tmp_path, capsys):
    bad = tmp_path / 'bad.zip'
    bad.write_bytes(b'not a zip')
    assert cli.extract_recovery_codes(str(bad)) is None
    assert 'Error reading backup file' in capsys.readouterr().err


def test_non_list_and_junk_entries_are_tolerated(tmp_path):
    z = make_backup_zip(tmp_path / 'b.zip', {
        'cameras.json': {'name': 'Solo', 'password': 'X'},
        'bridges.json': ['junk', 3, {'name': 'B', 'password': 'Y'}],
    })
    devices = cli.extract_recovery_codes(str(z))
    assert [d['name'] for d in devices['cameras']] == ['Solo']
    assert [d['name'] for d in devices['bridges']] == ['B']


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permissions')
def test_csv_is_owner_only(backup_zip, tmp_path):
    out = tmp_path / 'codes.csv'
    out.write_text('old')
    os.chmod(out, 0o644)
    cli.save_to_csv(cli.extract_recovery_codes(str(backup_zip)), str(out))
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600  # existing file tightened
    old_umask = os.umask(0o022)
    try:
        out2 = tmp_path / 'new.csv'
        cli.save_to_csv(cli.extract_recovery_codes(str(backup_zip)), str(out2))
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(os.stat(out2).st_mode) == 0o600


def test_csv_content_and_formula_guard(tmp_path):
    z = make_backup_zip(tmp_path / 'b.zip', {'cameras.json': [
        {'name': '=HYPERLINK("http://evil")', 'type': '+cmd', 'mac': 'M',
         'host': '192.0.2.1', 'password': '-starts-with-dash'},
        {'name': 'Has "quotes", commas', 'type': 'T', 'mac': 'M2',
         'host': '192.0.2.2', 'password': 'P2'},
    ]})
    out = tmp_path / 'o.csv'
    cli.save_to_csv(cli.extract_recovery_codes(str(z)), str(out))
    rows = list(csv.DictReader(out.open(encoding='utf-8')))
    assert rows[0]['Type'] == 'Camera'
    assert rows[0]['Name'] == '\'=HYPERLINK("http://evil")'
    assert rows[0]['Model'] == "'+cmd"
    # recovery codes are never modified, even if they look like formulas
    assert rows[0]['Recovery Code'] == '-starts-with-dash'
    assert rows[1]['Name'] == 'Has "quotes", commas'


def test_backup_sort_key_orders_by_timestamp_not_version():
    names = [
        'unifi_protect_backup.v6.9.0.20260101000000.zip',
        'unifi_protect_backup.v6.10.0.20260301000000.zip',
        'unifi_protect_backup.v6.10.0.20260201000000.zip',
    ]
    assert max(names, key=cli.backup_sort_key) == names[1]
    # plain name sort (old behaviour) got this wrong
    assert sorted(names)[-1] == names[0]


def test_backup_sort_key_short_dates():
    a = 'unifi_protect_backup.v6.2.0.20260521.zip'
    b = 'unifi_protect_backup.v6.1.9.20260520235959.zip'
    assert max([a, b], key=cli.backup_sort_key) == a


def test_find_latest_backup_skips_missing_dirs(tmp_path):
    d = tmp_path / 'backups'
    d.mkdir()
    old = make_backup_zip(d / 'unifi_protect_backup.v6.9.0.20260101000000.zip')
    new = make_backup_zip(d / 'unifi_protect_backup.v6.10.0.20260301000000.zip')
    os.utime(old, (2_000_000_000, 2_000_000_000))  # newer mtime must not win over the name timestamp
    (d / 'notes.txt').write_text('x')
    found = cli.find_latest_backup([str(tmp_path / 'missing'), str(d)])
    assert found == str(new)
    assert cli.find_latest_backup([str(tmp_path / 'missing')]) is None


def test_main_exit_codes(tmp_path, backup_zip, capsys, monkeypatch):
    monkeypatch.setattr(cli, 'CANDIDATE_BACKUP_DIRS', [str(tmp_path / 'nope')])
    assert cli.main([]) == 1
    assert cli.main([str(backup_zip), 'xml']) == 2
    bad = tmp_path / 'bad.zip'
    bad.write_bytes(b'x')
    assert cli.main([str(bad)]) == 1
    capsys.readouterr()
    assert cli.main([str(backup_zip), 'json']) == 0
    data = json.loads(capsys.readouterr().out)  # stdout is pure JSON
    assert len(data['cameras']) == 2


def test_main_auto_selects_latest_and_keeps_json_clean(tmp_path, capsys, monkeypatch):
    d = tmp_path / 'b'
    d.mkdir()
    make_backup_zip(d / 'unifi_protect_backup.v6.2.0.20260521000000.zip')
    monkeypatch.setattr(cli, 'CANDIDATE_BACKUP_DIRS', [str(d)])
    assert cli.main(['', 'json']) == 0
    out = capsys.readouterr()
    json.loads(out.out)
    assert 'Using latest backup' in out.err


def test_main_csv_custom_path(tmp_path, backup_zip):
    out = tmp_path / 'x.csv'
    assert cli.main([str(backup_zip), 'csv', str(out)]) == 0
    assert len(list(csv.DictReader(out.open()))) == 5
    assert cli.main([str(backup_zip), 'csv', str(tmp_path / 'no' / 'dir.csv')]) == 1


def test_text_output(backup_zip, capsys):
    cli.print_recovery_codes(cli.extract_recovery_codes(str(backup_zip)))
    out = capsys.readouterr().out
    assert 'CAMERAS:' in out and 'Total cameras: 2' in out
    assert 'SPEAKERS:' not in out


def test_script_runs_as_subprocess(backup_zip):
    import subprocess
    r = subprocess.run([sys.executable, cli.__file__, str(backup_zip), 'json'],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)['bridges'][0]['name'] == 'Garage'
