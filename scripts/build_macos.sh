#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BUILD_ROOT="$PROJECT_ROOT/.artifacts"
BUILD_ENV="$BUILD_ROOT/macos-venv"
DIST_ROOT="$BUILD_ROOT/macos-dist"
WORK_ROOT="$BUILD_ROOT/macos-build"
ICONSET_ROOT="$BUILD_ROOT/AppIcon.iconset"
ICNS_PATH="$BUILD_ROOT/靶场扫描助手.icns"
RELEASE_ROOT="$BUILD_ROOT/release"
RELEASE_VERSION="${RELEASE_VERSION:-local}"
APP_NAME="靶场扫描助手"
PNG_PATH="$PROJECT_ROOT/scanner_app/desktop/web/app_icon.png"

cd "$PROJECT_ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS." >&2
  exit 1
fi

if [[ ! -x "$BUILD_ENV/bin/python" ]]; then
  python3 -m venv "$BUILD_ENV"
fi

PYTHON="$BUILD_ENV/bin/python"
"$PYTHON" -m pip install -r "$PROJECT_ROOT/requirements-build.txt" \
  'pyobjc-framework-Cocoa>=9' \
  'pyobjc-framework-Quartz>=9' \
  'pyobjc-framework-WebKit>=9' \
  'pyobjc-framework-security>=9' \
  'pyobjc-framework-UniformTypeIdentifiers>=9'

rm -rf "$DIST_ROOT" "$WORK_ROOT" "$ICONSET_ROOT" "$ICNS_PATH"
mkdir -p "$DIST_ROOT" "$WORK_ROOT" "$ICONSET_ROOT" "$RELEASE_ROOT"

# macOS requires an .icns container for the application bundle icon.
sips -z 16 16 "$PNG_PATH" --out "$ICONSET_ROOT/icon_16x16.png" >/dev/null
sips -z 32 32 "$PNG_PATH" --out "$ICONSET_ROOT/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$PNG_PATH" --out "$ICONSET_ROOT/icon_32x32.png" >/dev/null
sips -z 64 64 "$PNG_PATH" --out "$ICONSET_ROOT/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$PNG_PATH" --out "$ICONSET_ROOT/icon_128x128.png" >/dev/null
sips -z 256 256 "$PNG_PATH" --out "$ICONSET_ROOT/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$PNG_PATH" --out "$ICONSET_ROOT/icon_256x256.png" >/dev/null
sips -z 512 512 "$PNG_PATH" --out "$ICONSET_ROOT/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$PNG_PATH" --out "$ICONSET_ROOT/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$PNG_PATH" --out "$ICONSET_ROOT/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET_ROOT" -o "$ICNS_PATH"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --icon "$ICNS_PATH" \
  --collect-all webview \
  --add-data "$PROJECT_ROOT/scanner_app/desktop/web:scanner_app/desktop/web" \
  --distpath "$DIST_ROOT" \
  --workpath "$WORK_ROOT" \
  "$PROJECT_ROOT/scanner_app/desktop/gui.py"

APP_PATH="$DIST_ROOT/$APP_NAME.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "PyInstaller did not create $APP_PATH" >&2
  exit 1
fi

case "$(uname -m)" in
  arm64) ARCH_LABEL="arm64" ;;
  x86_64) ARCH_LABEL="x64" ;;
  *) ARCH_LABEL="$(uname -m)" ;;
esac

ZIP_PATH="$RELEASE_ROOT/yucedu-vlunhub-scan-${RELEASE_VERSION}-macos-${ARCH_LABEL}.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
echo "Built: $ZIP_PATH"
shasum -a 256 "$ZIP_PATH"
