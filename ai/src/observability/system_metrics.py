"""Non-invasive, lightweight system resource telemetry snapshot provider."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


def capture_system_snapshot(include_gpu: bool | None = None) -> dict[str, Any]:
    """Capture a low-overhead system and process resource snapshot.

    Fails open: returns whatever metrics are safely queryable without raising errors.
    """
    snapshot: dict[str, Any] = {}

    try:
        import psutil

        vm = psutil.virtual_memory()
        snapshot["cpu_percent"] = psutil.cpu_percent(interval=None)
        snapshot["ram_total_mb"] = round(vm.total / (1024 * 1024), 1)
        snapshot["ram_used_mb"] = round(vm.used / (1024 * 1024), 1)
        snapshot["ram_available_mb"] = round(vm.available / (1024 * 1024), 1)
        snapshot["ram_percent"] = vm.percent

        proc = psutil.Process()
        mem_info = proc.memory_info()
        snapshot["process_rss_mb"] = round(mem_info.rss / (1024 * 1024), 1)
        snapshot["process_vms_mb"] = round(mem_info.vms / (1024 * 1024), 1)
    except Exception:
        pass

    # Optional GPU telemetry via nvidia-smi query
    check_gpu = include_gpu
    if check_gpu is None:
        check_gpu = os.getenv("LATENCY_AUDIT_ENABLE_GPU", "0").lower() in ("1", "true", "yes")

    if check_gpu and shutil.which("nvidia-smi"):
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=0.4)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
                if len(parts) >= 3:
                    snapshot["gpu_utilization_pct"] = float(parts[0])
                    snapshot["gpu_memory_used_mb"] = float(parts[1])
                    snapshot["gpu_memory_total_mb"] = float(parts[2])
        except Exception:
            pass

    return snapshot
