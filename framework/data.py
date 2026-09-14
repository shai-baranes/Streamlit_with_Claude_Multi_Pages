"""Private source storage and bounded, projected pandas ingestion."""
from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import uuid
import pandas as pd
import psutil
from framework.config import ROOT, MAX_UPLOAD_MB, MAX_FRAME_MB, TTL_SECONDS, MAX_PROCESS_MB

INGEST_LOCK = threading.Lock()

@dataclass
class Dataset:
    source: Path
    name: str
    available: list[str]
    selected: list[str]
    frame: pd.DataFrame
    version: str


def session_directory(session_id):
    # Only server-generated UUIDs may become directory components.
    uuid.UUID(session_id)
    directory = ROOT / session_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.touch()
    return directory


def cleanup(now=None):
    now = time.time() if now is None else now
    if ROOT.exists():
        for directory in ROOT.iterdir():
            if directory.is_dir() and now - directory.stat().st_mtime > TTL_SECONDS:
                shutil.rmtree(directory, ignore_errors=True)


def save_source(stream, session_id):
    directory = session_directory(session_id)
    path = directory / f'{uuid.uuid4().hex}.csv'
    size = 0
    try:
        stream.seek(0)
        with path.open('wb') as output:
            while block := stream.read(1024 * 1024):
                # Cooperatively stop ingestion when an administrator ends this session.
                from framework.admin_runtime import check_cancelled
                check_cancelled()
                size += len(block)
                if size > MAX_UPLOAD_MB * 1024**2:
                    raise ValueError(f'Upload exceeds {MAX_UPLOAD_MB} MB. Reduce the source size.')
                output.write(block)
        inspect_header(path)
        # Validate structure once per uploaded source; usecols otherwise masks extra fields.
        with path.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.reader(source, strict=True)
            width = len(next(reader))
            for row in reader:
                if row and len(row) != width:
                    raise ValueError(f'CSV row ending at line {reader.line_num} has {len(row)} fields; expected {width}.')
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def inspect_header(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        header = next(csv.reader(source), [])
    if not header or any(not name.strip() for name in header):
        raise ValueError('CSV requires one header row with nonempty field names.')
    if len(set(header)) != len(header):
        raise ValueError('Duplicate CSV field names are ambiguous. Rename them before uploading.')
    return header


def normalize(frame):
    # Preserve the legacy sales transformation only for the sales schema.
    if {'Date', 'Revenue', 'Region', 'Category'}.issubset(frame.columns):
        frame['Date'] = pd.to_datetime(frame['Date'], dayfirst=True)
        date = frame['Date'].dt
        for name, values in {'Year': date.year, 'MonthNum': date.month,
                             'Month': date.strftime('%b'),
                             'Quarter': date.quarter.map(lambda q: f'Q{q}' if pd.notna(q) else None)}.items():
            if name not in frame:
                frame[name] = values
        frame = frame.sort_values('Date').reset_index(drop=True)
    return frame


def load_projection(path, selected, parquet=False):
    available = inspect_header(path)
    selected = [name for name in available if name in selected]
    if not selected:
        raise ValueError('Select at least one available column.')
    key = hashlib.sha256(json.dumps(selected).encode()).hexdigest()[:24]
    cache = Path(path).with_suffix(f'.{key}.parquet')
    with INGEST_LOCK:
        # Admission includes native upload buffers and other sessions already in this process.
        if psutil.Process().memory_info().rss + 3 * MAX_FRAME_MB * 1024**2 > MAX_PROCESS_MB * 1024**2:
            raise ValueError('Server memory budget is busy. Clear unused datasets or retry later.')
        if parquet and cache.exists():
            try:
                return pd.read_parquet(cache)
            except Exception:
                cache.unlink(missing_ok=True)
        chunks, memory = [], 0
        # Keep each parser chunk near 100,000 cells even for very wide selections.
        for chunk in pd.read_csv(path, usecols=selected,
                                 chunksize=max(1, min(10000, 100000 // len(selected)))):
            from framework.admin_runtime import check_cancelled
            check_cancelled()  # Native reads finish before cancellation can be observed.
            memory += int(chunk.memory_usage(deep=True).sum())
            if psutil.Process().memory_info().rss + 2 * memory > MAX_PROCESS_MB * 1024**2:
                raise ValueError('Server memory budget reached. Select fewer columns or retry later.')
            if memory > MAX_FRAME_MB * 1024**2:
                raise ValueError(f'Selected data exceeds {MAX_FRAME_MB} MB. Select fewer columns.')
            chunks.append(chunk)
        frame = normalize(pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=selected))
        if int(frame.memory_usage(deep=True).sum()) > MAX_FRAME_MB * 1024**2:
            raise ValueError('Normalized data exceeds the working-set limit. Select fewer columns.')
        if parquet:
            try:
                frame.to_parquet(cache, index=False)
            except Exception:
                cache.unlink(missing_ok=True)
        return frame


def load_dataset(path, name, selected, parquet=False):
    frame = load_projection(path, selected, parquet)
    return Dataset(Path(path), name, inspect_header(path), list(selected), frame, uuid.uuid4().hex)
