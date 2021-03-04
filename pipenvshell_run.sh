#!/usr/bin/env bash

echo "NOTICE!"
echo "I only login into the virtual env"
echo ""

# This file was created because you may want to test many small python scripts in a virtual environment. 'pipenv shell' is much faster at this.
# feel free to replace run.sh with me if that is your task

# Note: pipenv shell does not use a login shell

git pull --ff-only
pipenv install --dev
pipenv shell
#pipenv run python3 connect.py
