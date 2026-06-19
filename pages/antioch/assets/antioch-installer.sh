#!/usr/bin/env bash
# Antioch Framework - Portable Installer
# Single-command installation: curl -sSL <url> | bash
# Or download and run: bash antioch-installer.sh

set -e

INSTALL_DIR="${HOME}/.antioch"
BIN_DIR="${HOME}/.local/bin"
ANTIOCH_VERSION="0.1.0"
GITHUB_REPO="https://github.com/nielrya4/antioch.git"
GITHUB_BRANCH="master"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║                    Antioch Framework                           ║"
    echo "║                  Portable Installer v${ANTIOCH_VERSION}                    ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}▶${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Parse command line arguments
UNINSTALL=false
SYSTEM_WIDE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --system)
            SYSTEM_WIDE=true
            INSTALL_DIR="/opt/antioch"
            BIN_DIR="/usr/local/bin"
            shift
            ;;
        --repo)
            GITHUB_REPO="$2"
            shift 2
            ;;
        --branch)
            GITHUB_BRANCH="$2"
            shift 2
            ;;
        --help|-h)
            echo "Antioch Framework Installer"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --system        Install system-wide (requires sudo, installs to /opt/antioch)"
            echo "  --repo URL      Specify GitHub repository URL (default: https://github.com/nielrya4/antioch.git)"
            echo "  --branch NAME   Specify branch to install (default: master)"
            echo "  --uninstall     Uninstall Antioch"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Default: Installs to ~/.antioch from GitHub master branch"
            echo ""
            echo "Examples:"
            echo "  $0                              # Install from GitHub master branch"
            echo "  $0 --branch dev                 # Install from GitHub dev branch"
            echo "  $0 --repo https://...           # Install from custom repository"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Uninstall
if [ "$UNINSTALL" = true ]; then
    print_header
    echo "Uninstalling Antioch..."
    echo ""

    if [ "$SYSTEM_WIDE" = true ] && [ "$EUID" -ne 0 ]; then
        print_error "System-wide uninstall requires sudo"
        echo "Run: sudo $0 --system --uninstall"
        exit 1
    fi

    if [ -d "$INSTALL_DIR" ]; then
        print_step "Removing $INSTALL_DIR"
        rm -rf "$INSTALL_DIR"
        print_success "Removed installation directory"
    fi

    if [ -f "$BIN_DIR/antioch" ]; then
        print_step "Removing $BIN_DIR/antioch"
        rm -f "$BIN_DIR/antioch"
        print_success "Removed antioch command"
    fi

    echo ""
    print_success "Antioch has been uninstalled"
    exit 0
fi

# Check for sudo if system-wide
if [ "$SYSTEM_WIDE" = true ] && [ "$EUID" -ne 0 ]; then
    print_error "System-wide installation requires sudo"
    echo "Run: sudo $0 --system"
    exit 1
fi

print_header

# Check Python version
print_step "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    echo "Please install Python 3.9 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_success "Found Python $PYTHON_VERSION"

# Check minimum version (3.9)
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    print_error "Python 3.9 or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

# Create installation directory
print_step "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
print_success "Created $INSTALL_DIR"

# Check for git (required)
if ! command -v git &> /dev/null; then
    print_error "Git is not installed"
    echo "Please install git to use the Antioch installer"
    exit 1
fi

print_step "Cloning from GitHub: $GITHUB_REPO (branch: $GITHUB_BRANCH)"

# Create temp directory for clone
TEMP_CLONE=$(mktemp -d)

# Clone the repository
git clone --depth 1 --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$TEMP_CLONE" 2>&1 | grep -v "Cloning into" || true

# Copy antioch framework from GitHub
print_step "  → Copying antioch framework from GitHub"
cp -r "$TEMP_CLONE/antioch" "$INSTALL_DIR/"

# Cleanup temp clone
rm -rf "$TEMP_CLONE"

# Extract CLI and build tools from embedded archive
print_step "  → Extracting CLI and build tools from installer"
ARCHIVE_LINE=$(awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0; }' "$0")
tail -n+${ARCHIVE_LINE} "$0" | base64 -d | tar -xzf - -C "$INSTALL_DIR" --strip-components=1

print_success "Installed from GitHub ($GITHUB_BRANCH branch)"

# Create bin directory
print_step "Setting up antioch command..."
mkdir -p "$BIN_DIR"

# Create the antioch executable
cat > "$BIN_DIR/antioch" << EXEC_EOF
#!/usr/bin/env bash
# Antioch CLI - Installed executable

# Add antioch install dir to Python path so CLI can import environment
export PYTHONPATH="$INSTALL_DIR:\$PYTHONPATH"

# Run CLI in current directory (not install directory)
python3 "$INSTALL_DIR/cli.py" "\$@"
EXEC_EOF

chmod +x "$BIN_DIR/antioch"
print_success "Created antioch command at $BIN_DIR/antioch"

# Check if bin dir is in PATH
echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    print_warning "$BIN_DIR is not in your PATH"
    echo ""
    echo "Add it by adding this line to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    echo ""
    echo "Then reload your shell: source ~/.bashrc"
else
    print_success "$BIN_DIR is already in your PATH"
fi

# Installation complete
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                                ║${NC}"
echo -e "${GREEN}║         ✓ Antioch Framework installed successfully!            ║${NC}"
echo -e "${GREEN}║                                                                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Installation location: $INSTALL_DIR"
echo "Executable: $BIN_DIR/antioch"
echo ""
echo "Quick Start:"
echo "  1. Create a new project directory"
echo "  2. Run: antioch build"
echo "  3. Run: antioch run"
echo ""
echo "Documentation: $INSTALL_DIR/README_CLI.md"
echo ""
echo "To uninstall: $0 --uninstall"
echo ""

exit 0

__ARCHIVE_BELOW__
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
