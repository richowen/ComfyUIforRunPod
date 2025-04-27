# ComfyUI RunPod Package System

A streamlined system for packaging and deploying ComfyUI workflows to RunPod servers. This tool identifies all dependencies in a workflow (models and custom nodes), creates a self-contained package, and provides easy installation on RunPod servers.

## Features

- 📦 **Interactive Model Discovery**: Guided process for identifying and locating models used in workflows
- 🔍 **Smart Dependency Detection**: Automatically detects custom nodes and their requirements
- 🚀 **Efficient Model Downloads**: Robust downloading with Civitai API integration and parallel processing
- 🛠️ **One-Command Installation**: Simple deployment to RunPod servers
- ✅ **Installation Verification**: Built-in testing to ensure proper setup

## Quick Start

```bash
# Create a package from a workflow
python example.py create path/to/your_workflow.json --comfyui-dir /path/to/comfyui

# Analyze a workflow without creating a package
python example.py analyze path/to/your_workflow.json

# Test your ComfyUI installation
python example.py test --comfyui-dir /path/to/comfyui
```

## Components

### 1. Interactive Package Creator
The `scripts/interactive_package_creator.py` module provides a guided workflow for creating packages:

- Interactively identifies and classifies models used in workflows
- Guides users through locating model files on their system
- Handles large models with options for direct inclusion or download URLs
- Collects Python package requirements from custom nodes
- Generates a standardized package structure with config.json

### 2. Workflow Parsers
Two workflow parser implementations are provided:

- `scripts/simplified_workflow_parser.py`: Extracts model references without path resolution
- `scripts/workflow_parser.py`: Full-featured parser with enhanced model type detection and path resolution

### 3. Model Downloader
The `scripts/model_downloader.py` script provides robust model downloading:

- Reliable downloads with retry mechanism
- Civitai API key integration
- Progress reporting with ETA
- Parallel download capability
- Hash verification for integrity

### 4. Installation Script
The `install_package.sh` script simplifies deployment to RunPod:

- One-command installation
- Proper handling of requirements.txt
- Efficient model downloading
- GPU optimization settings

### 5. Main Interface
The `example.py` script provides a unified command-line interface to all functionality:

- Package creation
- Workflow analysis
- Installation testing

## Detailed Usage

### Creating a Package

```bash
python example.py create path/to/your_workflow.json --comfyui-dir /path/to/comfyui
```

#### Options:
- `--comfyui-dir PATH`: Path to local ComfyUI installation
- `--output NAME`: Custom name for the output package
- `--output-dir DIR`: Directory to save the package
- `--civitai-key KEY`: Civitai API key for model downloading
- `--size-threshold GB`: Size threshold for large models (default: 2GB)
- `--no-manager`: Don't include ComfyUI-Manager in the package
- `--verbose`: Enable detailed logging

### Interactive Model Discovery

When creating a package, you'll be guided through the model discovery process:

1. The system will extract model references from your workflow
2. For each model, you'll be prompted to:
   - Select the model type (checkpoint, LoRA, VAE, etc.)
   - Locate the model on your system
3. You'll be given options for large models:
   - Include directly in the package
   - Provide a download URL (recommended for large files)
   - Skip the model

### Installing a Package on RunPod

1. Upload the package ZIP file to a web-accessible location
2. On your RunPod server, run:

```bash
bash -c "$(curl -sSL https://raw.githubusercontent.com/yourusername/comfyui/main/install_package.sh)" -- --package URL_TO_YOUR_PACKAGE
```

Replace `URL_TO_YOUR_PACKAGE` with the URL to your uploaded package ZIP file.

#### Options:
- `--package URL`: URL to the package ZIP file (required)
- `--dir PATH`: ComfyUI installation directory (default: /workspace/ComfyUI)

## Package Structure

The created packages follow a standardized structure:

```
package-name/
├── config.json                 # Package configuration and metadata
├── civitai_config.json         # Optional Civitai API configuration
├── custom_nodes/               # Custom node packages
│   ├── NodePackage1/           # Individual custom node packages
│   └── NodePackage2/
├── models/                     # Model files organized by type
│   ├── checkpoints/
│   ├── loras/
│   ├── vae/
│   └── ...
├── workflows/                  # Workflow JSON files
│   └── workflow.json
├── download_models.py          # Script for downloading external models
└── README.md                   # Package documentation
```

## Development

### Extending the System

To add support for new model types:

1. Edit `scripts/interactive_package_creator.py`
2. Add new model types to the `MODEL_TYPES` list
3. Update the model type detection logic in the workflow parser

### Requirements

- Python 3.8 or higher
- `requests` library (auto-installed if missing)
- `pyyaml` library (for parsing extra_model_paths.yaml)

The installation script requires:
- wget, curl, unzip, jq (auto-installed if missing on Ubuntu-based systems)
- Python 3 and pip

## Example Workflow

1. Create a workflow in ComfyUI using custom nodes and models
2. Save the workflow as JSON
3. Run `python example.py create my_workflow.json`
4. Follow the interactive prompts to identify models
5. Upload the resulting ZIP file to a web hosting service
6. Run the installer on your RunPod server
7. Access ComfyUI with your workflow ready to use

## For More Information

See [SUMMARY.md](SUMMARY.md) for a detailed system overview, architecture diagrams, and additional technical details.
