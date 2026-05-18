#!/bin/bash

set -e

MESSAGE="$1"

if [ -z "$MESSAGE" ]; then
    echo "Usage: ./dev_step.sh \"commit message\""
    exit 1
fi

./quick_check.sh

echo "Changed files:"
git status --short

if [ -z "$(git status --short)" ]; then
    echo "Nothing to commit."
    exit 0
fi

git add app tests requirements.txt smoke_test.sh quick_check.sh dev_step.sh Procfile CHANGELOG.md
git commit -m "$MESSAGE"
git push

echo "Pushed: $MESSAGE"
