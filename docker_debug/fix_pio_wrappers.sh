#!/bin/bash
# fix_pio_wrappers.sh - Replace PlatformIO's Rust wrapper binaries with shell scripts
# for Alpine Linux (musl) compatibility.
#
# PlatformIO's xtensa toolchain includes Rust-compiled wrapper binaries that
# translate chip-specific tool names (e.g., xtensa-esp32-elf-gcc) to the
# generic tools (xtensa-esp-elf-gcc) with appropriate -mdynconfig flags.
# These Rust binaries require glibc runtime features beyond what gcompat
# provides on Alpine. This script replaces them with equivalent shell scripts.

set -e

# ---------------------------------------------------------------------------
# Step 0: Ensure SSL certificates are present so HTTPS downloads work.
# On Alpine, idf_tools.py download fails silently (no .tmp file created) when
# CA certificates are missing — the rename of .tmp → final file then throws
# FileNotFoundError.
# ---------------------------------------------------------------------------
echo "=== Updating CA certificates ==="
apk add --no-cache ca-certificates 2>/dev/null || true
update-ca-certificates 2>/dev/null || true

# Ensure the PlatformIO dist cache directory exists (idf_tools.py does mkdir
# itself, but creating it early avoids any race / permission edge cases).
mkdir -p /root/.platformio/dist

# ---------------------------------------------------------------------------
# Step 1: Fix esptool installation.
# PlatformIO downloads tool-esptoolpy as a source tarball and runs
# `pip install .` inside it.  On Alpine the extracted directory sometimes
# appears empty (corrupt download or pip metadata issue), causing:
#   "does not appear to be a Python project, as neither pyproject.toml nor
#    setup.py are present"
# Work-around: install esptool at the OS/pip level and symlink it into the
# PlatformIO tool directory so PlatformIO finds a working esptool binary.
# ---------------------------------------------------------------------------
echo "=== Ensuring esptool is available ==="
if ! python3 -m esptool version >/dev/null 2>&1; then
    pip3 install --break-system-packages esptool 2>/dev/null || pip3 install esptool 2>/dev/null || true
fi

# If PlatformIO's esptoolpy package directory exists but is broken, patch it.
ESPTOOL_PIO_DIR=$(find /root/.platformio/packages -maxdepth 1 -name 'tool-esptoolpy*' -type d 2>/dev/null | head -1)
if [ -n "$ESPTOOL_PIO_DIR" ]; then
    ESPTOOL_BIN=$(command -v esptool.py 2>/dev/null || command -v esptool 2>/dev/null)
    if [ -n "$ESPTOOL_BIN" ]; then
        # Make sure esptool.py exists in the tool dir so PlatformIO can invoke it
        if [ ! -f "$ESPTOOL_PIO_DIR/esptool.py" ]; then
            echo "  Symlinking $ESPTOOL_BIN -> $ESPTOOL_PIO_DIR/esptool.py"
            ln -sf "$ESPTOOL_BIN" "$ESPTOOL_PIO_DIR/esptool.py"
        fi
        echo "  esptool OK: $ESPTOOL_BIN"
    else
        echo "  WARNING: esptool not found in PATH after pip install attempt"
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: Replace Rust wrapper binaries in the xtensa toolchain.
# ---------------------------------------------------------------------------
TOOLCHAIN_DIR=$(find /root/.platformio/packages -maxdepth 1 -name 'toolchain-xtensa-esp-elf*' -type d 2>/dev/null | head -1)

if [ -z "$TOOLCHAIN_DIR" ]; then
    TOOLCHAIN_DIR=$(ls -d /root/.platformio/packages/toolchain-xtensa-esp-elf* 2>/dev/null | head -1)
fi

if [ -z "$TOOLCHAIN_DIR" ]; then
    echo "WARNING: toolchain-xtensa-esp-elf not found in /root/.platformio/packages/"
    echo "This is expected if the toolchain hasn't been downloaded yet."
    echo "Attempting to locate any xtensa toolchain..."
    TOOLCHAIN_DIR=$(find /root/.platformio/packages -maxdepth 1 -name 'toolchain-xtensa*' -type d 2>/dev/null | head -1)
fi
if [ -z "$TOOLCHAIN_DIR" ]; then
    echo "No toolchain found. Exiting."
    exit 0
fi

BIN_DIR="$TOOLCHAIN_DIR/bin"
echo "Fixing Rust wrappers in $BIN_DIR/"

# Detect GCC version for LD_LIBRARY_PATH (dynconfig .so files are in TOOLCHAIN_DIR/lib/)
GCC_VERSION=$(ls "$TOOLCHAIN_DIR/lib/gcc/xtensa-esp-elf/" 2>/dev/null | head -1)
if [ -z "$GCC_VERSION" ]; then
    echo "ERROR: Cannot detect GCC version in $TOOLCHAIN_DIR/lib/gcc/xtensa-esp-elf/"
    exit 1
fi

