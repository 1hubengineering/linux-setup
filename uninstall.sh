#!/usr/bin/env bash
set -euo pipefail
setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$#" == 1 && ( "$1" == --help || "$1" == -h ) && -z "${LINUX_SETUP_BUILD_CLI:-}" && -r "$setup_dir/config/cli-help/uninstall.sh.txt" ]]; then
  while IFS= read -r help_line; do printf '%s\n' "$help_line"; done < "$setup_dir/config/cli-help/uninstall.sh.txt"
  exit 0
fi

if [[ "$#" == 1 && "$1" == --version ]]; then
  read -r setup_version < "$setup_dir/VERSION"
  printf "%s %s\n" "uninstall.sh" "$setup_version"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo 'Uninstallation requires Python 3.9 or newer.' >&2
  exit 1
fi
exec python3 "$setup_dir/scripts/uninstall.py" "$@"
