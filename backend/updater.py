import subprocess
import sys


def restart_application() -> None:
    """Relaunch the application and exit the current process.

    Source install: spawns new Python process with identical args.
    Frozen Linux/macOS: re-executes the binary.
    Frozen Windows: raises RuntimeError — user must restart manually.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen and sys.platform == "win32":
        raise RuntimeError(
            "Auto-restart is not supported for Windows packaged builds.\n"
            "Please close and reopen the application to use the updated version."
        )
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([sys.executable] + sys.argv, **kwargs)
    sys.exit(0)
