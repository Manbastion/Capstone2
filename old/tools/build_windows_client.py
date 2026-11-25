"""TEAM ONLY: py -3.13 tools/build_windows_client.py

Build on Windows. The delivered folder includes Python and Tk; the client does
not run this build script. Real MATLAB/Rhino/device acceptance is separate.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows executable on Windows, or use the Build Windows client GitHub Action.")
    venv = ROOT / ".venv-build"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    python = venv / "Scripts/python.exe"
    subprocess.check_call([str(python), "-m", "pip", "install", "pyinstaller==6.16.0"])
    subprocess.check_call([str(python), "-m", "PyInstaller", "--clean", "--noconfirm",
        "--onedir", "--windowed", "--name", "HabSimClient",
        "--add-data", "examples/notification_demo/workflow_demo.m:examples/notification_demo",
        "--add-data", "CLIENT_START_HERE.md:.", "habsim_client.py"], cwd=str(ROOT))
    folder = ROOT / "dist/HabSimClient"
    shutil.copy2(ROOT / "CLIENT_START_HERE.md", folder / "START_HERE.md")
    with tempfile.TemporaryDirectory(prefix="habsim build check ") as temp:
        report = Path(temp) / "report.json"
        env = dict(os.environ, HABSIM_NOTIFICATION_SETTINGS=str(Path(temp) / "notifications.json"))
        subprocess.run([str(folder / "HabSimClient.exe"), "--self-test", str(report)],
                       check=True, timeout=60, env=env)
        data = json.loads(report.read_text(encoding="utf-8"))
        if data.get("status") != "passed" or data.get("frozen") is not True:
            raise RuntimeError("The packaged application did not pass its startup check.")
        shutil.copy2(report, folder / "build-startup-check.json")
    archive = shutil.make_archive(str(ROOT / "dist/HabSimClient-Windows"), "zip",
                                 root_dir=str(ROOT / "dist"), base_dir="HabSimClient")
    print("Built and checked GUI startup:", archive)
    print("Next: real MATLAB, desktop and phone checks in WINDOWS_CLIENT_BUILD.md.")


if __name__ == "__main__":
    main()
