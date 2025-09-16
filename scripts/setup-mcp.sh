#!/bin/bash
# filepath: .devcontainer/setup-mcp.sh

set -e

echo "Setting up MCP Server integration for SAX Battery..."

# Ensure Docker is accessible
if ! docker --version > /dev/null 2>&1; then
    echo "Warning: Docker CLI not available, MCP server may not work"
    exit 1
fi

# Pull the MCP server image
echo "Pulling awesome-copilot MCP server image..."
docker pull ghcr.io/microsoft/mcp-dotnet-samples/awesome-copilot:latest

# Test MCP server connectivity
echo "Testing MCP server..."
timeout 10s docker run --rm ghcr.io/microsoft/mcp-dotnet-samples/awesome-copilot:latest --help || echo "MCP server test completed"

# Create symlink for easy access to MCP config
ln -sf /workspaces/sax_battery_ha/.github/mcp-config.json /home/vscode/.mcp-config.json

# Set permissions
chown vscode:vscode /home/vscode/.mcp-config.json || true

echo "MCP Server setup complete!"
echo "Restart VS Code to activate awesome-copilot with MCP integration"
