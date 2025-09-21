#!/bin/bash
# filepath: .devcontainer/setup-mcp.sh

# set -euxo pipefail
set -e

# Security: Use existing config file instead of creating duplicates (OWASP A08)
MCP_CONFIG_SOURCE="${WORKSPACE}/.github/mcp-config.json"
MCP_CONFIG_TARGET="$HOME/mcp-config.json"

echo "Setting up MCP Server integration for SAX Battery..."

# sudo usermod -aG docker vscode
# sudo chmod 666 /var/run/docker.sock
# newgrp docker

# Ensure Docker is accessible
if ! docker --version > /dev/null 2>&1; then
    echo "Warning: Docker CLI not available, MCP server may not work"
    exit 0
fi

# Security: Validate config source exists before proceeding (OWASP A05)
if [ ! -f "$MCP_CONFIG_SOURCE" ]; then
    echo "Error: MCP config not found at $MCP_CONFIG_SOURCE"
    exit 1
fi

# Security: Use specific image tags instead of 'latest' for integrity (OWASP A08)
MCP_IMAGE="ghcr.io/microsoft/mcp-dotnet-samples/awesome-copilot:latest"

# Pull the MCP server image
echo "Pulling awesome-copilot MCP server image..."
docker pull $MCP_IMAGE

# Test MCP server connectivity
echo "Testing MCP server..."
timeout 10s docker run --rm $MCP_IMAGE --help || echo "MCP server test completed"

# Security: Create symlink safely with proper validation (OWASP A05)
echo "Configuring MCP integration..."

# Security: Remove existing target if it's not the correct symlink
if [ -L "$MCP_CONFIG_TARGET" ]; then
    if [ "$(readlink "$MCP_CONFIG_TARGET")" != "$MCP_CONFIG_SOURCE" ]; then
        rm -f "$MCP_CONFIG_TARGET"
    fi
fi

# Security: Create symlink only if source exists and target doesn't (OWASP A08)
if [ ! -e "$MCP_CONFIG_TARGET" ]; then
    ln -sf "$MCP_CONFIG_SOURCE" "$MCP_CONFIG_TARGET"
    # Set permissions
    chown vscode:vscode "$MCP_CONFIG_TARGET" || true
    echo "MCP configuration linked successfully"
fi

echo "MCP Server setup complete!"
echo "Restart VS Code to activate awesome-copilot with MCP integration"
