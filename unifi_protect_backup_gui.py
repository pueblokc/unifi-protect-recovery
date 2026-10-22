#!/usr/bin/env python3
"""
UniFi Protect Recovery Code Backup GUI
A portable GUI application to backup device recovery codes from any UniFi NVR.

Requirements:
- Python 3.6+
- paramiko (pip install paramiko)

Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
License: MIT
"""

__author__ = "KCCS <info@kccsonline.com>"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2026 KCCS - kccsonline.com"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import zipfile
import os
import csv
import re
import stat
import threading
import tempfile
from datetime import datetime
from pathlib import Path

# Try to import paramiko, show helpful error if not available
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

# Configuration file location
CONFIG_FILE = Path(__file__).parent / "config.json"
# SSH host keys seen on first connect (trust-on-first-use). A later key
# mismatch for the same NVR aborts the connection instead of silently
# sending the root password to whoever answered.
KNOWN_HOSTS_FILE = Path(__file__).parent / "known_hosts"
DEFAULT_BACKUP_PATH = "/srv/unifi-protect/backups"

# UniFi Protect writes its automatic backups to different locations depending on
# the console model and firmware. We probe the user-supplied path first, then
# fall back through these known locations (verified on UNVR / UniFi OS consoles).
CANDIDATE_BACKUP_PATHS = [
    "/srv/unifi-protect/backups",
    "/etc/unifi-protect/backups",
    "/data/unifi-core/backups",
    "/data/unifi-protect/backups",
]

# Every adoptable UniFi Protect device stores its recovery code in the
# "password" field of its per-type JSON file inside the backup ZIP. Keep this
# list complete — a missing entry silently drops those devices' recovery codes.
DEVICE_FILES = {
    'cameras':  'cameras.json',
    'bridges':  'bridges.json',
    'lights':   'lights.json',
    'speakers': 'speakers.json',
    'aiports':  'aiports.json',
    'sirens':   'sirens.json',
    'viewers':  'viewers.json',
}


def device_record(d):
    """Build a normalized recovery record. `or` (not dict default) so empty
    strings fall back too — e.g. bridges often have an empty `host`."""
    return {
        'name': d.get('name') or 'Unknown',
        'model': d.get('type') or 'Unknown',
        'mac': d.get('mac') or 'N/A',
        'ip': d.get('host') or 'N/A',
        'recovery_code': d.get('password') or 'N/A',
    }


# Protect backups are named unifi_protect_backup.v<ver>.<YYYYMMDD[HHMMSS]>.zip.
# The version comes *before* the timestamp, so a plain name sort is wrong
# (v6.10 < v6.9, and a downgrade sorts below older backups). Sort on the
# trailing timestamp, then the file mtime, then the name.
_BACKUP_TS_RE = re.compile(r'(\d{8,14})\.zip$', re.IGNORECASE)


def backup_sort_key(name, mtime=0):
    m = _BACKUP_TS_RE.search(name)
    ts = m.group(1).ljust(14, '0') if m else ''
    return (ts, mtime or 0, name)


def candidate_paths(configured_path):
    """Configured path first, then the known fallback locations (de-duped)."""
    paths = []
    if configured_path:
        paths.append(configured_path)
    for p in CANDIDATE_BACKUP_PATHS:
        if p not in paths:
            paths.append(p)
    return paths


def find_backup_dir(sftp, configured_path):
    """Probe the configured path, then fall back through known locations.

    Returns (path, zip_files) with zip_files ordered oldest -> newest:
      - (path, [..zips..]) when a directory containing .zip backups is found
      - (first_existing_dir, [])  when a backup dir exists but holds no zips
      - (None, [])  when none of the candidate directories exist at all
    """
    first_existing = None
    for path in candidate_paths(configured_path):
        try:
            entries = sftp.listdir_attr(path)
        except IOError:
            continue  # directory does not exist on this console; try next
        if first_existing is None:
            first_existing = path
        zips = [e for e in entries
                if e.filename.lower().endswith('.zip')
                and not stat.S_ISDIR(e.st_mode or 0)]
        if zips:
            zips.sort(key=lambda e: backup_sort_key(e.filename, e.st_mtime))
            return path, [e.filename for e in zips]
    return first_existing, []


