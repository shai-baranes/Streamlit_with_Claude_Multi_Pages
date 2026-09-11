"""Opt-in capacity test. Run from repository root; generated data can occupy many GB."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import psutil
from framework.config import ALWAYS_LOAD_COLUMNS
from framework.data import load_projection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=500000)
    parser.add_argument('--columns', type=int, default=2000)
    parser.add_argument('--users', type=int, default=5)
    parser.add_argument('--include-upload-buffers', action='store_true', help='Retain one raw upload buffer per worker; may need substantial RAM')
    parser.add_argument('--output', default='benchmark-results/result.json')
    args = parser.parse_args()
    process = psutil.Process()
    peak = [0]
    stop = threading.Event()
    def monitor():
        while not stop.wait(.02):
            peak[0] = max(peak[0], process.memory_info().rss)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    results = {'rows':args.rows, 'columns':args.columns, 'users':args.users, 'runs':[]}
    try:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'wide.csv'
            # Bounded generation avoids materializing a billion-cell fixture in RAM.
            for start in range(0, args.rows, 1000):
                count = min(1000, args.rows-start)
                values = np.arange(start, start+count)
                block = {c: (['01/01/2022']*count if c == 'Date' else values) for c in ALWAYS_LOAD_COLUMNS}
                for i in range(max(0, args.columns-len(block))):
                    block[f'field_{i}'] = values if i % 4 else np.where(values % 2, 'on', 'off')
                pd.DataFrame(block).to_csv(source, mode='a', header=start == 0, index=False)
            results['file_bytes'] = source.stat().st_size
            for extras in (20,100):
                selected = ALWAYS_LOAD_COLUMNS + [f'field_{i}' for i in range(min(extras, max(0,args.columns-19)))]
                for parquet in (False, True):
                    peak[0] = process.memory_info().rss
                    def workload(user):
                        # Distinct source paths exercise private caches for each user.
                        private = Path(directory) / f'{user}.csv'
                        if not private.exists():
                            import shutil
                            shutil.copyfile(source, private)
                        upload_buffer = private.read_bytes() if args.include_upload_buffers else None
                        timings=[]
                        for _ in range(4):
                            before=time.perf_counter()
                            frame=load_projection(private, selected, parquet)
                            frame.groupby('Region')['Revenue'].sum()
                            timings.append(time.perf_counter()-before)
                        return timings
                    before=time.perf_counter()
                    with ThreadPoolExecutor(max_workers=args.users) as pool:
                        times=list(pool.map(workload, range(args.users)))
                    results['runs'].append({'extra_columns':extras,'parquet':parquet,'seconds':time.perf_counter()-before,'per_user_reads':times,'peak_rss_bytes':peak[0],'cache_bytes':sum(p.stat().st_size for p in Path(directory).glob('*.parquet'))})
            results['peak_rss_bytes']=max(r['peak_rss_bytes'] for r in results['runs'])
            results['below_24_gib']=results['peak_rss_bytes'] < 24*1024**3
            results['note']='Synthetic upload buffers included: ' + str(args.include_upload_buffers) + '; browser/network overhead excluded; automatic Parquet remains disabled.'
    finally:
        stop.set(); thread.join()
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))

if __name__ == '__main__': main()
