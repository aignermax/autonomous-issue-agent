#!/bin/bash
# install-dev-environment.sh - Complete Development Environment Setup for WSL
#
# This script installs ALL necessary tools for the autonomous agent:
# - Rust + Cargo (for Vulkan/SPIR-V work)
# - .NET SDK 8.0 (for C# / Avalonia projects)
# - Vulkan SDK + validation layers
# - Build tools (pkg-config, build-essential)

set -e

echo "=================================================================="
echo "  Autonomous Agent - Complete Development Environment Setup"
echo "=================================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
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

print_section() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
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

# ============================================================================
# 1. Install/Update Rust toolchain
# ============================================================================
print_section "1. Installing Rust Toolchain"

if ! command -v rustc &> /dev/null; then
    print_info "Rust not found, installing..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
    print_status "Rust installed: $(rustc --version)"
else
    print_status "Rust already installed: $(rustc --version)"
    print_info "Updating Rust to latest stable..."
    rustup update stable 2>&1 | grep -E "installed|unchanged" || true
fi

# Ensure cargo is in PATH for this script
source $HOME/.cargo/env

print_status "Cargo version: $(cargo --version)"

# ============================================================================
# 2. Update package lists
# ============================================================================
print_section "2. Updating Package Lists"

sudo apt-get update -qq
print_status "Package lists updated"

# ============================================================================
# 3. Install build essentials and pkg-config
# ============================================================================
print_section "3. Installing Build Dependencies"

sudo apt-get install -y pkg-config build-essential dos2unix
print_status "pkg-config installed: $(pkg-config --version)"
print_status "build-essential installed"
print_status "dos2unix installed (for line ending conversion)"

# ============================================================================
# 4. Install Vulkan development tools
# ============================================================================
print_section "4. Installing Vulkan Development Tools"

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

# ============================================================================
# 5. Install .NET SDK 8.0
# ============================================================================
print_section "5. Installing .NET SDK 8.0"

if ! command -v dotnet &> /dev/null; then
    print_info ".NET not found, installing..."

    # Download and run .NET install script
    wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
    chmod +x /tmp/dotnet-install.sh
    /tmp/dotnet-install.sh --channel 8.0 --install-dir $HOME/.dotnet
    rm /tmp/dotnet-install.sh

    # Add to PATH for this session
    export DOTNET_ROOT=$HOME/.dotnet
    export PATH=$PATH:$DOTNET_ROOT:$DOTNET_ROOT/tools

    print_status ".NET SDK installed: $($HOME/.dotnet/dotnet --version)"
else
    print_status ".NET SDK already installed: $(dotnet --version)"
fi

# Add .NET to shell config if not already there
if ! grep -q "DOTNET_ROOT" ~/.bashrc; then
    print_info "Adding .NET to ~/.bashrc..."
    cat >> ~/.bashrc << 'EOF'

# .NET SDK
export DOTNET_ROOT=$HOME/.dotnet
export PATH=$PATH:$DOTNET_ROOT:$DOTNET_ROOT/tools
EOF
    print_status "Added .NET to ~/.bashrc"
fi

# ============================================================================
# 6. Verify all installations
# ============================================================================
print_section "6. Verifying Installations"

# Ensure paths are set
source $HOME/.cargo/env
export DOTNET_ROOT=$HOME/.dotnet
export PATH=$PATH:$DOTNET_ROOT

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
else
    print_error "vulkaninfo not available"
fi

# Check .NET
if [ -x "$HOME/.dotnet/dotnet" ]; then
    print_status ".NET SDK: $($HOME/.dotnet/dotnet --version)"
else
    print_error ".NET SDK not found"
fi

echo ""
print_section "✅ Installation Complete!"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "Environment summary:"
echo "  • Rust:       $(rustc --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • Cargo:      $(cargo --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • pkg-config: $(pkg-config --version 2>/dev/null || echo 'NOT FOUND')"
echo "  • Vulkan SDK: $(pkg-config --modversion vulkan 2>/dev/null || echo 'NOT FOUND')"
echo "  • .NET SDK:   $($HOME/.dotnet/dotnet --version 2>/dev/null || echo 'NOT FOUND')"
echo ""
echo "To use Rust in new terminal sessions:"
echo "    ${GREEN}source \$HOME/.cargo/env${NC}"
echo ""
echo "To use .NET in new terminal sessions:"
echo "    ${GREEN}export DOTNET_ROOT=\$HOME/.dotnet${NC}"
echo "    ${GREEN}export PATH=\$PATH:\$DOTNET_ROOT${NC}"
echo ""
echo "Or simply open a new terminal (paths added to ~/.bashrc)"
echo ""
echo "You can now:"
echo "  • Build Rust projects:   ${GREEN}cargo build${NC}"
echo "  • Build .NET projects:   ${GREEN}dotnet build${NC}"
echo "  • Test Vulkan apps:      ${GREEN}vulkaninfo${NC}"
echo "  • Develop Vulkan layers and C#/Avalonia applications"
echo ""
echo "The autonomous agent now has ALL required dependencies! 🎉"
echo ""

# ============================================================================
# Optional: Display Vulkan info
# ============================================================================
if command -v vulkaninfo &> /dev/null; then
    echo ""
    print_info "Vulkan Instance Information:"
    echo ""
    vulkaninfo --summary 2>&1 | head -25 || true
fi
