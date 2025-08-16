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
