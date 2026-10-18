#!/bin/sh
# Compile the app's Models.swift with main.swift and run it against the backend.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
models="$here/../../../frontend/ios/CrewSafe/Models/Models.swift"
mkdir -p "$here/.build"
swiftc -o "$here/.build/ios_contract_check" "$models" "$here/main.swift"
"$here/.build/ios_contract_check" "$@"
