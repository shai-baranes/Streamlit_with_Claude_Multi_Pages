import os
import re
import queue
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import scrolledtext

import numpy as np
import pandas as pd
from tkinterdnd2 import TkinterDnD, DND_FILES


APPLICABLE_COLS = [
    'col_1', 'col_2', 'col_3', 'col_4', 'col_5',
    'col_6', 'col_7', 'col_8', 'col_9', 'col_10',
    'col_11', 'col_12', 'col_13', 'col_14', 'col_15',
    'col_16', 'col_17', 'col_18', 'col_19', 'col_20'
]

ERRORS_COLS = [
    'cole_1', 'cole_1', 'cole_1', 'cole_1', 'cole_1',
    'cole_1', 'cole_1', 'cole_1', 'cole_1', 'cole_1',
    'cole_1', 'cole_1', 'cole_1', 'cole_1', 'cole_1'
]

APPLICABLE_COLS = APPLICABLE_COLS + ERRORS_COLS





# -------

def skip_rows(source_file: Path) -> int:
    i = 0
    with source_file.open('r') as f:
        first_line = next(f)
        if "," not in first_line or ",," in first_line:
            for line in f:
                if "," not in line or ",," in line or line == "\n":
                    i += 1
                else:
                    break
    return i


def col_strip(column: str) -> str:
    parts = [p.strip() for p in re.split(r'[\\/]+', column.strip()) if p.strip()]
    return parts[-1] if parts else column


def drop_zero_na_columns(df, column_list):
    columns_to_drop = []

    for col in column_list:
        if col in df.columns:
            df[col] = df[col].replace(['NA', 'N/A', 'NaN', '', ' '], np.nan)
            df[col] = pd.to_numeric(df[col], errors='coerce')

            if (df[col] == 0).all() or df[col].isnull().all():
                columns_to_drop.append(col)

            if (df[col] == 0).sum() + df[col].isnull().sum() == len(df):
                columns_to_drop.append(col)

    columns_to_drop = sorted(set(columns_to_drop))
    df = df.drop(columns=columns_to_drop, errors='ignore')
    return df, columns_to_drop


def make_lean_csv(source_path: Path) -> Path:
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    output_file = source_path.with_name(f"{source_path.stem}_LEAN.csv")
    skipped = skip_rows(source_path)

    df = pd.read_csv(
        source_path,
        usecols=lambda col: any(sub in col for sub in APPLICABLE_COLS),
        skiprows=skipped,
        low_memory=False,
    )

    df.columns = df.columns.map(col_strip)
    df, _ = drop_zero_na_columns(df, ERRORS_COLS)
    df.to_csv(output_file, index=False)

    temp_file = output_file.parent / "temp_file.csv"
    with (
        source_path.open('r') as src,
        output_file.open('r') as trimmed,
        temp_file.open('w') as dst,
    ):
        for _ in range(skipped):
            line = src.readline()
            if not line:
                break
            dst.write(line)
        for line in trimmed:
            dst.write(line)

    os.replace(temp_file, output_file)
    return output_file


class CSVLeanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV Leaner")
        self.root.geometry("860x560")

        self.msg_queue = queue.Queue()
        self.job_running = False

        self.file_var = tk.StringVar()
        self.launch_var = tk.BooleanVar(value=True)
        # self.launch_var = tk.BooleanVar(value=False)

        self.build_ui()
        self.setup_dnd()
        self.root.after(100, self.process_queue)



    # def open_calculator(self):
    #     try:
    #         subprocess.Popen(["calc.exe"])
    #         self.log("\nOpened Windows Calculator.")
    #     except Exception as exc:
    #         messagebox.showerror("Calculator Error", str(exc))


    # new addition
    def open_streamlit(self):
        try:
            # subprocess.Popen(["calc.exe"])
            streamlit_cmd = f'streamlit run "Load CSV_2.py"'
            subprocess.Popen(streamlit_cmd, shell=True)
            self.log("\nLaunch Streamlit session.")
        except Exception as exc:
            messagebox.showerror("Streamlit Error", str(exc))



    def build_ui(self):
        main = tk.Frame(self.root, padx=12, pady=12)
        main.pack(fill="both", expand=True)

        tk.Label(
            main,
            text='Select or drop a DAT file to make it Leaner:'
        ).pack(anchor="w")

        file_row = tk.Frame(main)
        file_row.pack(fill="x", pady=(8, 8))

        self.file_entry = tk.Entry(file_row, textvariable=self.file_var, width=90)
        self.file_entry.pack(side="left", fill="x", expand=True)

        tk.Button(
            file_row,
            text="Browse",
            width=12,
            command=self.browse_file
        ).pack(side="left", padx=(8, 0))

        self.drop_box = tk.Text(
            main,
            height=4,
            wrap="word",
            bg="#f2f2f2",
            relief="groove",
            bd=2
        )
        self.drop_box.pack(fill="x", pady=(0, 10))
        self.drop_box.insert("1.0", "Drag and drop a .dat file here")
        self.drop_box.config(state="disabled")


        options_row = tk.Frame(main)
        options_row.pack(fill="x", pady=(0, 8))

        self.run_btn = tk.Button(
            options_row,
            text="Create Lean CSV",
            width=18,
            command=self.start_job
        )
        self.run_btn.pack(side="left")

        tk.Button(
            options_row,
            text="Exit",
            width=10,
            command=self.root.destroy
        ).pack(side="left", padx=(8, 0))

        tk.Checkbutton(
            options_row,
            text="View in Streamlit",
            variable=self.launch_var
        ).pack(side="left", padx=(18, 0))

        tk.Button(
            options_row,
            text="Streamlit Viewer",
            width=18,
            command=self.open_streamlit
        ).pack(side="right")


        self.log_box = scrolledtext.ScrolledText(
            main,
            height=20,
            wrap="word",
            font=("Consolas", 10),
            state="disabled"
        )
        self.log_box.pack(fill="both", expand=True)

    def setup_dnd(self):
        self.drop_box.drop_target_register(DND_FILES)
        self.drop_box.dnd_bind('<<Drop>>', self.on_drop)

    def on_drop(self, event):
        try:
            files = list(self.root.tk.splitlist(event.data))
        except Exception:
            files = [event.data]

        if not files:
            return

        first_file = files[0]
        self.file_var.set(first_file)
        self.log(f'Dropped file: {first_file}')

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select DAT file",
            filetypes=[("DAT Files", "*.dat"), ("All Files", "*.*")]
        )
        if path:
            self.file_var.set(path)

    def log(self, msg: str):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def queue_log(self, msg: str):
        self.msg_queue.put(("log", msg))

    def queue_done(self, src: str, out: str):
        self.msg_queue.put(("done", {"src": src, "out": out}))

    def queue_error(self, err: str):
        self.msg_queue.put(("error", err))

    def set_running(self, running: bool):
        self.job_running = running
        self.run_btn.config(state="disabled" if running else "normal")

    def start_job(self):
        if self.job_running:
            messagebox.showerror("Busy", "A job is already running. Please wait.")
            return

        src_str = self.file_var.get().strip()
        if not src_str:
            messagebox.showerror("Missing file", "Please browse or drop a DAT file first.")
            return

        src = Path(src_str)
        if not src.is_file():
            messagebox.showerror("File not found", f"File not found:\n{src}")
            return

        if src.suffix.lower() != ".dat":
            messagebox.showerror("Invalid file", "Please select a .dat file.")
            return

        self.set_running(True)
        self.log(f"Starting: {src.name}")

        t = threading.Thread(
            target=self.run_job_worker,
            args=(src_str, self.launch_var.get()),
            daemon=True
        )
        t.start()

    def run_job_worker(self, src_str: str, launch_streamlit: bool):
        src = Path(src_str)

        try:
            self.queue_log(f'Processing: {src}')

            target_directory = r"D:\MY_DIRECTORY"
            converter_cmd = (
                f'my_converter.exe '
                f'arg1="D:\\my_dir\\my_sub_dir" '
                f'arg2=1 arg3=3 '
                f'FilePath="{src}"'
            )

            self.queue_log('Running converter...')
            result = subprocess.run(
                converter_cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=target_directory
            )

            if result.stdout.strip():
                self.queue_log('[converter stdout]')
                for line in result.stdout.splitlines():
                    self.queue_log(line)

            if result.stderr.strip():
                self.queue_log('[converter stderr]')
                for line in result.stderr.splitlines():
                    self.queue_log(line)

            self.queue_log(f'Converter return code: {result.returncode}')

            if result.returncode != 0:
                raise RuntimeError(f'Converter failed with return code {result.returncode}')

            txt_file = src.with_name(f"{src.stem}.txt")
            if not txt_file.is_file():
                raise FileNotFoundError(f'Expected converter output not found: {txt_file}')

            self.queue_log(f'Creating lean CSV from: {txt_file}')
            out = make_lean_csv(txt_file)

            if launch_streamlit:
                self.queue_log('Launching Streamlit viewer...')
                streamlit_cmd = f'streamlit run Load_CSV.py -- "{out}"'
                subprocess.Popen(streamlit_cmd, shell=True)

            try:
                os.remove(txt_file)
                self.queue_log(f'Deleted temporary file: {txt_file}')
            except OSError as e:
                self.queue_log(f'Error deleting temporary file: {e}')

            self.queue_done(str(src), str(out))

        except Exception as exc:
            self.queue_error(str(exc))

    def process_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "log":
                    self.log(payload)

                elif kind == "done":
                    self.set_running(False)
                    self.log(f'✅ Source: {payload["src"]}')
                    self.log(f'✅ Saved: {payload["out"]}')
                    messagebox.showinfo("Finished", f'Lean CSV saved as:\n{payload["out"]}')

                elif kind == "error":
                    self.set_running(False)
                    self.log(f'❌ Error: {payload}')
                    messagebox.showerror("Error", payload)

        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = CSVLeanerApp(root)
    root.mainloop()