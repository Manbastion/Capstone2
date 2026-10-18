#! python 3
"""Open notification settings from Grasshopper; no Tkinter inside Rhino.

Inputs (Item Access): Repo (str), PythonExe (str), Open (bool Button).
Outputs: Status (str).
PythonExe must be an external Python with working Tkinter. On macOS use
python.org Python, not Rhino's embedded interpreter or Xcode's Python.
"""
import importlib.util
from pathlib import Path
import subprocess
import scriptcontext as sc
from Grasshopper.Kernel import GH_RuntimeMessageLevel

Status = "Press Open for notification settings."
try:
    root = Path(str(Repo)).expanduser().resolve()
    path = root / "grasshopper_components" / "bridge.py"
    spec = importlib.util.spec_from_file_location("notification_settings_bridge", path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    key = ("HabSimNotificationSettings", str(ghenv.Component.InstanceGuid))
    pressed = bridge.button_edge(sc.sticky, key, Open)
    process_key = key + ("process",)
    child = sc.sticky.get(process_key)
    if pressed and child is not None and child.poll() is None:
        Status = "The notification settings window is already open."
    elif pressed:
        if not PythonExe:
            raise ValueError("Set PythonExe to a standalone Python with Tkinter.")
        child = subprocess.Popen([str(PythonExe), str(root / "notification_settings.py")], cwd=str(root))
        sc.sticky[process_key] = child
        Status = "Settings opened in a separate process. Save and test the desired channels."
    elif child is not None and child.poll() not in (None, 0):
        Status = "Settings could not open. Check PythonExe; see README.md for Python/Tkinter setup."
except Exception as error:
    Status = "Notification settings: %s" % error
    ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, Status)
