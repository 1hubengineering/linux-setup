"""Update this linux-setup checkout and rerun installation from any directory."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Your current directory is preserved. Git must be able to fast-forward the checkout's tracking branch.")
    parser.parse_args(argv)
    if not (ROOT / ".git").exists():
        print(f"linux-setup-update: {ROOT} is not a Git checkout. Clone the repository to enable updates.", file=sys.stderr)
        return 1
    try:
        print(f"Updating linux-setup in {ROOT} ...", flush=True)
        subprocess.run(["git", "-C", str(ROOT), "pull", "--ff-only"], check=True)
        print("Running the updated installer ...", flush=True)
        subprocess.run(["bash", str(ROOT / "install.sh")], cwd=ROOT, check=True)
    except subprocess.CalledProcessError as error:
        print("linux-setup-update: " + ("Git update failed; resolve the reported problem and run update again." if error.cmd[0] == "git"
                                       else "Installation is incomplete. Run update again to retry."), file=sys.stderr)
        return error.returncode if error.returncode > 0 else 1
    except OSError as error:
        print(f"linux-setup-update: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nUpdate stopped. Run update again to continue.", file=sys.stderr)
        sys.exit(130)
