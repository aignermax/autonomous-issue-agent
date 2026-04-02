#!/bin/bash
# install-vulkan-dev.sh - Setup WSL for Vulkan + Rust development
#
# This script installs all necessary tools for complex Vulkan testing in WSL
# including Rust, Cargo, build tools, and Vulkan SDK components.

set -e

echo "=================================================="
echo "  Vulkan Development Environment Setup for WSL"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[i]${NC} $1"
}

# Check if running in WSL
if ! grep -qi microsoft /proc/version; then
    print_error "This script is designed for WSL (Windows Subsystem for Linux)"
    print_info "Detected system: $(uname -a)"
    exit 1
fi

print_status "Running in WSL environment"
print_info "Architecture: $(uname -m)"
echo ""

# 1. Install/Update Rust toolchain
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Installing Rust toolchain"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v rustc &> /dev/null; then
    print_info "Rust not found, installing..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
    print_status "Rust installed: $(rustc --version)"
else
    print_status "Rust already installed: $(rustc --version)"
    print_info "Updating Rust to latest stable..."
    rustup update stable
fi

# Ensure cargo is in PATH for this script
source $HOME/.cargo/env

print_status "Cargo version: $(cargo --version)"
echo ""

# 2. Update package lists
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Updating package lists"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sudo apt-get update
print_status "Package lists updated"
echo ""

# 3. Install build essentials and pkg-config
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Installing build dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sudo apt-get install -y pkg-config
print_status "pkg-config installed: $(pkg-config --version)"
echo ""

# 4. Install Vulkan development tools
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Installing Vulkan development tools"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

print_info "Installing Vulkan libraries and headers..."

sudo apt-get install -y \
    libvulkan-dev \
    vulkan-tools \
    vulkan-validationlayers \
    libxcb1-dev \
    libxrandr-dev \
    libx11-xcb-dev \
    mesa-vulkan-drivers

print_status "Vulkan development packages installed"
echo ""

# 5. Verify installations
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Verifying installations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Rust
if command -v rustc &> /dev/null; then
    print_status "Rust: $(rustc --version)"
else
    print_error "Rust not found in PATH"
fi

# Check Cargo
if command -v cargo &> /dev/null; then
    print_status "Cargo: $(cargo --version)"
else
    print_error "Cargo not found in PATH"
fi

# Check pkg-config
if command -v pkg-config &> /dev/null; then
    print_status "pkg-config: $(pkg-config --version)"
else
    print_error "pkg-config not found"
fi

# Check Vulkan
if pkg-config --exists vulkan; then
    VULKAN_VERSION=$(pkg-config --modversion vulkan)
    print_status "Vulkan headers: version $VULKAN_VERSION"
else
    print_error "Vulkan development headers not found"
fi

# Check vulkaninfo
if command -v vulkaninfo &> /dev/null; then
    print_status "vulkaninfo tool available"
    echo ""
    print_info "Running vulkaninfo to detect GPUs..."
    vulkaninfo --summary 2>&1 | head -30 || true
else
    print_error "vulkaninfo not available"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Environment summary:"
echo "  • Rust:       $(rustc --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • Cargo:      $(cargo --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • pkg-config: $(pkg-config --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • Vulkan:     $(pkg-config --modversion vulkan 2>/dev/null || echo 'NOT FOUND')"
echo ""
echo "To use Rust in new terminal sessions, the following line"
echo "has been added to your shell configuration:"
echo ""
echo "    source \$HOME/.cargo/env"
echo ""
echo "For THIS session, run:"
echo "    ${GREEN}source \$HOME/.cargo/env${NC}"
echo ""
echo "You can now:"
echo "  • Build Rust projects with: ${GREEN}cargo build${NC}"
echo "  • Test Vulkan apps with: ${GREEN}vulkaninfo${NC}"
echo "  • Develop Vulkan layers and applications"
echo ""
