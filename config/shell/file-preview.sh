# File previews for fzf's Ctrl-T widget in Bash and Zsh.
for _setup_viewer in bat batcat; do
  if command -v "$_setup_viewer" >/dev/null; then
    _setup_color=always
    case "${LINUX_SETUP_PLAIN:-}" in 1|true|yes) _setup_color=never ;; esac
    if [ "${NO_COLOR+x}" = x ] || [ "${TERM:-}" = dumb ]; then _setup_color=never; fi
    export FZF_CTRL_T_OPTS="--preview '$_setup_viewer --color=$_setup_color --paging=never --style=numbers --line-range=:200 -- {}'"
    break
  fi
done
unset _setup_color _setup_viewer
