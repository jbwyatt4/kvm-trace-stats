#!/usr/bin/env bash

# Uses the Pipfile ('pipenv install x' will create one)
pipenv install --dev

#pipenv run python3 core-sched-stats.py # some distros are still on py2 # debian/ubuntu
python3 core-sched-stats.py $1
