import os
import sys


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    sys.path.insert(0, src_dir)

    try:
        from pyqt_app import main as run_app
    except ModuleNotFoundError as exc:
        if exc.name == "PyQt6":
            print("PyQt6 is not installed. Run: pip install -r requirements.txt")
            return 1
        raise

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
