#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║     COMPANION CORE — INSTALLER       ║${NC}"
echo -e "${BOLD}  ╚══════════════════════════════════════╝${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_DIR="$SCRIPT_DIR/llama.cpp"
MODELS_DIR="$SCRIPT_DIR/models"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ "$(uname -s)" != "Linux" ]]; then
    error "This script is for Linux only."
fi

if [[ "$EUID" -eq 0 ]]; then
    warn "Running as root. It's safer to run as a regular user."
fi

RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_GB=$(( RAM_KB / 1024 / 1024 ))

if [[ "$RAM_GB" -ge 12 ]]; then
    MODEL_FILENAME="qwen2.5-7b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
    MODEL_LABEL="Qwen2.5-7B Q4_K_M (~4.7 GB)"
else
    MODEL_FILENAME="qwen2.5-3b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
    MODEL_LABEL="Qwen2.5-3B Q4_K_M (~2.0 GB)"
fi

MODEL_PATH="$MODELS_DIR/$MODEL_FILENAME"

info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git cmake build-essential \
    libcurl4-openssl-dev wget curl \
    > /dev/null
success "System packages installed."

info "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q
success "Python environment ready."

LLAMA_BIN="$LLAMA_DIR/build/bin/llama-server"

if [[ -f "$LLAMA_BIN" ]]; then
    success "llama.cpp already built, skipping."
else
    info "Cloning llama.cpp..."
    if [[ -d "$LLAMA_DIR" ]]; then
        git -C "$LLAMA_DIR" pull --quiet
    else
        git clone --depth=1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR" --quiet
    fi

    ARCH="$(uname -m)"
    CMAKE_EXTRA_FLAGS=""
    if [[ "$ARCH" == "x86_64" ]]; then
        CMAKE_EXTRA_FLAGS="-DGGML_AVX=ON -DGGML_AVX2=OFF -DGGML_F16C=OFF -DGGML_FMA=OFF"
        info "Building llama.cpp (x86-64 universal)..."
    else
        info "Building llama.cpp (generic — arch: $ARCH)..."
    fi

    cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLAMA_NATIVE=OFF \
        -DGGML_BLAS=OFF \
        -DBUILD_SHARED_LIBS=OFF \
        $CMAKE_EXTRA_FLAGS \
        -Wno-dev \
        > /dev/null 2>&1

    cmake --build "$LLAMA_DIR/build" --config Release -j"$(nproc)" --target llama-server \
        > /dev/null 2>&1

    if [[ ! -f "$LLAMA_BIN" ]]; then
        error "Build failed. llama-server not found."
    fi
    success "llama.cpp built successfully."
fi

ln -sf "$LLAMA_BIN" "$SCRIPT_DIR/llama-server" 2>/dev/null || true

mkdir -p "$MODELS_DIR"

if [[ -f "$MODEL_PATH" ]]; then
    success "Model already exists: $MODEL_FILENAME"
else
    info "Downloading $MODEL_LABEL (RAM: ${RAM_GB}GB)..."
    info "This may take 5-30 minutes depending on your connection."
    echo ""

    if command -v wget &> /dev/null; then
        wget --progress=bar:force:noscroll \
             --header="User-Agent: Mozilla/5.0" \
             -O "$MODEL_PATH" "$MODEL_URL" \
             || error "Download failed."
    else
        curl -L --progress-bar \
             -H "User-Agent: Mozilla/5.0" \
             -o "$MODEL_PATH" "$MODEL_URL" \
             || error "Download failed."
    fi

    FILE_SIZE=$(stat -c%s "$MODEL_PATH" 2>/dev/null || echo 0)
    if [[ "$FILE_SIZE" -lt 100000000 ]]; then
        rm -f "$MODEL_PATH"
        error "Downloaded file is too small (corrupt?). Try again."
    fi

    success "Model downloaded: $MODEL_FILENAME"
fi

mkdir -p "$SCRIPT_DIR/memory"

if [[ ! -f "$SCRIPT_DIR/memory/facts.json" ]]; then
cat > "$SCRIPT_DIR/memory/facts.json" << 'EOF'
{
  "name": null,
  "age": null,
  "location": null,
  "occupation": null,
  "interests": [],
  "preferences": {},
  "misc": {}
}
EOF
fi

[[ ! -f "$SCRIPT_DIR/memory/dialogue.json" ]] && echo "[]" > "$SCRIPT_DIR/memory/dialogue.json"
[[ ! -f "$SCRIPT_DIR/memory/relationship.md" ]] && echo "# Relationship history" > "$SCRIPT_DIR/memory/relationship.md"
[[ ! -f "$SCRIPT_DIR/memory/moments.md" ]] && echo "# Important moments" > "$SCRIPT_DIR/memory/moments.md"

success "Memory files ready."

CONFIG="$SCRIPT_DIR/config.yaml"
sed -i "s|model_path:.*|model_path: \"models/$MODEL_FILENAME\"|" "$CONFIG" || true
success "Config updated."

echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║         INSTALLATION COMPLETE        ║${NC}"
echo -e "${BOLD}  ╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  RAM       : ${GREEN}${RAM_GB}GB${NC}"
echo -e "  Model     : ${GREEN}$MODEL_LABEL${NC}"
echo -e "  llama.cpp : ${GREEN}$LLAMA_BIN${NC}"
echo ""
echo -e "  Edit ${YELLOW}config.yaml${NC} — change the default password!"
echo -e "  Then run: ${CYAN}bash run.sh${NC}"
echo ""
LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
echo -e "  http://${LOCAL_IP}:7777"
echo ""
