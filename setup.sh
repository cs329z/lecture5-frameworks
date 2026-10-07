#!/usr/bin/env bash
# One-time setup for the lecture: installs uv if needed, installs dependencies, saves your API key, opens the notebook.
# macOS / Linux: ./setup.sh        Windows: run this from Git Bash (comes with Git for Windows).
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing Python 3.12 and all dependencies..."
uv sync

if [ ! -f .env ]; then
    read -rp "Paste your OpenRouter API key (starts with sk-or-): " key
    echo "OPENROUTER_API_KEY=$key" > .env
    echo "Saved to .env (gitignored)."
fi

echo
echo "Done. Open lecture5.ipynb and select the .venv kernel (Python 3.12)."
if command -v code >/dev/null 2>&1; then
    code . lecture5.ipynb
fi
