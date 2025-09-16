#!/usr/bin/env bash
export VIRTUAL_ENV="$HOME/.local/ha-venv"
source "$VIRTUAL_ENV/bin/activate"
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

# Setup MCP server integration
echo "Setting up MCP server integration..."
if [ -f "/workspaces/sax_battery_ha/.scripts/setup-mcp.sh" ]; then
    bash /workspaces/sax_battery_ha/.scripts/setup-mcp.sh
else
    echo "Warning: MCP setup script not found at /workspaces/sax_battery_ha/.scripts/setup-mcp.sh"
    echo "MCP integration will not be available"
fi

echo "Post-create setup completed!"
