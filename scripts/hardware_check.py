"""
Reports the real hardware specs of the machine running it, to ground the
local-LLM feasibility assessment in measured facts rather than assumptions.

Usage (from backend/.venv, which already has psutil installed):
    ../backend/.venv/Scripts/python.exe hardware_check.py
"""

import platform
import shutil

import psutil


def gb(num_bytes: int) -> float:
    return round(num_bytes / (1024 ** 3), 2)


def main() -> None:
    print("=== OS ===")
    print(f"{platform.system()} {platform.release()} ({platform.version()})")

    print("\n=== CPU ===")
    print(f"Physical cores: {psutil.cpu_count(logical=False)}")
    print(f"Logical cores:  {psutil.cpu_count(logical=True)}")
    freq = psutil.cpu_freq()
    if freq:
        print(f"Max frequency:  {freq.max:.0f} MHz")

    print("\n=== RAM ===")
    vm = psutil.virtual_memory()
    print(f"Total: {gb(vm.total)} GB")
    print(f"Available now: {gb(vm.available)} GB")

    print("\n=== Disk (project drive) ===")
    usage = shutil.disk_usage(".")
    print(f"Total: {gb(usage.total)} GB | Free: {gb(usage.free)} GB")

    print("\n=== GPU ===")
    print("psutil has no cross-platform GPU API; see docs/local_llm_feasibility.md")
    print("for GPU details captured separately via Windows CIM (Win32_VideoController).")


if __name__ == "__main__":
    main()
