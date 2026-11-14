#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if grep -q "from 'expo-linear-gradient'" App.tsx; then echo 'FAIL: native LinearGradient import remains'; exit 1; fi
grep -q "GradientBackground" App.tsx
test -f src/components/GradientBackground.tsx
test -f assets/gradients/hero.png
if grep -q '<H>Quick Actions</H>' App.tsx; then echo 'FAIL: Quick Actions remains'; exit 1; fi
node -e "const p=require('./package.json'); if(p.dependencies['expo-linear-gradient']) process.exit(1); console.log('Native gradient dependency: not required');"
echo 'PASS: V10 gradient images, components, and no Quick Actions'
