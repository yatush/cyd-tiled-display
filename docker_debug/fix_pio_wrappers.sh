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
