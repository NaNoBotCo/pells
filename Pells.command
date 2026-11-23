#!/bin/bash
# Double-click in Finder to open the Pells desk in your browser.
# The work folder is ~/Pells-work; write another folder after WORK= to change it.
cd "$(dirname "$0")" || exit 1
WORK="${PELLS_WORK:-$HOME/Pells-work}"
exec /usr/bin/env python3 -m pells desk --work "$WORK"