def _find_member(names, fname):
    """Exact top-level match first, else the first entry with that basename
    (in case a firmware nests the JSON files in a folder)."""
    if fname in names:
        return fname
    for n in names:
        if n.rsplit('/', 1)[-1] == fname:
            return n
    return None


def extract_devices(backup_file):
    """Read every device type's recovery codes from a Protect backup ZIP.
    Raises on a corrupt/unreadable backup."""
    devices = {k: [] for k in DEVICE_FILES}
    with zipfile.ZipFile(backup_file, 'r') as zip_ref:
        names = zip_ref.namelist()
        for dtype, fname in DEVICE_FILES.items():
            member = _find_member(names, fname)
            if member is None:
                continue
            data = json.loads(zip_ref.read(member))
            if isinstance(data, dict):
                data = [data]
            for d in data:
                if isinstance(d, dict):
                    devices[dtype].append(device_record(d))
    return devices


def csv_safe(value):
    """Neutralise spreadsheet formula injection for free-text columns
    (device names come from the NVR and the CSV is meant to be opened in
    Excel). Recovery codes/MACs/IPs are never altered."""
    value = str(value)
    if value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def write_csv(devices, output_file):
    """Write recovery codes to CSV, readable only by the current user."""
    fd = os.open(str(output_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, 'fchmod'):
        os.fchmod(fd, 0o600)  # also tighten a pre-existing file
    with os.fdopen(fd, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Type', 'Name', 'Model', 'MAC', 'IP', 'Recovery Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for device_type, device_list in devices.items():
            for device in device_list:
                writer.writerow({
                    'Type': device_type.rstrip('s').title(),
                    'Name': csv_safe(device['name']),
                    'Model': csv_safe(device['model']),
                    'MAC': device['mac'],
                    'IP': device['ip'],
                    'Recovery Code': device['recovery_code']
                })


def make_ssh_client(known_hosts_file=KNOWN_HOSTS_FILE):
    """SSH client with trust-on-first-use host keys.

    Unknown hosts are accepted and remembered in `known_hosts_file`; a host
    whose key later changes raises paramiko.BadHostKeyException. Keys in the
    user's ~/.ssh/known_hosts are honoured too."""
    ssh = paramiko.SSHClient()
    try:
        ssh.load_system_host_keys()
    except Exception:
        pass
    try:
        Path(known_hosts_file).touch(mode=0o600, exist_ok=True)
        ssh.load_host_keys(str(known_hosts_file))
    except Exception:
        pass  # read-only install dir: fall back to in-memory TOFU
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return ssh


def host_key_error_message(host, known_hosts_file=KNOWN_HOSTS_FILE):
    return (
        f"The SSH host key for {host} has CHANGED since the last connection.\n\n"
        "This happens after replacing/factory-resetting the NVR, but it can "
        "also mean someone is intercepting the connection. Nothing was sent.\n\n"
        f"If the change is expected, delete the line for {host} from:\n"
        f"{known_hosts_file}\n(and ~/.ssh/known_hosts if present), then retry."
    )


class UniFiProtectBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UniFi Protect Recovery Code Backup")
        self.root.geometry("700x600")
        self.root.minsize(600, 500)

        # Variables
        self.nvr_ip = tk.StringVar()
        self.username = tk.StringVar(value="root")
        self.password = tk.StringVar()
        self.backup_path = tk.StringVar(value=DEFAULT_BACKUP_PATH)
        self.save_location = tk.StringVar(value=str(Path.home() / "Documents"))
        self.show_password = tk.BooleanVar(value=False)
        self.remember_settings = tk.BooleanVar(value=True)

        # Status tracking
        self.is_running = False
        self.devices_found = {k: 0 for k in DEVICE_FILES}

        # Load saved configuration
        self.load_config()

        # Build UI
        self.create_widgets()

        # Check for paramiko
        if not PARAMIKO_AVAILABLE:
            self.root.after(100, self.show_paramiko_warning)

    def show_paramiko_warning(self):
        messagebox.showwarning(
            "Missing Dependency",
            "The 'paramiko' library is required for SSH connections.\n\n"
            "Please install it by running:\n"
            "pip install paramiko\n\n"
            "The application will not work without this dependency."
        )

    def create_widgets(self):
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="UniFi Protect Recovery Code Backup",
            font=("Segoe UI", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 15))

        # === NVR Connection Settings ===
        connection_frame = ttk.LabelFrame(main_frame, text="NVR Connection", padding="10")
        connection_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        connection_frame.columnconfigure(1, weight=1)

        # NVR IP
        ttk.Label(connection_frame, text="NVR IP Address:").grid(row=0, column=0, sticky="w", pady=5)
        nvr_entry = ttk.Entry(connection_frame, textvariable=self.nvr_ip, width=30)
        nvr_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=5)

        # Username
        ttk.Label(connection_frame, text="Username:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(connection_frame, textvariable=self.username, width=30).grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=5
        )

        # Password
        ttk.Label(connection_frame, text="Password:").grid(row=2, column=0, sticky="w", pady=5)
        self.password_entry = ttk.Entry(
            connection_frame,
            textvariable=self.password,
            show="*",
            width=30
        )
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)

        # Show password checkbox
        ttk.Checkbutton(
            connection_frame,
            text="Show",
            variable=self.show_password,
            command=self.toggle_password_visibility
        ).grid(row=2, column=2, padx=(5, 0))

        # Backup path on server
        ttk.Label(connection_frame, text="Backup Path:").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(connection_frame, textvariable=self.backup_path, width=30).grid(
            row=3, column=1, sticky="ew", padx=(10, 0), pady=5
        )

        # === Output Settings ===
        output_frame = ttk.LabelFrame(main_frame, text="Output Settings", padding="10")
        output_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        output_frame.columnconfigure(1, weight=1)

        # Save location
        ttk.Label(output_frame, text="Save To:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(output_frame, textvariable=self.save_location, width=40).grid(
            row=0, column=1, sticky="ew", padx=(10, 5), pady=5
        )
        ttk.Button(output_frame, text="Browse...", command=self.browse_save_location).grid(
            row=0, column=2, pady=5
        )

        # Remember settings checkbox
        ttk.Checkbutton(
            output_frame,
            text="Remember settings for next time",
            variable=self.remember_settings
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=5)

        # === Action Buttons ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=15)

        self.test_btn = ttk.Button(
            button_frame,
            text="Test Connection",
            command=self.test_connection
        )
        self.test_btn.pack(side="left", padx=5)

        self.backup_btn = ttk.Button(
            button_frame,
            text="Backup Recovery Codes",
            command=self.start_backup,
            style="Accent.TButton"
        )
        self.backup_btn.pack(side="left", padx=5)

        # === Progress Section ===
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        # Progress bar
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Status label
        self.status_label = ttk.Label(progress_frame, text="Ready", foreground="gray")
        self.status_label.grid(row=1, column=0, sticky="w")

        # === Results Section ===
        results_frame = ttk.LabelFrame(main_frame, text="Results", padding="10")
        results_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # Results text area with scrollbar
        self.results_text = tk.Text(
            results_frame,
            height=10,
            wrap="word",
            font=("Consolas", 10)
        )
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)

        self.results_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Device count summary
        self.summary_label = ttk.Label(
            results_frame,
            text="",
            font=("Segoe UI", 10, "bold")
        )
        self.summary_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # === Footer (KCCS branding) ===
        footer_label = ttk.Label(
            main_frame,
            text="■  © 2026 KCCS  ·  kccsonline.com",
            foreground="gray",
            font=("Segoe UI", 8)
        )
        footer_label.grid(row=6, column=0, columnspan=3, pady=(10, 0))

    def toggle_password_visibility(self):
        if self.show_password.get():
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def browse_save_location(self):
        folder = filedialog.askdirectory(initialdir=self.save_location.get())
        if folder:
            self.save_location.set(folder)

    def load_config(self):
        """Load saved configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.nvr_ip.set(config.get('nvr_ip', ''))
                    self.username.set(config.get('username', 'root'))
                    self.backup_path.set(config.get('backup_path', DEFAULT_BACKUP_PATH))
                    self.save_location.set(config.get('save_location', str(Path.home() / "Documents")))
                    # Note: Password is NOT saved for security
            except Exception:
                pass  # Ignore config load errors

    def save_config(self):
        """Save configuration to file (excluding password)"""
        if self.remember_settings.get():
            config = {
                'nvr_ip': self.nvr_ip.get(),
                'username': self.username.get(),
                'backup_path': self.backup_path.get(),
                'save_location': self.save_location.get()
            }
            try:
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(config, f, indent=2)
            except Exception:
                pass  # Ignore config save errors

    def update_status(self, message, color="black"):
        """Update status label"""
        self.status_label.configure(text=message, foreground=color)
        self.root.update_idletasks()

    def log_message(self, message):
        """Add message to results text area"""
        self.results_text.insert("end", message + "\n")
        self.results_text.see("end")
        self.root.update_idletasks()

    def clear_results(self):
        """Clear results text area"""
        self.results_text.delete("1.0", "end")
        self.summary_label.configure(text="")

    def validate_inputs(self):
        """Validate user inputs"""
        if not self.nvr_ip.get().strip():
            messagebox.showerror("Error", "Please enter the NVR IP address")
            return False
        if not self.username.get().strip():
            messagebox.showerror("Error", "Please enter the username")
            return False
        if not self.password.get():
            messagebox.showerror("Error", "Please enter the password")
            return False
        if not self.backup_path.get().strip():
            messagebox.showerror("Error", "Please enter the backup path on the NVR")
            return False
        return True

    def set_ui_state(self, enabled):
        """Enable/disable UI elements during operation"""
        state = "normal" if enabled else "disabled"
        self.test_btn.configure(state=state)
        self.backup_btn.configure(state=state)

        if enabled:
            self.progress.stop()
        else:
            self.progress.start(10)

    def _snapshot_inputs(self):
        """Read Tk variables on the main thread; worker threads must not
        touch Tk objects (tkinter is not thread-safe)."""
        return {
            'host': self.nvr_ip.get().strip(),
            'username': self.username.get().strip(),
            'password': self.password.get(),
            'backup_path': self.backup_path.get().strip(),
            'save_location': self.save_location.get().strip(),
        }

    def _ui(self, func, *args):
        """Schedule func(*args) on the Tk main loop from a worker thread.
        Arguments are bound now, so callers never close over loop or
        exception variables that change/vanish before the callback runs."""
        self.root.after(0, lambda: func(*args))

    def test_connection(self):
        """Test SSH connection to NVR"""
        if not PARAMIKO_AVAILABLE:
            messagebox.showerror("Error", "paramiko library is not installed")
            return

        if not self.validate_inputs():
            return

        if self.is_running:
            return
        self.is_running = True

        params = self._snapshot_inputs()
        self.clear_results()
        self.set_ui_state(False)
        self.update_status("Testing connection...", "blue")

        # Run in background thread
        thread = threading.Thread(target=self._test_connection_thread, args=(params,))
        thread.daemon = True
        thread.start()

    def _candidate_paths(self, configured_path):
        """Configured path first, then the known fallback locations (de-duped)."""
        return candidate_paths(configured_path)

    def _find_backup_dir(self, sftp, configured_path):
        """See module-level find_backup_dir()."""
        return find_backup_dir(sftp, configured_path)

    def _finish(self):
        self.is_running = False
        self.set_ui_state(True)

    def _test_connection_thread(self, params):
        """Background thread for connection test"""
        host = params['host']
        ssh = None
        try:
            ssh = make_ssh_client()
            ssh.connect(
                host,
                username=params['username'],
                password=params['password'],
                timeout=10
            )

            # Probe the configured path, then known fallback locations
            sftp = ssh.open_sftp()
            configured = params['backup_path']
            tried = self._candidate_paths(configured)

            self._ui(self.log_message, f"Connected to {host}")

            try:
                found_path, zip_files = self._find_backup_dir(sftp, configured)

                if zip_files:
                    latest = zip_files[-1]
                    if found_path != configured:
                        # Found backups somewhere other than the configured path
                        self._ui(self.backup_path.set, found_path)
                        self._ui(self.log_message, f"Backups found in {found_path} (path updated)")
                    self._ui(self.log_message, f"Backup directory: {found_path}")
                    self._ui(self.log_message, f"Found {len(zip_files)} backup file(s)")
                    self._ui(self.log_message, f"Latest backup: {latest}")
                    self._ui(self.update_status, "Connection successful!", "green")
                    self._ui(messagebox.showinfo, "Success",
                             f"Connection successful!\n\nFound {len(zip_files)} backup file(s) in:\n"
                             f"{found_path}\nLatest: {latest}")
                elif found_path is not None:
                    # A backup directory exists but contains no .zip files
                    self._ui(self.update_status, "Connected, but no backups found", "orange")
                    self._ui(self.log_message,
                             f"Backup directory {found_path} exists but contains no .zip files")
                    self._ui(messagebox.showwarning, "No backups found",
                             "Connected successfully, but no backup ZIP files were found.\n\n"
                             "Paths checked:\n  " + "\n  ".join(tried) + "\n\n"
                             "Most likely automatic backups are not enabled yet. In the UniFi "
                             "Protect web UI go to:\n"
                             "  Settings -> System -> Backups\n"
                             "enable Automatic Backups, then wait for the nightly run (~midnight).")
                else:
                    # None of the candidate directories exist on this console
                    self._ui(self.update_status, "Backup directory not found", "red")
                    self._ui(self.log_message, "No backup directory found. Checked: " + ", ".join(tried))
                    self._ui(messagebox.showerror, "Backup directory not found",
                             "Connected, but no UniFi Protect backup directory was found.\n\n"
                             "Paths checked:\n  " + "\n  ".join(tried) + "\n\n"
                             "If your console stores backups elsewhere, set the correct path in "
                             "the 'Backup path' field. Otherwise enable Automatic Backups under "
                             "Settings -> System -> Backups in the Protect UI.")
            finally:
                sftp.close()

        except paramiko.AuthenticationException:
            self._ui(self.update_status, "Authentication failed", "red")
            self._ui(messagebox.showerror, "Error",
                     "Authentication failed.\n\nPlease check your username and password.")
        except paramiko.BadHostKeyException:
            self._ui(self.update_status, "Host key changed - connection refused", "red")
            self._ui(messagebox.showerror, "Host key mismatch", host_key_error_message(host))
        except Exception as e:
            self._ui(self.update_status, "Connection failed", "red")
            self._ui(messagebox.showerror, "Error", f"Connection failed:\n\n{e}")
        finally:
            if ssh is not None:
                ssh.close()
            self._ui(self._finish)

    def start_backup(self):
        """Start the backup process"""
        if not PARAMIKO_AVAILABLE:
            messagebox.showerror("Error", "paramiko library is not installed")
            return

        if not self.validate_inputs():
            return

        if self.is_running:
            return
        self.is_running = True

        # Save config for next time
        self.save_config()

        params = self._snapshot_inputs()
        self.clear_results()
        self.set_ui_state(False)
        self.update_status("Starting backup...", "blue")

        # Run in background thread
        thread = threading.Thread(target=self._backup_thread, args=(params,))
        thread.daemon = True
        thread.start()

    def _backup_thread(self, params):
        """Background thread for backup operation"""
        host = params['host']
        ssh = None
        tmp_path = None
        try:
            # Connect to NVR
            self._ui(self.log_message, "Connecting to NVR...")

            ssh = make_ssh_client()
            ssh.connect(
                host,
                username=params['username'],
                password=params['password'],
                timeout=30
            )

            self._ui(self.log_message, f"Connected to {host}")

            # Find latest backup (probe configured path, then known locations)
            sftp = ssh.open_sftp()
            try:
                configured = params['backup_path']
                backup_path, zip_files = self._find_backup_dir(sftp, configured)

                if not zip_files:
                    tried = ", ".join(self._candidate_paths(configured))
                    raise Exception(
                        "No backup ZIP files found. Checked: " + tried + ".\n"
                        "Enable Automatic Backups under Settings -> System -> Backups "
                        "in the UniFi Protect UI, then wait for the nightly run."
                    )

                if backup_path != configured:
                    self._ui(self.backup_path.set, backup_path)
                    self._ui(self.log_message, f"Using backup directory: {backup_path} (path updated)")

                latest_backup = zip_files[-1]
                remote_file = f"{backup_path.rstrip('/')}/{latest_backup}"

                self._ui(self.log_message, f"Found latest backup: {latest_backup}")
                self._ui(self.update_status, "Downloading backup file...", "blue")

                # Download to temp file (the ZIP also holds the NVR's TLS
                # private key, so it is always removed in `finally`).
                fd, tmp_path = tempfile.mkstemp(suffix='.zip')
                os.close(fd)

                self._ui(self.log_message, "Downloading backup file...")
                sftp.get(remote_file, tmp_path)
            finally:
                sftp.close()
            ssh.close()
            ssh = None

            self._ui(self.log_message, "Download complete")
            self._ui(self.update_status, "Extracting recovery codes...", "blue")

            # Extract recovery codes
            self._ui(self.log_message, "Extracting recovery codes...")
            devices = self.extract_recovery_codes(tmp_path)

            if devices is None:
                raise Exception("Failed to extract recovery codes (backup file unreadable)")

            # Count devices
            total = 0
            for device_type, device_list in devices.items():
                count = len(device_list)
                self.devices_found[device_type] = count
                total += count
                if count > 0:
                    self._ui(self.log_message, f"  {device_type.title()}: {count}")

            # Save to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_dir = Path(params['save_location'] or (Path.home() / "Documents"))
            save_dir.mkdir(parents=True, exist_ok=True)
            output_file = save_dir / f"recovery_codes_{timestamp}.csv"

            self.save_to_csv(devices, str(output_file))

            self._ui(self.log_message, "")
            self._ui(self.log_message, f"Saved to: {output_file}")

            # Build the per-type breakdown generically so new device types
            # always appear without code changes.
            present = [(dt, self.devices_found[dt]) for dt in DEVICE_FILES
                       if self.devices_found.get(dt, 0) > 0]
            summary = f"Total: {total} devices (" + \
                      ", ".join(f"{c} {dt}" for dt, c in present) + ")"
            self.root.after(0, lambda: self.summary_label.configure(text=summary))

            if total == 0:
                self._ui(self.update_status, "Backup read, but it contained no devices", "orange")
                self._ui(messagebox.showwarning, "No devices found",
                         "The latest backup was read successfully but contained no "
                         "device recovery codes.\n\nAn empty CSV was saved to:\n"
                         f"{output_file}")
                return

            # Update UI with success
            self._ui(self.update_status, f"Backup complete! {total} devices saved.", "green")

            breakdown = "\n".join(f"- {dt.title()}: {c}" for dt, c in present)
            self._ui(messagebox.showinfo, "Backup Complete",
                     f"Successfully backed up recovery codes!\n\n"
                     f"Total devices: {total}\n"
                     f"{breakdown}\n\n"
                     f"Saved to:\n{output_file}")

        except paramiko.AuthenticationException:
            self._ui(self.update_status, "Authentication failed", "red")
            self._ui(self.log_message, "ERROR: Authentication failed")
            self._ui(messagebox.showerror, "Backup Failed",
                     "Authentication failed.\n\nPlease check your username and password.")
        except paramiko.BadHostKeyException:
            self._ui(self.update_status, "Host key changed - connection refused", "red")
            self._ui(self.log_message, "ERROR: NVR host key changed; connection refused")
            self._ui(messagebox.showerror, "Host key mismatch", host_key_error_message(host))
        except Exception as e:
            self._ui(self.update_status, "Backup failed", "red")
            self._ui(self.log_message, f"ERROR: {e}")
            self._ui(messagebox.showerror, "Backup Failed", str(e))
        finally:
            if ssh is not None:
                ssh.close()
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            self._ui(self._finish)

    def extract_recovery_codes(self, backup_file):
        """Extract recovery codes for every device type in a Protect backup ZIP.
        Returns None (and logs) if the backup can't be read."""
        try:
            return extract_devices(backup_file)
        except Exception as e:
            self._ui(self.log_message, f"Error reading backup: {e}")
            return None

    def save_to_csv(self, devices, output_file):
        """Save recovery codes to CSV file (mode 0600)"""
        write_csv(devices, output_file)


def main():
    root = tk.Tk()

    # Set app icon if available
    try:
        root.iconbitmap(default='')
    except Exception:
        pass

    # Style configuration
    style = ttk.Style()
    if 'vista' in style.theme_names():
        style.theme_use('vista')
    elif 'clam' in style.theme_names():
        style.theme_use('clam')

    UniFiProtectBackupGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