# Dynconfig .so files (xtensa_esp32.so, etc.) live in the toolchain's top-level lib/
LIB_DIR="$TOOLCHAIN_DIR/lib"
echo "GCC version: $GCC_VERSION"
echo "Dynconfig lib dir: $LIB_DIR"

# Tools that need -mdynconfig flag (compilers and assembler)
COMPILER_TOOLS="gcc g++ cc c++ cpp as"

# Chips and their dynconfig .so files
CHIPS="esp32 esp32s2 esp32s3"

REPLACED=0

for chip in $CHIPS; do
    dynconfig="xtensa_${chip}.so"
    prefix="xtensa-${chip}-elf-"

    # Verify dynconfig .so exists
    if [ ! -f "$LIB_DIR/$dynconfig" ]; then
        echo "  WARNING: $LIB_DIR/$dynconfig not found, looking for alternative locations"
        # Try to find the dynconfig file recursively
        FOUND_DYN=$(find "$TOOLCHAIN_DIR" -name "$dynconfig" | head -1)
        if [ -n "$FOUND_DYN" ]; then
            LIB_DIR=$(dirname "$FOUND_DYN")
            echo "  Found dynconfig at $LIB_DIR"
        else
            echo "  SKIPPING $chip wrappers"
            continue
        fi
    fi

    for wrapper in "$BIN_DIR"/${prefix}*; do
        [ -f "$wrapper" ] || continue

        tool_name=$(basename "$wrapper")
        # Extract the tool suffix (e.g., "gcc" from "xtensa-esp32-elf-gcc")
        suffix="${tool_name#${prefix}}"

        # The real (generic) tool name
        real_tool="xtensa-esp-elf-${suffix}"
        real_path="$BIN_DIR/$real_tool"

        # Skip if the real tool doesn't exist
        if [ ! -f "$real_path" ]; then
            echo "  SKIP $tool_name (no matching $real_tool)"
            continue
        fi

        # Skip if this IS the real tool (not a wrapper)
        if [ "$tool_name" = "$real_tool" ]; then
            continue
        fi

        # Only replace ELF binaries (Rust wrappers are compiled ELF binaries).
        # We previously used a size check but wrapper sizes vary across toolchain versions.
        # Instead, check for the ELF magic number (\x7fELF) in the first 4 bytes.
        magic=$(dd if="$wrapper" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')
        if [ "$magic" != "7f454c46" ]; then
            echo "  SKIP $tool_name (not an ELF binary - already a shell script?)"
            continue
        fi

        # Determine if this tool needs -mdynconfig
        needs_dynconfig=false
        for ct in $COMPILER_TOOLS; do
            if [ "$suffix" = "$ct" ]; then
                needs_dynconfig=true
                break
            fi
        done

        # Replace the Rust wrapper with a shell script
        rm -f "$wrapper"

        if [ "$needs_dynconfig" = true ]; then
            cat > "$wrapper" << WRAPPER_EOF
#!/bin/sh
export LD_LIBRARY_PATH="$LIB_DIR:\${LD_LIBRARY_PATH:-}"
exec "$real_path" -mdynconfig=$dynconfig "\$@"
WRAPPER_EOF
        else
             cat > "$wrapper" << WRAPPER_EOF
#!/bin/sh
export LD_LIBRARY_PATH="$LIB_DIR:\${LD_LIBRARY_PATH:-}"
exec "$real_path" "\$@"
WRAPPER_EOF
        fi
        
        chmod +x "$wrapper"
        echo "  REPLACED $tool_name with shell script"
        REPLACED=$((REPLACED + 1))
    done
done

echo "Replaced $REPLACED Rust wrapper binaries with shell scripts"

# ---------------------------------------------------------------------------
# Step 3: Fix PlatformIO's bundled ninja.
# It's a glibc binary that deadlocks under gcompat on musl/Alpine.
# Replace it with the system ninja (apk install ninja) which is natively compiled.
# ---------------------------------------------------------------------------
NINJA_PIO=$(find /root/.platformio/packages/tool-ninja -name 'ninja' -not -name '*.bak' 2>/dev/null | head -1)
if [ -n "$NINJA_PIO" ]; then
    # Install system ninja if not present
    if ! command -v ninja >/dev/null 2>&1; then
        echo "Installing system ninja..."
        apk add --no-cache ninja 2>/dev/null || true
    fi
    SYSTEM_NINJA=$(command -v ninja 2>/dev/null)
    if [ -n "$SYSTEM_NINJA" ] && [ "$SYSTEM_NINJA" != "$NINJA_PIO" ]; then
        echo "Replacing PlatformIO ninja with system ninja ($SYSTEM_NINJA)..."
        cp -f "$NINJA_PIO" "${NINJA_PIO}.bak" 2>/dev/null || true
        ln -sf "$SYSTEM_NINJA" "$NINJA_PIO"
        echo "  ninja version: $($SYSTEM_NINJA --version 2>/dev/null)"
    else
        echo "System ninja not available or already linked — skipping ninja fix"
    fi
fi
