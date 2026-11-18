# Read definitions from the calling Bash session, including private overrides.
_dev_commands_snapshot() {
  local name
  for name in "${!BASH_ALIASES[@]}"; do
    builtin printf '%s\0%s\0%s\0' alias "$name" "${BASH_ALIASES[$name]}"
  done
  while IFS= read -r name; do
    [[ $name == _* ]] && continue
    builtin printf '%s\0%s\0%s\0' function "$name" "$(declare -f -- "$name")"
  done < <(compgen -A function)
}

# List custom commands or filter the list by text.
devhelp() {
  _dev_commands_snapshot | command python3 "$LINUX_SETUP_DIR/scripts/command_catalog.py" --shell bash --list -- "$*"
}

_dev_commands_widget() {
  local selected
  if selected=$(_dev_commands_snapshot | command python3 "$LINUX_SETUP_DIR/scripts/command_catalog.py" --shell bash --pick); then
    READLINE_LINE=$selected
    # Readline counts bytes, including for non-ASCII command text.
    local LC_ALL=C
    READLINE_POINT=${#READLINE_LINE}
  fi
}

if [[ $- == *i* ]]; then
  for _setup_keymap in emacs-standard vi-insert vi-command; do
    bind -m "$_setup_keymap" -x '"\ex":_dev_commands_widget'
    bind -m "$_setup_keymap" -x '"\eX":_dev_commands_widget'
  done
  unset _setup_keymap
fi
