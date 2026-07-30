#!/usr/bin/env bash
# Plain demo you can run or screen-record by hand (no vhs needed).
# Scenario: a deploy just shipped; find the regression it introduced.
set -e
cd "$(dirname "$0")/.."

echo '$ loglens diff examples/before.log examples/after.log'
loglens diff examples/before.log examples/after.log
echo
echo '# Add --explain for a plain-English summary (needs OPENAI_API_KEY):'
echo '$ loglens diff examples/before.log examples/after.log --explain'
