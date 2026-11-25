#!/bin/bash
# Open settings using a standalone Python; prefer the tested python.org 3.13.
cd -- "$(dirname -- "$0")" || exit 1
notification_python=""
for notification_version in 3.13 3.14 3.15; do
    notification_candidate="/Library/Frameworks/Python.framework/Versions/$notification_version/bin/python$notification_version"
    if [ -x "$notification_candidate" ]; then
        notification_python="$notification_candidate"
        break
    fi
done
if [ -z "$notification_python" ]; then
    notification_python="$(command -v python3)"
fi
if [ -z "$notification_python" ]; then
    printf 'Install Python from https://www.python.org/downloads/macos/ first.\n'
else
    "$notification_python" notification_settings.py
    notification_exit=$?
    if [ "$notification_exit" -eq 0 ]; then
        exit 0
    fi
fi
printf '\nSee README.md for setup. Press Return to close.\n'
read -r notification_reply
exit 1
