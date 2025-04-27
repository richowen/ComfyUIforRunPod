#!/bin/bash
# ComfyUI RunPod Package Installer
# A streamlined script for installing ComfyUI packages on RunPod servers

set -e
trap 'echo "An error occurred. Exiting..."; exit 1' ERR

# ANSI colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Set proper encoding
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

# Default values
PACKAGE_URL=""
COMFYUI_DIR="/workspace/ComfyUI"
TEMP_DIR="/tmp/comfyui-package"

# Usage information
usage() {
    echo "ComfyUI RunPod Package Installer"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -p, --package URL    URL to the package ZIP file (required)"
    echo "  -d, --dir PATH       ComfyUI installation directory (default: /workspace/ComfyUI)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --package https://example.com/my-package.zip"
}

# Parse command line arguments
while [ "$#" -gt 0 ]; do
    case "$1" in
        -p|--package)
            PACKAGE_URL="$2"
            shift 2
            ;;
        -d|--dir)
            COMFYUI_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Check if package URL is provided
if [ -z "$PACKAGE_URL" ]; then
    echo -e "${RED}Package URL is required${NC}"
    usage
    exit 1
fi

# Install ComfyUI if not already installed
install_comfyui() {
    if [ ! -d "$COMFYUI_DIR" ]; then
        echo -e "${BLUE}ComfyUI not found at $COMFYUI_DIR${NC}"
        echo -e "${BLUE}Installing ComfyUI...${NC}"
        
        # Create parent directory if it doesn't exist
        mkdir -p "$(dirname "$COMFYUI_DIR")"
        
        # Clone ComfyUI repository
        git clone https://github.com/comfyanonymous/ComfyUI "$COMFYUI_DIR"
        
        # Install basic requirements
        cd "$COMFYUI_DIR"
        pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121
        pip install -r requirements.txt
        
        echo -e "${GREEN}ComfyUI has been successfully installed at $COMFYUI_DIR${NC}"
    else
        echo -e "${GREEN}ComfyUI already installed at $COMFYUI_DIR${NC}"
    fi
}

# Check dependencies
check_dependencies() {
    echo -e "${BLUE}Checking dependencies...${NC}"
    local missing_deps=()
    
    # Check for basic CLI tools
    for cmd in wget curl unzip jq python3 pip3 git; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo -e "${YELLOW}Installing missing dependencies: ${missing_deps[*]}${NC}"
        apt-get update
        apt-get install -y "${missing_deps[@]}"
    fi
    
    echo -e "${GREEN}All dependencies satisfied.${NC}"
}

# Create necessary directories
create_directories() {
    echo -e "${BLUE}Setting up directories...${NC}"
    
    # Clean up existing temp directory if it exists
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
    
    mkdir -p "$TEMP_DIR"
    
    # Ensure required ComfyUI directories exist
    mkdir -p "$COMFYUI_DIR/custom_nodes"
    mkdir -p "$COMFYUI_DIR/models/checkpoints"
    mkdir -p "$COMFYUI_DIR/models/loras"
    mkdir -p "$COMFYUI_DIR/models/vae"
    mkdir -p "$COMFYUI_DIR/models/controlnet"
    mkdir -p "$COMFYUI_DIR/models/embeddings"
    mkdir -p "$COMFYUI_DIR/models/insightface"
    mkdir -p "$COMFYUI_DIR/models/ultralytics"
    mkdir -p "$COMFYUI_DIR/models/clip"
    mkdir -p "$COMFYUI_DIR/models/clip_vision"
    mkdir -p "$COMFYUI_DIR/models/upscale_models"
    mkdir -p "$COMFYUI_DIR/models/facerestore_models"
    mkdir -p "$COMFYUI_DIR/models/hypernetworks"
    mkdir -p "$COMFYUI_DIR/models/sams"
    
    # Create user workflows directory
    mkdir -p "$COMFYUI_DIR/user/default/workflows"
}

# Download and extract package
download_package() {
    echo -e "${BLUE}Downloading package from $PACKAGE_URL...${NC}"
    
    # Check if URL is valid
    if ! curl --output /dev/null --silent --head --fail "$PACKAGE_URL"; then
        echo -e "${RED}Invalid package URL: $PACKAGE_URL${NC}"
        exit 1
    fi
    
    local package_file="$TEMP_DIR/package.zip"
    wget -O "$package_file" "$PACKAGE_URL"
    
    echo -e "${BLUE}Extracting package...${NC}"
    unzip -q "$package_file" -d "$TEMP_DIR/extracted"
    
    echo -e "${GREEN}Package downloaded and extracted.${NC}"
}

