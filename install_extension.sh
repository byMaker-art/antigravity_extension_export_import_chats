#!/usr/bin/env bash
# Antigravity IDE Extension Installer for Chat Sync
# Installs extension into ~/.antigravity-ide/extensions/

set -e

VERSION="1.0.1"
EXT_DIR="$HOME/.antigravity-ide/extensions/bymaker.antigravity-chat-sync-$VERSION"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)/vscode-extension"

echo "=== Installing Antigravity Chat Sync Extension v$VERSION ==="
# Remove older versions if present
rm -rf "$HOME/.antigravity-ide/extensions/bymaker.antigravity-chat-sync-"*
mkdir -p "$EXT_DIR"
cp -R "$SRC_DIR/"* "$EXT_DIR/"
cp "$(cd "$(dirname "$0")" && pwd)/antigravity_chat_sync.py" "$EXT_DIR/scripts/antigravity_chat_sync.py"
chmod +x "$EXT_DIR/scripts/antigravity_chat_sync.py"

echo "✓ Extension installed successfully to: $EXT_DIR"
echo "Restart Antigravity IDE or reload window (Cmd+Shift+P -> Developer: Reload Window) to activate."
