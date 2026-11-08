# Rerun, resume, and update

[User guides](README.md) · [Installation](installation.md)

## Rerun the installer

Run the same command from your checkout:

```sh
cd ~/linux-setup
./install.sh
```

Completed tools report **already installed** and skip downloading and extracting.
Configuration and executable links are checked again so missing links can be
repaired. Existing configuration backups are reused when a managed link is
repaired; rerunning does not make another copy of the same original file.
Programs already available outside linux-setup are kept and remain owned by
their original installer.

## Continue after a failure

Fix the reported problem, such as a network connection or missing package index,
then rerun `./install.sh`. No reset or separate resume flag is needed.

The installer saves progress in
`~/.local/state/linux-setup/deployment.json`, respecting `XDG_STATE_HOME`.
A retry checks each step, reuses completed artifacts, and retries incomplete work.
A tool download failure allows independent tools and configuration setup to
continue. The installer exits with a failure status and lists unfinished items
until they succeed.

Downloads are checksum-verified and cached. Tools, plugins, base packages, and
skills are prepared in temporary directories before they become active. An
interrupted download or extraction starts again; already verified downloads are
reused. A failed Vite+ runtime bootstrap is retried even if it left an environment
file behind. Previously completed GitHub and skills setup prompts stay completed;
a failed optional setup is offered again.

Keep the manifest, caches, and backups while recovering. Older incomplete or
modified tool directories may be retained beside a completed replacement. If a
configuration path changes after an interrupted backup, the installer preserves
it and reports the conflict for review. The original backup location remains in
the manifest.

Only one install or uninstall can modify a deployment at a time. If another is
running, wait for it to finish. The operating system releases the lock when the
process exits; the lock file can remain on disk.

## Approve updates

Run the update shortcut from any directory in Zsh:

```sh
update
```

It pulls the latest changes into your checkout and runs the installer. Your
working directory stays the same. Other shells can use `linux-setup-update`.
See [installation](installation.md#update-an-existing-installation) to add the
shortcut to an older setup. You can still run `./install.sh` directly when you
only need to retry an installation without fetching repository changes.

When a managed tool or plugin has a different pinned version, the installer asks
before changing it. Keeping the current version is the default. Use arrows and
Enter to choose. A non-interactive run keeps the current version. Once you approve
an update, a failed or interrupted attempt can resume without asking again for
that same version.

External tools are kept. Vite+ and uv also retain their installed versions; use
their own upgrade commands to update them. System base packages follow your
Linux distribution's package manager.

## Check or repair configuration

```sh
doctor
./install.sh --config-only --skip-mcp
```

Configuration-only installation repairs links without downloading tools. Use the
full installer to retry tool installation or Vite+ bootstrap. For a deliberately
modified configuration, keep private additions in
`~/.config/linux-setup-local/` as described in [customization](customization.md).
See [troubleshooting](troubleshooting.md) for specific errors and
[uninstall and recovery](uninstall.md) to restore backed-up configuration.