# Install custom nodes and their requirements
install_custom_nodes() {
    if [ ! -d "$TEMP_DIR/extracted/custom_nodes" ]; then
        echo -e "${YELLOW}No custom nodes found in package.${NC}"
        return
    fi
    
    echo -e "${BLUE}Installing custom nodes...${NC}"
    
    # Check if config.json has installation order
    local install_order=()
    if [ -f "$TEMP_DIR/extracted/config.json" ]; then
        if jq -e '.installation_order' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
            mapfile -t install_order < <(jq -r '.installation_order[]' "$TEMP_DIR/extracted/config.json")
        fi
    fi
    
    # If installation order is specified, use it
    if [ ${#install_order[@]} -gt 0 ]; then
        echo -e "${BLUE}Installing custom nodes in specified order...${NC}"
        for node_path in "${install_order[@]}"; do
            if [[ "$node_path" == custom_nodes/* ]]; then
                local node_name=$(basename "$node_path")
                local src_path="$TEMP_DIR/extracted/$node_path"
                local dest_path="$COMFYUI_DIR/custom_nodes/$node_name"
                
                echo -e "${BLUE}Installing $node_name...${NC}"
                
                # Copy the node files
                if [ -d "$src_path" ]; then
                    cp -r "$src_path" "$dest_path"
                    
                    # Install requirements if any
                    if [ -f "$dest_path/requirements.txt" ]; then
                        echo -e "${BLUE}Installing requirements for $node_name...${NC}"
                        pip install -r "$dest_path/requirements.txt"
                    fi
                fi
            fi
        done
    else
        # No installation order specified, just copy all nodes
        echo -e "${BLUE}Installing all custom nodes...${NC}"
        for node_dir in "$TEMP_DIR/extracted/custom_nodes"/*; do
            if [ -d "$node_dir" ]; then
                local node_name=$(basename "$node_dir")
                local dest_path="$COMFYUI_DIR/custom_nodes/$node_name"
                
                echo -e "${BLUE}Installing $node_name...${NC}"
                cp -r "$node_dir" "$dest_path"
                
                # Install requirements if any
                if [ -f "$dest_path/requirements.txt" ]; then
                    echo -e "${BLUE}Installing requirements for $node_name...${NC}"
                    pip install -r "$dest_path/requirements.txt"
                fi
            fi
        done
    fi
    
    # Install any package-level dependencies
    if [ -f "$TEMP_DIR/extracted/config.json" ]; then
        if jq -e '.dependencies' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
            echo -e "${BLUE}Installing package dependencies...${NC}"
            readarray -t deps < <(jq -r '.dependencies[]' "$TEMP_DIR/extracted/config.json")
            for dep in "${deps[@]}"; do
                echo -e "${BLUE}Installing dependency: $dep${NC}"
                pip install "$dep"
            done
        fi
    fi
    
    echo -e "${GREEN}Custom nodes installed.${NC}"
}

# Copy workflows and models
copy_assets() {
    echo -e "${BLUE}Copying workflows and models...${NC}"
    
    # Copy workflows
    if [ -d "$TEMP_DIR/extracted/workflows" ]; then
        for workflow in "$TEMP_DIR/extracted/workflows"/*; do
            if [ -f "$workflow" ]; then
                cp "$workflow" "$COMFYUI_DIR/user/default/workflows/"
            fi
        done
    fi
    
    # Copy models
    if [ -d "$TEMP_DIR/extracted/models" ]; then
        find "$TEMP_DIR/extracted/models" -type f -name "*.safetensors" -o -name "*.ckpt" -o -name "*.pt" -o -name "*.bin" -o -name "*.pth" -o -name "*.onnx" | while read model_file; do
            # Determine model type from directory structure
            local rel_path=$(realpath --relative-to="$TEMP_DIR/extracted/models" "$(dirname "$model_file")")
            local model_type="$rel_path"
            
            # If it's a nested path, use the top level directory as the model type
            if [[ "$model_type" == */* ]]; then
                model_type=$(echo "$model_type" | cut -d'/' -f1)
            fi
            
            # Create target directory
            local target_dir="$COMFYUI_DIR/models/$model_type"
            mkdir -p "$target_dir"
            
            # Copy the model
            cp "$model_file" "$target_dir/"
        done
    fi
    
    echo -e "${GREEN}Workflows and models copied.${NC}"
}

# Download external models
download_models() {
    # Check for Civitai API key
    if [ -f "$TEMP_DIR/extracted/civitai_config.json" ]; then
        cp "$TEMP_DIR/extracted/civitai_config.json" "$COMFYUI_DIR/"
        echo -e "${BLUE}Civitai API configuration copied.${NC}"
    fi
    
    # Check if we have a download script and external models
    if [ -f "$TEMP_DIR/extracted/download_models.py" ]; then
        # Copy the download script
        cp "$TEMP_DIR/extracted/download_models.py" "$COMFYUI_DIR/"
        
        # Copy config.json for the downloader
        if [ -f "$TEMP_DIR/extracted/config.json" ]; then
            cp "$TEMP_DIR/extracted/config.json" "$COMFYUI_DIR/"
        fi
        
        echo -e "${BLUE}Processing external models...${NC}"
        cd "$COMFYUI_DIR"
        
        # Install requests if not already installed
        pip install requests
        
        # Run the downloader
        python download_models.py --comfyui-dir "$COMFYUI_DIR"
        
        echo -e "${GREEN}External models processed.${NC}"
    elif [ -f "$TEMP_DIR/extracted/config.json" ] && jq -e '.external_models' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
        # We have external models but no downloader script
        echo -e "${YELLOW}External models found but no downloader script.${NC}"
        echo -e "${YELLOW}You may need to download models manually.${NC}"
    fi
}

# Apply GPU settings from config
apply_gpu_settings() {
    if [ -f "$TEMP_DIR/extracted/config.json" ]; then
        if jq -e '.gpu_settings' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
            echo -e "${BLUE}Applying GPU settings from config.json...${NC}"
            
            # Check for VRAM optimization
            if jq -e '.gpu_settings.vram_optimize' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
                local vram_optimize=$(jq -r '.gpu_settings.vram_optimize' "$TEMP_DIR/extracted/config.json")
                if [ "$vram_optimize" = "true" ]; then
                    echo -e "${BLUE}Enabling VRAM optimization...${NC}"
                    export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
                fi
            fi
            
            # Check for xformers setting
            if jq -e '.gpu_settings.xformers' "$TEMP_DIR/extracted/config.json" >/dev/null 2>&1; then
                local xformers=$(jq -r '.gpu_settings.xformers' "$TEMP_DIR/extracted/config.json")
                if [ "$xformers" = "true" ]; then
                    echo -e "${BLUE}Installing xformers...${NC}"
                    pip install xformers
                fi
            fi
            
            echo -e "${GREEN}GPU settings applied.${NC}"
        fi
    fi
}

# Main installation process
main() {
    echo -e "${BLUE}====================================${NC}"
    echo -e "${BLUE}  ComfyUI RunPod Package Installer  ${NC}"
    echo -e "${BLUE}====================================${NC}"
    
    # Check dependencies
    check_dependencies
    
    # Install ComfyUI if needed
    install_comfyui
    
    # Create necessary directories
    create_directories
    
    # Download and extract package
    download_package
    
    # Install custom nodes
    install_custom_nodes
    
    # Copy workflows and models
    copy_assets
    
    # Download external models
    download_models
    
    # Apply GPU settings
    apply_gpu_settings
    
    # Clean up
    echo -e "${BLUE}Cleaning up...${NC}"
    rm -rf "$TEMP_DIR"
    
    echo -e "${GREEN}====================================${NC}"
    echo -e "${GREEN}  Installation Complete!            ${NC}"
    echo -e "${GREEN}====================================${NC}"
    echo -e "${GREEN}ComfyUI package has been installed to: $COMFYUI_DIR${NC}"
    echo -e "${GREEN}To start ComfyUI, run:${NC}"
    echo -e "${GREEN}  cd $COMFYUI_DIR && python main.py --listen 0.0.0.0 --port 3000${NC}"
}

# Run the main function
main
