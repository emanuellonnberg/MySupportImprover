#!/bin/bash
# Package script for My Support Improver Cura Plugin
# Creates a distributable package ready for installation

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}My Support Improver - Package Builder${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get version from plugin.json
VERSION=$(grep -o '"version": *"[^"]*"' plugin.json | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+')
PLUGIN_NAME="MySupportImprover"
PACKAGE_NAME="${PLUGIN_NAME}-${VERSION}"
BUILD_DIR="build"
PACKAGE_DIR="${BUILD_DIR}/${PLUGIN_NAME}"

echo -e "${YELLOW}Version:${NC} ${VERSION}"
echo -e "${YELLOW}Package:${NC} ${PACKAGE_NAME}.zip"
echo ""

# Clean previous build
if [ -d "$BUILD_DIR" ]; then
    echo "Cleaning previous build..."
    rm -rf "$BUILD_DIR"
fi

# Create build directory structure
echo "Creating package structure..."
mkdir -p "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR/qt6"

# Copy plugin files
echo "Copying plugin files..."
cp plugin.json "$PACKAGE_DIR/"
cp __init__.py "$PACKAGE_DIR/"
cp MySupportImprover.py "$PACKAGE_DIR/"
cp presets.json "$PACKAGE_DIR/"
cp down.svg "$PACKAGE_DIR/"
cp qt6/SupportImprover.qml "$PACKAGE_DIR/qt6/"

# Copy documentation
echo "Copying documentation..."
cp README.md "$PACKAGE_DIR/"
cp CHANGELOG.md "$PACKAGE_DIR/"

# Create the zip package
echo "Creating zip archive..."
cd "$BUILD_DIR"
zip -r "${PACKAGE_NAME}.zip" "$PLUGIN_NAME" -q

# Move zip to root and cleanup
mv "${PACKAGE_NAME}.zip" ..
cd ..

echo ""
echo -e "${GREEN}✓ Package created successfully!${NC}"
echo -e "${GREEN}✓ File: ${PACKAGE_NAME}.zip${NC}"
echo ""

# Calculate file size
SIZE=$(du -h "${PACKAGE_NAME}.zip" | cut -f1)
echo -e "${YELLOW}Package size:${NC} ${SIZE}"
echo ""

# Display installation instructions
echo -e "${YELLOW}Installation Instructions:${NC}"
echo "1. Open Cura"
echo "2. Go to: Help → Show Configuration Folder"
echo "3. Navigate to the 'plugins' folder"
echo "4. Extract ${PACKAGE_NAME}.zip into the plugins folder"
echo "5. Restart Cura"
echo ""

# List package contents
echo -e "${YELLOW}Package contents:${NC}"
unzip -l "${PACKAGE_NAME}.zip" | tail -n +4 | head -n -2

echo ""
echo -e "${GREEN}Done!${NC}"
