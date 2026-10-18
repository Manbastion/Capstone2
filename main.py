import sys


def main():
    if sys.platform == "darwin" and any(part in sys.executable for part in ("/Xcode.app/", "/CommandLineTools/")):
        print("Use a standalone Python from python.org for the GUI.\n"
              "Xcode's Python/Tk can abort on macOS 26. See README.md > macOS setup.", file=sys.stderr)
        return 2
    from gui import VariableTransferGUI
    app = VariableTransferGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
