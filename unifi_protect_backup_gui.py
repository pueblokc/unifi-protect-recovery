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
DEFAULT_BACKUP_PATH = "/srv/unifi-protect/backups"


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
        self.devices_found = {
            'cameras': 0,
            'bridges': 0,
            'lights': 0,
            'speakers': 0
        }

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

    def test_connection(self):
        """Test SSH connection to NVR"""
        if not PARAMIKO_AVAILABLE:
            messagebox.showerror("Error", "paramiko library is not installed")
            return

        if not self.validate_inputs():
            return

        self.clear_results()
        self.set_ui_state(False)
        self.update_status("Testing connection...", "blue")

        # Run in background thread
        thread = threading.Thread(target=self._test_connection_thread)
        thread.daemon = True
        thread.start()

    def _test_connection_thread(self):
        """Background thread for connection test"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                self.nvr_ip.get().strip(),
                username=self.username.get().strip(),
                password=self.password.get(),
                timeout=10
            )

            # Test if backup directory exists
            sftp = ssh.open_sftp()
            backup_path = self.backup_path.get().strip()

            try:
                files = sftp.listdir(backup_path)
                zip_files = [f for f in files if f.endswith('.zip')]

                self.root.after(0, lambda: self.log_message(f"Connected to {self.nvr_ip.get()}"))
                self.root.after(0, lambda: self.log_message(f"Backup directory: {backup_path}"))
                self.root.after(0, lambda: self.log_message(f"Found {len(zip_files)} backup file(s)"))

                if zip_files:
                    latest = sorted(zip_files)[-1]
                    self.root.after(0, lambda: self.log_message(f"Latest backup: {latest}"))
                    self.root.after(0, lambda: self.update_status("Connection successful!", "green"))
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Success",
                        f"Connection successful!\n\nFound {len(zip_files)} backup file(s)\nLatest: {latest}"
                    ))
                else:
                    self.root.after(0, lambda: self.update_status("Connected, but no backups found", "orange"))
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Warning",
                        "Connected successfully, but no backup ZIP files found.\n\n"
                        "Make sure automatic backups are enabled in UniFi Protect."
                    ))
            except FileNotFoundError:
                self.root.after(0, lambda: self.update_status("Backup directory not found", "red"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Error",
                    f"Backup directory not found: {backup_path}\n\n"
                    "Please check the backup path setting."
                ))
            finally:
                sftp.close()
                ssh.close()

        except paramiko.AuthenticationException:
            self.root.after(0, lambda: self.update_status("Authentication failed", "red"))
            self.root.after(0, lambda: messagebox.showerror(
                "Error",
                "Authentication failed.\n\nPlease check your username and password."
            ))
        except Exception as e:
            self.root.after(0, lambda: self.update_status("Connection failed", "red"))
            self.root.after(0, lambda: messagebox.showerror("Error", f"Connection failed:\n\n{str(e)}"))
        finally:
            self.root.after(0, lambda: self.set_ui_state(True))

    def start_backup(self):
        """Start the backup process"""
        if not PARAMIKO_AVAILABLE:
            messagebox.showerror("Error", "paramiko library is not installed")
            return

        if not self.validate_inputs():
            return

        # Save config for next time
        self.save_config()

        self.clear_results()
        self.set_ui_state(False)
        self.update_status("Starting backup...", "blue")

        # Run in background thread
        thread = threading.Thread(target=self._backup_thread)
        thread.daemon = True
        thread.start()

    def _backup_thread(self):
        """Background thread for backup operation"""
        try:
            # Connect to NVR
            self.root.after(0, lambda: self.log_message("Connecting to NVR..."))

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                self.nvr_ip.get().strip(),
                username=self.username.get().strip(),
                password=self.password.get(),
                timeout=30
            )

            self.root.after(0, lambda: self.log_message(f"Connected to {self.nvr_ip.get()}"))

            # Find latest backup
            sftp = ssh.open_sftp()
            backup_path = self.backup_path.get().strip()

            files = sftp.listdir(backup_path)
            zip_files = sorted([f for f in files if f.endswith('.zip')])

            if not zip_files:
                raise Exception("No backup files found")

            latest_backup = zip_files[-1]
            remote_file = f"{backup_path}/{latest_backup}"

            self.root.after(0, lambda: self.log_message(f"Found latest backup: {latest_backup}"))
            self.root.after(0, lambda: self.update_status("Downloading backup file...", "blue"))

            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                tmp_path = tmp.name

            self.root.after(0, lambda: self.log_message("Downloading backup file..."))
            sftp.get(remote_file, tmp_path)

            self.root.after(0, lambda: self.log_message("Download complete"))
            self.root.after(0, lambda: self.update_status("Extracting recovery codes...", "blue"))

            sftp.close()
            ssh.close()

            # Extract recovery codes
            self.root.after(0, lambda: self.log_message("Extracting recovery codes..."))
            devices = self.extract_recovery_codes(tmp_path)

            # Clean up temp file
            os.unlink(tmp_path)

            if not devices:
                raise Exception("Failed to extract recovery codes")

            # Count devices
            total = 0
            for device_type, device_list in devices.items():
                count = len(device_list)
                self.devices_found[device_type] = count
                total += count
                if count > 0:
                    self.root.after(0, lambda dt=device_type, c=count:
                        self.log_message(f"  {dt.title()}: {c}"))

            # Save to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(self.save_location.get()) / f"recovery_codes_{timestamp}.csv"

            self.save_to_csv(devices, str(output_file))

            self.root.after(0, lambda: self.log_message(""))
            self.root.after(0, lambda: self.log_message(f"Saved to: {output_file}"))

            # Update UI with success
            self.root.after(0, lambda: self.update_status(
                f"Backup complete! {total} devices saved.", "green"
            ))

            summary = f"Total: {total} devices ({self.devices_found['cameras']} cameras, " \
                      f"{self.devices_found['bridges']} bridges, " \
                      f"{self.devices_found['lights']} lights, " \
                      f"{self.devices_found['speakers']} speakers)"
            self.root.after(0, lambda: self.summary_label.configure(text=summary))

            self.root.after(0, lambda: messagebox.showinfo(
                "Backup Complete",
                f"Successfully backed up recovery codes!\n\n"
                f"Total devices: {total}\n"
                f"- Cameras: {self.devices_found['cameras']}\n"
                f"- Bridges: {self.devices_found['bridges']}\n"
                f"- Lights: {self.devices_found['lights']}\n"
                f"- Speakers: {self.devices_found['speakers']}\n\n"
                f"Saved to:\n{output_file}"
            ))

        except Exception as e:
            self.root.after(0, lambda: self.update_status("Backup failed", "red"))
            self.root.after(0, lambda: self.log_message(f"ERROR: {str(e)}"))
            self.root.after(0, lambda: messagebox.showerror("Backup Failed", str(e)))
        finally:
            self.root.after(0, lambda: self.set_ui_state(True))

    def extract_recovery_codes(self, backup_file):
        """Extract recovery codes from a UniFi Protect backup ZIP file"""
        devices = {
            'cameras': [],
            'bridges': [],
            'lights': [],
            'speakers': []
        }

        try:
            with zipfile.ZipFile(backup_file, 'r') as zip_ref:
                # Extract cameras
                if 'cameras.json' in zip_ref.namelist():
                    cameras_data = json.loads(zip_ref.read('cameras.json'))
                    for cam in cameras_data:
                        devices['cameras'].append({
                            'name': cam.get('name', 'Unknown'),
                            'model': cam.get('type', 'Unknown'),
                            'mac': cam.get('mac', 'N/A'),
                            'ip': cam.get('host', 'N/A'),
                            'recovery_code': cam.get('password', 'N/A')
                        })

                # Extract bridges
                if 'bridges.json' in zip_ref.namelist():
                    bridges_data = json.loads(zip_ref.read('bridges.json'))
                    for bridge in bridges_data:
                        devices['bridges'].append({
                            'name': bridge.get('name', 'Unknown'),
                            'model': bridge.get('type', 'Unknown'),
                            'mac': bridge.get('mac', 'N/A'),
                            'ip': bridge.get('host', 'N/A'),
                            'recovery_code': bridge.get('password', 'N/A')
                        })

                # Extract lights
                if 'lights.json' in zip_ref.namelist():
                    lights_data = json.loads(zip_ref.read('lights.json'))
                    for light in lights_data:
                        devices['lights'].append({
                            'name': light.get('name', 'Unknown'),
                            'model': light.get('type', 'Unknown'),
                            'mac': light.get('mac', 'N/A'),
                            'ip': light.get('host', 'N/A'),
                            'recovery_code': light.get('password', 'N/A')
                        })

                # Extract speakers
                if 'speakers.json' in zip_ref.namelist():
                    speakers_data = json.loads(zip_ref.read('speakers.json'))
                    for speaker in speakers_data:
                        devices['speakers'].append({
                            'name': speaker.get('name', 'Unknown'),
                            'model': speaker.get('type', 'Unknown'),
                            'mac': speaker.get('mac', 'N/A'),
                            'ip': speaker.get('host', 'N/A'),
                            'recovery_code': speaker.get('password', 'N/A')
                        })

        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error reading backup: {e}"))
            return None

        return devices

    def save_to_csv(self, devices, output_file):
        """Save recovery codes to CSV file"""
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Type', 'Name', 'Model', 'MAC', 'IP', 'Recovery Code']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for device_type, device_list in devices.items():
                for device in device_list:
                    writer.writerow({
                        'Type': device_type.rstrip('s').title(),
                        'Name': device['name'],
                        'Model': device['model'],
                        'MAC': device['mac'],
                        'IP': device['ip'],
                        'Recovery Code': device['recovery_code']
                    })


def main():
    root = tk.Tk()

    # Set app icon if available
    try:
        root.iconbitmap(default='')
    except:
        pass

    # Style configuration
    style = ttk.Style()
    if 'vista' in style.theme_names():
        style.theme_use('vista')
    elif 'clam' in style.theme_names():
        style.theme_use('clam')

    app = UniFiProtectBackupGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
