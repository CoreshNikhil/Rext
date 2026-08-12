#!/bin/bash
# launch.json's preview_start runs commands from the repo root, but
# flutter needs pubspec.yaml in its cwd — this wrapper bridges that.
#
# Builds a release web bundle and serves it statically rather than using
# `flutter run`'s dev-mode server: dev mode's hot-reload/DWDS machinery
# expects an interactive stdin, which doesn't suit a backgrounded
# automated launch — and building for real is a truer verification of
# what actually ships anyway.
set -e
cd "$(dirname "$0")"
/home/coresh/development/flutter/bin/flutter build web --release
exec python3 -m http.server 8503 --bind 0.0.0.0 --directory build/web
