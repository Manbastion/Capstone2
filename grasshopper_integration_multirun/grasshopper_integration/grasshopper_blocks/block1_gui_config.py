#! python 3
"""BLOCK 1 - GUI (opens the full Variable Transfer window)

INPUTS
  Repo        str   item
  Names       str   list
  Values      TREE
  MatlabFile  str   item
  PythonExe   str   item
  Open        bool  item

OUTPUTS
  Config      str
  Status      str
"""

import sys
import Grasshopper as gh

Config, Status = None, ""

try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))

    import importlib
    import gh_bridge
    importlib.reload(gh_bridge)

    # Output the path to the saved configuration file.
    Config = str(gh_bridge.DEFAULT_CONFIG_PATH)

    if Open:
        gh_bridge.launch_config_gui(
            Names,
            Values,
            str(MatlabFile),
            str(PythonExe) if PythonExe else "python",
            Config
        )

        Status = (
            "GUI opened. Link your variables, click OK in the "
            "configuration window, then OK here; Block 2 uses the result."
        )
        gh_bridge.save_last_status(Status)

    else:
        have = gh_bridge.load_config(Config)
        Status = "Saved config found." if have else "No config yet - press Open."

        last = gh_bridge.load_last_status()

        if last:
            Status += "  |  Last Open: " + last

except Exception as e:
    Config = None
    Status = "ERROR: %s" % e

    try:
        gh_bridge.save_last_status(Status)
    except Exception:
        pass

    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status
    )