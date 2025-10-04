---
description: "Development environment setup and tooling information"
---

# Development Environment

This workspace is configured as a development container with pre-installed tools and dependencies for SAX Battery Home Assistant integration development.

## Environment Details

- **Operating System**: Debian GNU/Linux 12 (bookworm)
- **Container**: Dev container with up-to-date tools
- **Browser Integration**: Use `"$BROWSER" <url>` to open webpages in the host's default browser

## Pre-installed Tools

### Version Control

- `git` - Built from source, latest version available on `PATH`

### Node.js Development

- `node` - Node.js runtime
- `npm` - Node package manager  
- `eslint` - JavaScript linting

### Python Development

- `python3` - Python 3.13+ runtime
- `pip3` - Python package manager
- Python language extensions for development

### System Utilities

Command line tools available on `PATH`:

- **Package management**: `apt`, `dpkg`
- **Network tools**: `curl`, `wget`, `ssh`, `scp`, `rsync`
- **System monitoring**: `ps`, `lsof`, `netstat`, `top`
- **File operations**: `tree`, `find`, `grep`
- **Archive tools**: `zip`, `unzip`, `tar`, `gzip`, `bzip2`, `xz`
- **Security**: `gpg`

## Development Workflow

The development environment is optimized for:

- Python 3.13+ development with Home Assistant
- Linting and formatting with Ruff and PyLint
- Type checking with MyPy
- Testing with pytest
- Version control with Git
- SAX Battery system integration development

## Project Structure

This workspace contains:

- SAX Battery custom integration for Home Assistant
- Multi-battery system coordination code
- Modbus TCP/IP communication protocols
- Comprehensive testing framework
