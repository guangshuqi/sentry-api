#!/bin/bash
# Wrapper script to run sentry CLI from anywhere
cd "$(dirname "$0")" && uv run ./sentry "$@"
