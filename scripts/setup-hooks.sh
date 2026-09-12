#!/usr/bin/env bash
# Activa los hooks de git del repo. Córrelo una vez después de clonar.
set -e
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✓ Hooks activados. Los mensajes de commit ahora se validan contra Conventional Commits."
