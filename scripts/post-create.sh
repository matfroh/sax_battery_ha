#!/usr/bin/env bash
export VIRTUAL_ENV="$HOME/.local/ha-venv"
source "$VIRTUAL_ENV/bin/activate"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
export WORKSPACE="${WORKSPACE:-$PROJECT_ROOT}"

# requirements_dev is already loaded by Dockerfile.dev
# echo "export CODECOV_TOKEN='$CODECOV_TOKEN'" >> /home/vscode/.bashrc

if [ -n "$CODECOV_TOKEN" ]; then
  echo "CODECOV_TOKEN is set!"
else
  echo "CODECOV_TOKEN is NOT set in container !!!"
fi

pip install -r requirements_test.txt
echo $VIRTUAL_ENV
which python3
python --version
pip show pymodbus

# Security: Proper Docker setup with minimal privileges (OWASP A01)
# Only enable if Docker-in-Docker is configured in devcontainer.json
if [ -S /var/run/docker.sock ]; then
    echo "Docker socket detected, configuring access..."
    # Security: Only add to group if not already member
    if ! groups vscode | grep -q docker; then
        sudo usermod -aG docker vscode
    fi
    # Security: More restrictive permissions than 666
    sudo chmod 664 /var/run/docker.sock
    echo "Docker configured successfully"
else
    echo "Docker socket not available, skipping Docker setup"
fi

echo "Post-create setup completed!"
