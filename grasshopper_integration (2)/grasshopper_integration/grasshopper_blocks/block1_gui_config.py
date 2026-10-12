#! python 3
"""BLOCK 1 - GUI (opens the full Variable Transfer window)
Rhino 8 > Script editor > new "Python 3 Script" component.

The window is the same one as the standalone app, except:
  source      = the Names/Values wired into this block (live Grasshopper variables)
  destination = the MatlabFile wired into this block
Everything you set in it (mode, tick boxes, links, renames) is saved, and the
Transfer block uses it when you wire this block's Config output into it.

INPUTS  (right-click each input -> set Type Hint / Access as shown)
  Repo        str   item  - path to your Capstone2 folder
  Names       str   list  - GH variable names   (e.g. from a Panel)
  Values      float list  - GH variable values  (same length as Names)
  MatlabFile  str   item  - the MATLAB .m file to transfer into
  PythonExe   str   item  - OPTIONAL, python with tkinter (default: "python")
  Open        bool  item  - wire a Button here; press to open the GUI

OUTPUTS
  Config      str   - path of the saved settings (wire to Transfer block)
  Status      str
"""
import sys
import Grasshopper as gh

Config, Status = None, ""
try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib, gh_bridge
    importlib.reload(gh_bridge)          # pick up edits without restarting Rhino

    Config = gh_bridge.DEFAULT_CONFIG_PATH
    if Open:
        gh_bridge.launch_config_gui(Names, Values, str(MatlabFile),
                                    str(PythonExe) if PythonExe else "python",
                                    Config)
        Status = "GUI opened. Click Save Configuration in it; Transfer block uses the result."
    else:
        have = gh_bridge.load_config(Config)
        Status = "Saved config found." if have else "No config yet - press Open."
except Exception as e:
    Config = None
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
