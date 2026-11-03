"""Invoke the independent collector through its documented stdio protocol."""
import sys
from pathlib import Path

def collector_command(flag):
    if flag not in ('--download','--following','--probe-account'):
        raise ValueError('Unknown collector operation')
    if not getattr(sys,'frozen',False):
        return [sys.executable,str(Path(__file__).resolve().parents[1]/'collector/app.py'),flag]
    base=Path(sys.executable).resolve().parent
    candidates=[base.parent/'collector/luma-collector.exe',base.parent.parent/'collector-dist/luma-collector/luma-collector.exe']
    for path in candidates:
        if path.is_file():return [str(path),flag]
    raise RuntimeError('采集组件不完整，请重新安装完整 Luma 发行包；资料库和任务保留')
