# Allow both direct script launch and package import from any checkout name.
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from habsim_prototype import load_prototype
    __package__ = load_prototype().__name__

from .gui import VariableTransferGUI


def main():
    app = VariableTransferGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
