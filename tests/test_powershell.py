"""Runs the PowerShell helper checks when pwsh/powershell is installed."""
import shutil
import subprocess

import pytest

from conftest import ROOT

PWSH = shutil.which('pwsh') or shutil.which('powershell')


@pytest.mark.skipif(not PWSH, reason='PowerShell not installed')
def test_powershell_helpers():
    r = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File',
                        str(ROOT / 'tests' / 'powershell' / 'Test-Functions.ps1')],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
