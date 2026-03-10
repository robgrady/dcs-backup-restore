"""Main GUI application for DCS Backup & Restore."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .backup import create_backup, read_manifest_from_zip
from .dcs_paths import detect_dcs_paths, validate_dcs_path
from .models import (
    BackupCategory,
    BackupManifest,
    CATEGORY_LABELS,
    DeviceInfo,
    UUIDMapping,
)
from .restore import restore_backup
from .uuid_remapper import (
    auto_match_devices,
    detect_devices_from_log,
)
from .version import __version__


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"DCS Backup & Restore v{__version__}")
        self.geometry("800x700")
        self.minsize(700, 600)

        # State
        self.dcs_path: Path | None = None
        self._backup_manifest: BackupManifest | None = None
        self._current_devices: list[DeviceInfo] = []
        self._uuid_mapping_widgets: list[dict] = []

        self._build_ui()
        self._auto_detect_dcs()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        # DCS path row (shared across tabs)
        path_frame = ctk.CTkFrame(self, fg_color="transparent")
        path_frame.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(path_frame, text="DCS Folder:").pack(side="left")
        self.dcs_path_var = ctk.StringVar()
        self.dcs_path_entry = ctk.CTkEntry(
            path_frame, textvariable=self.dcs_path_var, width=480
        )
        self.dcs_path_entry.pack(side="left", padx=(8, 4), fill="x", expand=True)
        ctk.CTkButton(
            path_frame, text="Browse", width=80, command=self._browse_dcs_path
        ).pack(side="left")

        # Tabs
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.tabview.add("Backup")
        self.tabview.add("Restore")

        self._build_backup_tab(self.tabview.tab("Backup"))
        self._build_restore_tab(self.tabview.tab("Restore"))

    def _build_backup_tab(self, parent):
        # Destination
        dest_frame = ctk.CTkFrame(parent, fg_color="transparent")
        dest_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(dest_frame, text="Save to:").pack(side="left")
        self.backup_dest_var = ctk.StringVar()
        ctk.CTkEntry(
            dest_frame, textvariable=self.backup_dest_var, width=420
        ).pack(side="left", padx=(8, 4), fill="x", expand=True)
        ctk.CTkButton(
            dest_frame, text="Browse", width=80, command=self._browse_backup_dest
        ).pack(side="left")

        # Category checkboxes
        ctk.CTkLabel(parent, text="Include:", anchor="w").pack(
            fill="x", pady=(12, 4)
        )
        checkbox_frame = ctk.CTkFrame(parent, fg_color="transparent")
        checkbox_frame.pack(fill="x")

        self.backup_category_vars: dict[BackupCategory, ctk.BooleanVar] = {}
        for i, (cat, label) in enumerate(CATEGORY_LABELS.items()):
            var = ctk.BooleanVar(value=True)
            self.backup_category_vars[cat] = var
            ctk.CTkCheckBox(checkbox_frame, text=label, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=8, pady=2
            )

        # Backup button
        self.backup_btn = ctk.CTkButton(
            parent, text="Create Backup", command=self._on_backup, height=40
        )
        self.backup_btn.pack(pady=(16, 4))

        # Progress
        self.backup_progress = ctk.CTkProgressBar(parent)
        self.backup_progress.pack(fill="x", pady=(4, 2))
        self.backup_progress.set(0)

        self.backup_status = ctk.CTkLabel(parent, text="", anchor="w")
        self.backup_status.pack(fill="x")

        # Log
        self.backup_log = ctk.CTkTextbox(parent, height=120, state="disabled")
        self.backup_log.pack(fill="both", expand=True, pady=(4, 0))

    def _build_restore_tab(self, parent):
        # ZIP selection
        zip_frame = ctk.CTkFrame(parent, fg_color="transparent")
        zip_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(zip_frame, text="Backup:").pack(side="left")
        self.restore_zip_var = ctk.StringVar()
        ctk.CTkEntry(
            zip_frame, textvariable=self.restore_zip_var, width=420
        ).pack(side="left", padx=(8, 4), fill="x", expand=True)
        ctk.CTkButton(
            zip_frame, text="Browse", width=80, command=self._browse_restore_zip
        ).pack(side="left")

        # Manifest summary
        self.manifest_label = ctk.CTkLabel(
            parent, text="Select a backup ZIP to see its contents.", anchor="w"
        )
        self.manifest_label.pack(fill="x", pady=(4, 2))

        # Category checkboxes for restore
        self.restore_checkbox_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.restore_checkbox_frame.pack(fill="x")
        self.restore_category_vars: dict[BackupCategory, ctk.BooleanVar] = {}

        # UUID mapping section
        self.uuid_section_label = ctk.CTkLabel(
            parent, text="", anchor="w", font=ctk.CTkFont(weight="bold")
        )
        self.uuid_section_label.pack(fill="x", pady=(8, 2))

        self.uuid_scroll = ctk.CTkScrollableFrame(parent, height=140)
        self.uuid_scroll.pack(fill="x", pady=(0, 4))

        # Safety backup checkbox
        self.safety_backup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            parent,
            text="Create safety backup of current files before restoring",
            variable=self.safety_backup_var,
        ).pack(anchor="w", pady=(4, 2))

        # Restore button
        self.restore_btn = ctk.CTkButton(
            parent, text="Restore", command=self._on_restore, height=40
        )
        self.restore_btn.pack(pady=(8, 4))

        # Progress
        self.restore_progress = ctk.CTkProgressBar(parent)
        self.restore_progress.pack(fill="x", pady=(4, 2))
        self.restore_progress.set(0)

        self.restore_status = ctk.CTkLabel(parent, text="", anchor="w")
        self.restore_status.pack(fill="x")

        # Log
        self.restore_log = ctk.CTkTextbox(parent, height=100, state="disabled")
        self.restore_log.pack(fill="both", expand=True, pady=(4, 0))

    # ── DCS Path ─────────────────────────────────────────────────────

    def _auto_detect_dcs(self):
        paths = detect_dcs_paths()
        if paths:
            self.dcs_path = paths[0]
            self.dcs_path_var.set(str(paths[0]))
        else:
            self.dcs_path_var.set("(not found — use Browse)")

    def _browse_dcs_path(self):
        folder = filedialog.askdirectory(title="Select DCS Saved Games Folder")
        if folder:
            path = Path(folder)
            if validate_dcs_path(path):
                self.dcs_path = path
                self.dcs_path_var.set(str(path))
            else:
                messagebox.showwarning(
                    "Invalid Folder",
                    "This doesn't look like a DCS Saved Games folder.\n"
                    "Expected a 'Config' subdirectory.",
                )

    def _get_dcs_path(self) -> Path | None:
        """Get the current DCS path, validating from the text entry."""
        text = self.dcs_path_var.get().strip()
        if not text:
            return None
        path = Path(text)
        if validate_dcs_path(path):
            self.dcs_path = path
            return path
        return None

    # ── Backup Tab ───────────────────────────────────────────────────

    def _browse_backup_dest(self):
        folder = filedialog.askdirectory(title="Select Backup Destination")
        if folder:
            self.backup_dest_var.set(folder)

    def _on_backup(self):
        dcs_path = self._get_dcs_path()
        if not dcs_path:
            messagebox.showerror("Error", "Please select a valid DCS folder.")
            return

        dest_str = self.backup_dest_var.get().strip()
        if not dest_str:
            messagebox.showerror("Error", "Please select a backup destination folder.")
            return
        dest_dir = Path(dest_str)
        if not dest_dir.is_dir():
            messagebox.showerror("Error", "Backup destination folder does not exist.")
            return

        categories = [
            cat for cat, var in self.backup_category_vars.items() if var.get()
        ]
        if not categories:
            messagebox.showerror("Error", "Please select at least one category.")
            return

        self.backup_btn.configure(state="disabled")
        self.backup_progress.set(0)
        self._log_backup("Starting backup...")

        def run():
            try:
                zip_path = create_backup(
                    dcs_path, dest_dir, categories,
                    progress_callback=self._backup_progress,
                )
                self.after(0, lambda: self._backup_done(zip_path))
            except Exception as e:
                self.after(0, lambda: self._backup_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _backup_progress(self, current: int, total: int, filename: str):
        frac = current / total if total else 0
        self.after(0, lambda: self.backup_progress.set(frac))
        self.after(0, lambda: self.backup_status.configure(text=filename))

    def _backup_done(self, zip_path: Path):
        self.backup_btn.configure(state="normal")
        self.backup_progress.set(1.0)
        self.backup_status.configure(text="Done!")
        self._log_backup(f"Backup created: {zip_path}")
        messagebox.showinfo("Backup Complete", f"Saved to:\n{zip_path}")

    def _backup_error(self, msg: str):
        self.backup_btn.configure(state="normal")
        self.backup_status.configure(text="Error!")
        self._log_backup(f"ERROR: {msg}")
        messagebox.showerror("Backup Failed", msg)

    def _log_backup(self, text: str):
        self.backup_log.configure(state="normal")
        self.backup_log.insert("end", text + "\n")
        self.backup_log.configure(state="disabled")
        self.backup_log.see("end")

    # ── Restore Tab ──────────────────────────────────────────────────

    def _browse_restore_zip(self):
        file = filedialog.askopenfilename(
            title="Select Backup ZIP",
            filetypes=[("ZIP files", "*.zip")],
        )
        if file:
            self.restore_zip_var.set(file)
            self._load_manifest(Path(file))

    def _load_manifest(self, zip_path: Path):
        try:
            manifest = read_manifest_from_zip(zip_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read backup:\n{e}")
            return

        self._backup_manifest = manifest

        # Show summary
        version_str = manifest.dcs_version or "unknown"
        summary = (
            f"Backup from {manifest.timestamp} | "
            f"DCS version: {version_str} | "
            f"{len(manifest.files)} files"
        )
        self.manifest_label.configure(text=summary)

        # Build restore category checkboxes
        for widget in self.restore_checkbox_frame.winfo_children():
            widget.destroy()
        self.restore_category_vars.clear()

        backed_up_cats = set(manifest.categories)
        for i, (cat, label) in enumerate(CATEGORY_LABELS.items()):
            present = cat.value in backed_up_cats
            var = ctk.BooleanVar(value=present)
            self.restore_category_vars[cat] = var
            cb = ctk.CTkCheckBox(
                self.restore_checkbox_frame, text=label, variable=var
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=2)
            if not present:
                cb.configure(state="disabled")

        # UUID mapping section
        self._build_uuid_mapping(manifest)

    def _build_uuid_mapping(self, manifest: BackupManifest):
        # Clear existing widgets
        for widget in self.uuid_scroll.winfo_children():
            widget.destroy()
        self._uuid_mapping_widgets.clear()

        if not manifest.devices:
            self.uuid_section_label.configure(text="")
            return

        self.uuid_section_label.configure(text="Device UUID Mapping:")

        # Detect current devices from DCS log
        dcs_path = self._get_dcs_path()
        if dcs_path:
            self._current_devices = detect_devices_from_log(dcs_path)
        else:
            self._current_devices = []

        # Auto-match
        auto_mappings = auto_match_devices(manifest.devices, self._current_devices)
        auto_map = {m.old_uuid: m.new_uuid for m in auto_mappings}

        # Build dropdown options
        current_options = ["(keep original)"] + [
            f"{d.name} [{d.uuid[:8]}...]" for d in self._current_devices
        ]
        current_uuids = [None] + [d.uuid for d in self._current_devices]

        # Header row
        ctk.CTkLabel(self.uuid_scroll, text="Backup Device", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=4, pady=2, sticky="w"
        )
        ctk.CTkLabel(self.uuid_scroll, text="Remap To", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, padx=4, pady=2, sticky="w"
        )

        for i, dev in enumerate(manifest.devices):
            row = i + 1
            label_text = f"{dev.name} [{dev.uuid[:8]}...]"
            ctk.CTkLabel(self.uuid_scroll, text=label_text).grid(
                row=row, column=0, padx=4, pady=2, sticky="w"
            )

            combo_var = ctk.StringVar()
            combo = ctk.CTkComboBox(
                self.uuid_scroll, values=current_options,
                variable=combo_var, width=300, state="readonly"
            )

            # Set auto-matched value
            if dev.uuid in auto_map:
                new_uuid = auto_map[dev.uuid]
                for j, uid in enumerate(current_uuids):
                    if uid == new_uuid:
                        combo_var.set(current_options[j])
                        break
            else:
                combo_var.set(current_options[0])

            combo.grid(row=row, column=1, padx=4, pady=2, sticky="w")

            self._uuid_mapping_widgets.append({
                "device": dev,
                "combo_var": combo_var,
                "current_options": current_options,
                "current_uuids": current_uuids,
            })

    def _get_uuid_mappings(self) -> list[UUIDMapping]:
        """Read the UUID mapping selections from the UI."""
        mappings = []
        for w in self._uuid_mapping_widgets:
            selected = w["combo_var"].get()
            idx = w["current_options"].index(selected) if selected in w["current_options"] else 0
            new_uuid = w["current_uuids"][idx]
            if new_uuid and new_uuid != w["device"].uuid:
                mappings.append(UUIDMapping(
                    device_name=w["device"].name,
                    old_uuid=w["device"].uuid,
                    new_uuid=new_uuid,
                ))
        return mappings

    def _on_restore(self):
        dcs_path = self._get_dcs_path()
        if not dcs_path:
            messagebox.showerror("Error", "Please select a valid DCS folder.")
            return

        zip_str = self.restore_zip_var.get().strip()
        if not zip_str:
            messagebox.showerror("Error", "Please select a backup ZIP file.")
            return
        zip_path = Path(zip_str)

        categories = [
            cat for cat, var in self.restore_category_vars.items() if var.get()
        ]
        if not categories:
            messagebox.showerror("Error", "Please select at least one category.")
            return

        uuid_mappings = self._get_uuid_mappings()
        do_safety = self.safety_backup_var.get()

        # Confirm
        msg = f"Restore {len(categories)} categories to:\n{dcs_path}"
        if uuid_mappings:
            msg += f"\n\nWith {len(uuid_mappings)} UUID remap(s)."
        if do_safety:
            msg += "\n\nA safety backup will be created first."
        if not messagebox.askyesno("Confirm Restore", msg):
            return

        self.restore_btn.configure(state="disabled")
        self.restore_progress.set(0)
        self._log_restore("Starting restore...")

        def run():
            try:
                safety_path = restore_backup(
                    zip_path, dcs_path, categories,
                    uuid_mappings=uuid_mappings,
                    do_safety_backup=do_safety,
                    progress_callback=self._restore_progress,
                )
                self.after(0, lambda: self._restore_done(safety_path))
            except Exception as e:
                self.after(0, lambda: self._restore_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _restore_progress(self, current: int, total: int, filename: str):
        frac = current / total if total else 0
        self.after(0, lambda: self.restore_progress.set(frac))
        self.after(0, lambda: self.restore_status.configure(text=filename))

    def _restore_done(self, safety_path: Path | None):
        self.restore_btn.configure(state="normal")
        self.restore_progress.set(1.0)
        self.restore_status.configure(text="Done!")
        msg = "Restore complete!"
        if safety_path:
            msg += f"\n\nSafety backup at:\n{safety_path}"
            self._log_restore(f"Safety backup: {safety_path}")
        self._log_restore("Restore complete.")
        messagebox.showinfo("Restore Complete", msg)

    def _restore_error(self, msg: str):
        self.restore_btn.configure(state="normal")
        self.restore_status.configure(text="Error!")
        self._log_restore(f"ERROR: {msg}")
        messagebox.showerror("Restore Failed", msg)

    def _log_restore(self, text: str):
        self.restore_log.configure(state="normal")
        self.restore_log.insert("end", text + "\n")
        self.restore_log.configure(state="disabled")
        self.restore_log.see("end")
