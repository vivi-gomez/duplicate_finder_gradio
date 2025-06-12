import hashlib
import time
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# For _check_gpu
try:
    import cupy as cp
except ImportError:
    cp = None # Or handle it differently if cupy is strictly required

class DuplicateFinder:
    def __init__(self, use_gpu=True):
        self.use_gpu = use_gpu and self._check_gpu()
        self.total_files = 0
        self.processed_files = 0
        self.start_time = None

    def _check_gpu(self):
        try:
            # import cupy as cp # This import is already at the top
            cp.cuda.Device(0).compute_capability
            return True
        except:
            return False

    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math # This import is method-specific, keep it here or move to top
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

    def _calculate_hash(self, file_path, chunk_size=8192):
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                if self.use_gpu:
                    for chunk in iter(lambda: f.read(chunk_size * 4), b""):
                        hash_md5.update(chunk)
                else:
                    for chunk in iter(lambda: f.read(chunk_size), b""):
                        hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (PermissionError, OSError):
            return None

    def find_duplicates(self, directory, min_size_mb=1, progress_callback=None):
        # global stop_analysis # This global variable is not part of the class logic

        directory_path = Path(directory)
        if not directory_path.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        min_size_bytes = min_size_mb * 1024 * 1024
        file_hashes = defaultdict(list)
        all_files = []

        for file_path in directory_path.rglob('*'):
            # if stop_analysis: # This global variable is not part of the class logic
            #     return []
            if file_path.is_file():
                try:
                    size = file_path.stat().st_size
                    if size >= min_size_bytes:
                        all_files.append(file_path)
                except OSError:
                    continue

        self.total_files = len(all_files)
        self.processed_files = 0
        self.start_time = time.time()

        for file_path in all_files:
            # if stop_analysis: # This global variable is not part of the class logic
            #     return []
            try:
                file_hash = self._calculate_hash(file_path)
                if file_hash:
                    stat = file_path.stat()
                    file_info = {
                        'path': str(file_path),
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'mtime_readable': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'hash': file_hash
                    }
                    file_hashes[file_hash].append(file_info)
                self.processed_files += 1
                if progress_callback and self.processed_files % 10 == 0:
                    progress = (self.processed_files / self.total_files) * 100
                    elapsed = time.time() - self.start_time
                    speed = self.processed_files / elapsed if elapsed > 0 else 0
                    eta = (self.total_files - self.processed_files) / speed if speed > 0 else 0
                    status = f"Procesando: {self.processed_files}/{self.total_files} ({progress:.1f}%) - {speed:.1f} archivos/seg - ETA: {eta:.0f}s"
                    progress_callback(status)
            except (PermissionError, OSError):
                continue

        duplicate_groups = []
        group_id = 1

        for file_hash, files in file_hashes.items():
            if len(files) > 1:
                files.sort(key=lambda x: x['mtime'], reverse=True)
                file_counter = 1
                for file_info in files:
                    file_info['file_id'] = f"g{group_id}f{file_counter}"
                    file_counter += 1

                priority_file = files[0]
                duplicate_files = files[1:]
                wasted_space = sum(f['size'] for f in duplicate_files)

                group = {
                    'group_id': group_id,
                    'hash': file_hash,
                    'priority_file': priority_file,
                    'duplicate_files': duplicate_files,
                    'all_files': files,
                    'total_files': len(files),
                    'wasted_space': wasted_space
                }
                duplicate_groups.append(group)
                group_id += 1

        return duplicate_groups
