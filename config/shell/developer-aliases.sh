# Install optional developer tools or explicitly update them.
alias devtools='dev-tools'
# Authenticate Codex, preserving an existing login.
alias cxlogin='dev-tools auth codex'
# Authenticate Claude Code, preserving an existing login.
alias cldlogin='dev-tools auth claude'
# Run a Python command in the project environment.
alias uvr='uv run'
# Synchronize the project Python environment.
alias uvs='uv sync'
# Add a Python dependency to the project.
alias uva='uv add'
# Run an isolated Python tool.
alias uvtool='uv tool run'
# Install the latest stable Python supported by uv.
alias python-latest='uv python install'
# Run the current shadcn/ui CLI in the project.
alias shadcn='npx --yes shadcn@latest'
# Run the current Better Auth CLI in the project.
alias better-auth='npx --yes auth@latest'
# Run the Tailwind CSS CLI without changing project dependencies.
alias tailwind='npx --yes @tailwindcss/cli@latest'
# Initialize OpenSpec workflows for a project.
alias spec-init='openspec init'
# Show OpenSpec changes.
alias specs='openspec list'
# Update generated OpenSpec agent workflows.
alias spec-update='openspec update'
# Run Graphify.
alias graph='graphify'
# Change the default login shell (takes effect after the next login).
alias default-shell='shell-default'

# Install Graphify workflows for Codex in the current project.
alias graph-init='dev-tools workflow graphify'
