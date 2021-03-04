#!/usr/bin/env bash

git pull --ff-only

set -e
set -o pipefail

pipenv run coverage run -m pytest

# more verbose output
# https://www.patricksoftwareblog.com/testing-a-flask-application-using-pytest/
#pipenv run pytest --setup-show tests/unit/
# also more verbose output
#pipenv run pytest -v

pipenv run coverage report
# to see the html report with highlighting of the uncovered code
#pipenv run coverage html