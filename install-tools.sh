#!/bin/bash
# Quick install script for missing development tools

set -e

echo "===================================="
echo "Installing Development Tools"
echo "===================================="

# Install .NET SDK 8.0
echo ""
echo "[1/3] Installing .NET SDK 8.0..."
if ! command -v dotnet &> /dev/null; then
    wget -q https://dot.net/v1/dotnet-install.sh
    chmod +x dotnet-install.sh
    ./dotnet-install.sh --channel 8.0 --install-dir $HOME/.dotnet
    rm dotnet-install.sh

    # Add to PATH
    echo 'export PATH=$PATH:$HOME/.dotnet' >> ~/.bashrc
    export PATH=$PATH:$HOME/.dotnet

    echo "✅ .NET SDK installed: $($HOME/.dotnet/dotnet --version)"
else
    echo "✅ .NET already installed: $(dotnet --version)"
fi

# Install Rust + Cargo
echo ""
echo "[2/3] Installing Rust + Cargo..."
if ! command -v rustc &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
    echo "✅ Rust installed: $(rustc --version)"
else
    echo "✅ Rust already installed: $(rustc --version)"
fi

# Install CMake
echo ""
echo "[3/3] Installing CMake..."
if ! command -v cmake &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y cmake
    echo "✅ CMake installed: $(cmake --version | head -1)"
else
    echo "✅ CMake already installed: $(cmake --version | head -1)"
fi

echo ""
echo "===================================="
echo "✅ Installation Complete!"
echo "===================================="
echo ""
echo "Installed tools:"
echo "  - .NET SDK: $($HOME/.dotnet/dotnet --version 2>/dev/null || echo 'N/A')"
echo "  - Rust: $(rustc --version 2>/dev/null || echo 'N/A')"
echo "  - Cargo: $(cargo --version 2>/dev/null || echo 'N/A')"
echo "  - CMake: $(cmake --version 2>/dev/null | head -1 || echo 'N/A')"
echo ""
echo "NOTE: Restart your terminal or run: source ~/.bashrc"
