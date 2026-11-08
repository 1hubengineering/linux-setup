# GitHub accounts and Git author profiles

[User guides](README.md) · [Commands](commands.md)

Run the account manager from any terminal:

```sh
github
```

Use the arrows and Enter to choose **Add**, **Switch**, **List**, **Remove**, or
**Check GitHub login status**. Back or Esc leaves a selection unchanged. Run the
switch command from the repository whose commit author you want to change.

## First-time GitHub setup

From the linux-setup checkout:

```sh
./install.sh --github-setup
```

This fills missing global Git author settings, offers GitHub CLI installation,
and guides you through adding profiles. To install only the CLI:

```sh
./install.sh --install-gh
```

## Add one or several accounts

```sh
github add
```

Choose whether to authenticate through `gh auth login` or use an account already
logged in. Enter the GitHub login username for this profile.

The manager offers to reuse the most recently saved profile's **Git author name
and email**. For the first profile, it offers the global Git identity if both
values are set. Choose Yes to share those author details, or No to enter different
ones. GitHub login usernames remain separate for each account. Use an email
associated with the intended GitHub account, including its no-reply address if
desired.

A **Profile created** message shows the username and saved author. Only then does
the manager ask **Add another GitHub profile?** Choose Yes to start a new profile,
or No to finish. Each profile is saved before that question, so completed
profiles remain available if you stop partway through adding another.

## List and switch profiles

```sh
github list
cd ~/projects/my-repository
github use my-github-username
```

`use` switches GitHub CLI's active account for `github.com` and sets `user.name`
and `user.email` only in the current repository. The GitHub CLI account is shared
across terminal sessions for that host; switching it affects CLI authentication
in other terminals too. Other repositories' saved author settings stay as they
were.

```sh
gh auth status                     # Inspect saved GitHub CLI logins
gh auth setup-git                  # Let HTTPS Git use GitHub CLI credentials
```

SSH authentication follows your SSH configuration. `GH_TOKEN` or `GITHUB_TOKEN`
can override saved GitHub CLI accounts.

## Remove a profile or log out

Use **Remove a saved account** in `github`, then choose whether to keep the
GitHub login or log out locally too. The manager asks for confirmation before
removing anything. Direct commands are available:

```sh
github remove my-github-username           # Remove saved author profile only
github remove my-github-username --logout  # Also remove local gh login
```

Existing repository author settings and commits are kept. To remove only a
GitHub CLI login, including one without a saved author profile:

```sh
gh auth logout --hostname github.com --user my-github-username
```

[GitHub CLI logout](https://cli.github.com/manual/gh_auth_logout) removes the local
login; it does not revoke the token on GitHub. No GitHub account is deleted.

## Where information is stored

Saved usernames and author details live in
`~/.config/linux-setup-local/git-profiles.json`, respecting `XDG_CONFIG_HOME`.
GitHub CLI stores credentials separately. This setup never copies tokens into
its profile file or the repository. For automation, `git-profile list` and
`git-profile use USERNAME` accept explicit arguments; adding and removing
profiles require interactive confirmation.
