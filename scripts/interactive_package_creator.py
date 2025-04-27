#!/usr/bin/env python3
"""
Interactive ComfyUI Package Creator for RunPod
Creates packages with user-guided model discovery and selection.
"""

import os
import sys
import json
import shutil
import zipfile
import hashlib
import time
import glob
import fnmatch
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional, Union

# Add local module search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import local modules
try:
    from simplified_workflow_parser import WorkflowParser
except ImportError:
    print("Error: simplified_workflow_parser.py not found in the same directory.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("PackageCreator")

# Model types and their descriptions
MODEL_TYPES = [
    ("checkpoints", "Stable Diffusion checkpoint"),
    ("loras", "LoRA model"),
    ("vae", "VAE model"),
    ("controlnet", "ControlNet model"),
    ("embeddings", "Textual Inversion embedding"),
    ("upscale_models", "Upscaler model"),
    ("facerestore_models", "Face restoration model"),
    ("insightface", "InsightFace model"),
    ("clip", "CLIP model"),
    ("clip_vision", "CLIP Vision model"),
    ("hypernetworks", "Hypernetwork"),
    ("ultralytics", "Ultralytics/YOLO model"),
    ("sams", "Segment Anything model")
]

class RequirementsCollector:
    """Collects and processes requirements.txt files from custom nodes"""
    
    def __init__(self):
        self.requirements = set()
        self.processed_files = set()
        
    def process_requirements_file(self, req_file: str) -> None:
        """Process a requirements.txt file and add entries to the requirements set"""
        if not os.path.exists(req_file) or req_file in self.processed_files:
            return
            
        self.processed_files.add(req_file)
        
        try:
            with open(req_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                        
                    # Handle line continuations
                    while line.endswith('\\'):
                        line = line[:-1]
                        next_line = next(f, '').strip()
                        line += next_line
                    
                    # Clean up dependency specification
                    # Remove comments
                    if '#' in line:
                        line = line.split('#')[0].strip()
                        
                    # Skip if empty after cleaning
                    if not line:
                        continue
                        
                    # Add to our requirements set
                    self.requirements.add(line)
        except Exception as e:
            logger.warning(f"Error processing requirements file {req_file}: {e}")
    
    def process_node_directory(self, node_dir: str) -> None:
        """Process all requirements.txt files in a node directory"""
        # First check for requirements.txt in the root directory
        root_req = os.path.join(node_dir, "requirements.txt")
        if os.path.exists(root_req):
            self.process_requirements_file(root_req)
            
        # Then check for any subdirectories
        try:
            for root, dirs, files in os.walk(node_dir):
                for file in files:
                    if file.lower() == "requirements.txt":
                        req_path = os.path.join(root, file)
                        self.process_requirements_file(req_path)
        except Exception as e:
            logger.warning(f"Error scanning directory {node_dir} for requirements.txt: {e}")
    
    def get_requirements_list(self) -> List[str]:
        """Get the list of collected requirements"""
        return sorted(list(self.requirements))
    
    def has_requirements(self) -> bool:
        """Check if any requirements were collected"""
        return len(self.requirements) > 0


class InteractivePackageCreator:
    """Creates ComfyUI packages with user-guided model discovery"""
    
    def __init__(self, comfyui_path: str):
        """
        Initialize the package creator
        
        Args:
            comfyui_path: Path to ComfyUI installation
        """
        self.comfyui_path = os.path.abspath(comfyui_path)
        self.workflow_parser = WorkflowParser(comfyui_path)
        self.model_search_paths = self._get_model_search_paths()
        
    def _get_model_search_paths(self) -> Dict[str, List[str]]:
        """Get base paths to search for models"""
        # Start with standard ComfyUI model paths
        search_paths = {}
        
        for model_type, _ in MODEL_TYPES:
            search_paths[model_type] = [os.path.join(self.comfyui_path, "models", model_type)]
        
        # Try to load extra_model_paths.yaml
        yaml_files = [
            os.path.join(self.comfyui_path, "extra_model_paths.yaml"),
            os.path.join(os.path.dirname(self.comfyui_path), "extra_model_paths.yaml")
        ]
        
        for yaml_file in yaml_files:
            if os.path.exists(yaml_file):
                try:
                    import yaml
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    
                    if data:
                        print(f"Loading paths from {yaml_file}")
                        for ui_name, ui_config in data.items():
                            if 'base_path' in ui_config:
                                base_path = ui_config['base_path']
                                if base_path.startswith('~'):
                                    base_path = os.path.expanduser(base_path)
                                
                                # Add paths for each model type
                                for k, v in ui_config.items():
                                    if k.lower() in search_paths and k != 'base_path' and k != 'is_default':
                                        if isinstance(v, str):
                                            if '\n' in v:  # Multi-line string
                                                paths = [p.strip() for p in v.split('\n') if p.strip()]
                                            else:
                                                paths = [v.strip()]
                                                
                                            for p in paths:
                                                if os.path.isabs(p):
                                                    full_path = p
                                                else:
                                                    full_path = os.path.join(base_path, p)
                                                search_paths[k.lower()].append(full_path)
                                                print(f"Added search path for {k}: {full_path}")
                except Exception as e:
                    print(f"Error loading {yaml_file}: {e}")
        
        return search_paths
    
    def create_package(self, 
                       workflow_path: str, 
                       output_name: Optional[str] = None,
                       output_dir: Optional[str] = None,
                       civitai_api_key: Optional[str] = None,
                       size_threshold_gb: float = 2.0,
                       include_manager: bool = True) -> str:
        """
        Create a package from a workflow file with interactive model discovery
        
        Args:
            workflow_path: Path to the workflow JSON file
            output_name: Name for the output package (defaults to workflow filename)
            output_dir: Directory to save the package (defaults to current directory)
            civitai_api_key: Civitai API key for model downloads
            size_threshold_gb: Size threshold in GB for large models
            include_manager: Whether to include ComfyUI Manager by default
            
        Returns:
            Path to the created ZIP file
        """
        # Validate workflow path
        if not os.path.exists(workflow_path):
            logger.error(f"Workflow file not found: {workflow_path}")
            raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
        
        # Set default output name if not provided
        if not output_name:
            output_name = os.path.splitext(os.path.basename(workflow_path))[0] + "-package"
        
        # Set default output directory if not provided
        if not output_dir:
            output_dir = os.getcwd()
            
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a temporary directory for package assembly
        temp_dir = os.path.join(output_dir, output_name)
        if os.path.exists(temp_dir):
            # Check if civitai_config.json exists and save it if it does
            civitai_config_path = os.path.join(temp_dir, "civitai_config.json")
            civitai_config_content = None
            if os.path.exists(civitai_config_path):
                logger.info("Preserving existing civitai_config.json...")
                try:
                    with open(civitai_config_path, 'r') as f:
                        civitai_config_content = f.read()
                except Exception as e:
                    logger.warning(f"Could not read civitai_config.json: {e}")
            
            if input(f"Package directory '{temp_dir}' already exists. Overwrite? (y/n): ").lower() != 'y':
                logger.info("Operation cancelled.")
                return ""
            
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Failed to remove existing directory: {e}")
                return ""
            
            # Recreate directory and restore civitai_config.json if it existed
            os.makedirs(temp_dir, exist_ok=True)
            if civitai_config_content:
                with open(civitai_config_path, 'w') as f:
                    f.write(civitai_config_content)
        else:
            os.makedirs(temp_dir, exist_ok=True)
        
        # Create directory structure
        logger.info(f"Creating package structure in {temp_dir}")
        os.makedirs(os.path.join(temp_dir, "workflows"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "custom_nodes"), exist_ok=True)
        
        # Create model directories
        for model_type, _ in MODEL_TYPES:
            os.makedirs(os.path.join(temp_dir, "models", model_type), exist_ok=True)
            
        # Create Civitai API key config if provided
        if civitai_api_key:
            civitai_config = {
                "api_key": civitai_api_key
            }
            with open(os.path.join(temp_dir, "civitai_config.json"), 'w') as f:
                json.dump(civitai_config, f, indent=2)
            logger.info("Added Civitai API key configuration")
        
        # Copy workflow file
        logger.info("Copying workflow file...")
        shutil.copy2(workflow_path, os.path.join(temp_dir, "workflows", os.path.basename(workflow_path)))
        
        # Parse workflow to find dependencies
        logger.info(f"Analyzing workflow: {workflow_path}")
        dependencies = self.workflow_parser.parse_workflow(workflow_path)
        
        # Process custom nodes
        custom_nodes_processed = []
        if dependencies['custom_nodes']:
            logger.info(f"Processing {len(dependencies['custom_nodes'])} custom node packages...")
            
            # Add ComfyUI-Manager if requested
            if include_manager:
                manager_path = os.path.join(self.comfyui_path, "custom_nodes", "ComfyUI-Manager")
                if os.path.exists(manager_path):
                    # Check if it's already in dependencies
                    manager_found = False
                    for name, path in dependencies['custom_nodes']:
                        if name.lower() == "comfyui-manager":
                            manager_found = True
                            break
                    
                    if not manager_found:
                        dependencies['custom_nodes'].append(("ComfyUI-Manager", manager_path))
                        logger.info("Added ComfyUI-Manager to package")
                else:
                    logger.warning("ComfyUI-Manager not found in ComfyUI installation")
            
            # Collect requirements from all custom nodes
            requirements_collector = RequirementsCollector()
            
            # Copy custom nodes and collect their requirements
            for package_name, package_path in dependencies['custom_nodes']:
                try:
                    target_path = os.path.join(temp_dir, "custom_nodes", package_name)
                    logger.info(f"  - {package_name}")
                    
                    # Copy the node package
                    self._copy_tree_filtered(package_path, target_path)
                    
                    # Process requirements
                    requirements_collector.process_node_directory(package_path)
                    
                    # Add to processed list for config
                    custom_nodes_processed.append(f"custom_nodes/{package_name}")
                except Exception as e:
                    logger.error(f"    Error copying {package_name}: {e}")
        
        # Interactive model discovery and selection
        models_to_process = self._interactive_model_discovery(dependencies['model_references'])
        
        # Process models
        external_models = []
        models_processed = {}
        
        for model_type, model_list in models_to_process.items():
            if not model_list:
                continue
                
            models_processed[model_type] = []
            
            for model_name, model_path in model_list:
                if not model_path:
                    logger.warning(f"  - Warning: No path provided for {model_name}")
                    continue
                
                if not os.path.exists(model_path):
                    logger.warning(f"  - Warning: Model file not found: {model_path}")
                    continue
                
                # Check model size
                model_size = os.path.getsize(model_path)
                size_mb = model_size / (1024 * 1024)
                size_threshold = size_threshold_gb * 1024 * 1024 * 1024
                
                # Determine target directory based on model type
                dest_dir = os.path.join(temp_dir, "models", model_type)
                
                # Handle subdirectories in model path
                rel_path = os.path.basename(model_name)
                if '/' in model_name or '\\' in model_name:
                    rel_dir = os.path.dirname(model_name)
                    rel_path = model_name
                    dest_dir = os.path.join(dest_dir, rel_dir)
                    os.makedirs(dest_dir, exist_ok=True)
                
                dest_path = os.path.join(dest_dir, os.path.basename(rel_path))
                
                # Handle large model prompting
                if model_size > size_threshold:
                    size_gb = model_size / (1024 * 1024 * 1024)
                    logger.info(f"Large model detected: {model_name} ({size_gb:.2f} GB)")
                    print(f"\nModel '{model_name}' is large ({size_gb:.2f} GB)")
                    print("Options:")
                    print("1. Include in package (not recommended for large files)")
                    print("2. Add download URL to config.json (recommended)")
                    print("3. Skip this model")
                    
                    choice = input("Enter choice (1-3): ")
                    
                    if choice == "1":
                        logger.info(f"  - Copying large model {model_name}...")
                        shutil.copy2(model_path, dest_path)
                        models_processed[model_type].append(model_name)
                    elif choice == "2":
                        # Get model URL
                        print("\nPlease provide a download URL for this model.")
                        print("Suggested sources: Civitai, Hugging Face, or other model repositories")
                        model_url = input("URL: ")
                        
                        if model_url:
                            # Calculate file hash for verification
                            logger.info("  - Calculating hash for verification...")
                            file_hash = self._calculate_file_hash(model_path)
                            
                            # Add to external models list
                            external_models.append({
                                "name": os.path.basename(model_name),
                                "type": model_type,
                                "path": rel_path if '/' in model_name or '\\' in model_name else None,
                                "url": model_url,
                                "hash": file_hash,
                                "size": model_size
                            })
                            logger.info(f"  - Added {model_name} as external download")
                        else:
                            logger.info("  - No URL provided, skipping model")
                    else:
                        logger.info(f"  - Skipping model {model_name}")
                else:
                    # Regular-sized model, include it directly
                    logger.info(f"  - Copying model {model_name} ({size_mb:.2f} MB)...")
                    shutil.copy2(model_path, dest_path)
                    models_processed[model_type].append(model_name)
        
        # Create config.json
        logger.info("Creating config.json...")
        config_path = os.path.join(temp_dir, "config.json")
        
        # Package metadata
        package_config = {
            "name": output_name,
            "description": f"Package created from {os.path.basename(workflow_path)}",
            "version": "1.0.0",
            "author": "ComfyUI Package Creator",
        }
        
        # Add installation order for custom nodes
        if custom_nodes_processed:
            package_config["installation_order"] = custom_nodes_processed
        
        # Add external models if any
        if external_models:
            package_config["external_models"] = external_models
        
        # Add requirements if any were collected
        if 'requirements_collector' in locals() and requirements_collector.has_requirements():
            package_config["dependencies"] = requirements_collector.get_requirements_list()
        
        # Add processed models for reference
        package_config["included_models"] = models_processed
        
        # Add placeholder settings
        package_config["gpu_settings"] = {
            "vram_optimize": True,
            "precision": "fp16",
            "xformers": True
        }
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(package_config, f, indent=2)
        
        # Copy model downloader script if we have external models
        if external_models:
            logger.info("Adding model download script...")
            source_download_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_downloader.py")
            if os.path.exists(source_download_script):
                download_script_path = os.path.join(temp_dir, "download_models.py")
                shutil.copy2(source_download_script, download_script_path)
                logger.info("  - Added model_downloader.py to package")
            else:
                logger.warning("Warning: model_downloader.py not found in current directory. Model downloading may not work.")
        
        # Create README.md with package info
        readme_path = os.path.join(temp_dir, "README.md")
        with open(readme_path, 'w') as f:
            f.write(f"# {output_name}\n\n")
            f.write(f"Package created from {os.path.basename(workflow_path)}\n\n")
            
            # Add custom nodes info
            if custom_nodes_processed:
                f.write("## Custom Nodes\n\n")
                for node_path in custom_nodes_processed:
                    node_name = os.path.basename(node_path)
                    f.write(f"- {node_name}\n")
                f.write("\n")
            
            # Add model info
            if models_processed:
                f.write("## Included Models\n\n")
                for model_type, models in models_processed.items():
                    if models:
                        f.write(f"### {model_type}\n\n")
                        for model in models:
                            f.write(f"- {model}\n")
                        f.write("\n")
            
            # Add external models info
            if external_models:
                f.write("## External Models (Downloaded During Installation)\n\n")
                for model in external_models:
                    f.write(f"- {model['name']} ({model['type']})\n")
                f.write("\n")
                
                f.write("To download these models, run:\n")
                f.write("```\npython download_models.py\n```\n\n")
            
            # Add usage instructions
            f.write("## Usage\n\n")
            f.write("1. Install the package on your RunPod server\n")
            f.write("2. Run the installation script\n")
            f.write("3. The workflow will be available in ComfyUI\n")
        
        # Create ZIP file
        logger.info("Creating ZIP archive...")
        zip_path = os.path.join(output_dir, f"{output_name}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        logger.info(f"Package created successfully in {zip_path}")
        
        # Ask if we should clean up the temporary directory
        if input("Clean up temporary directory? (y/n): ").lower() == 'y':
            logger.info("Cleaning up temporary directory...")
            shutil.rmtree(temp_dir)
        
        return zip_path
    
    def _interactive_model_discovery(self, model_references: List[str]) -> Dict[str, List[Tuple[str, str]]]:
        """
        Interactive model discovery and classification
        
        Args:
            model_references: List of model references from the workflow
            
        Returns:
            Dictionary mapping model types to lists of (model_name, model_path) tuples
        """
        print("\n======= MODEL DISCOVERY =======")
        print(f"Found {len(model_references)} model references in the workflow")
        
        models_by_type = {}
        for model_type, _ in MODEL_TYPES:
            models_by_type[model_type] = []
            
        if not model_references:
            print("No models found in the workflow")
            return models_by_type
        
        print("\nWe'll now go through each model to classify and locate it.")
        print("For each model, you'll select the type and provide the location.\n")
        
        for model_ref in model_references:
            print(f"\n--- Processing: {model_ref} ---")
            
            # Prompt for model type
            model_type = self._prompt_for_model_type(model_ref)
            
            # Prompt for model path
            model_path = self._interactive_model_search(model_ref, model_type)
            
            if model_path:
                models_by_type[model_type].append((model_ref, model_path))
                print(f"Added {model_ref} as a {model_type} model")
            else:
                print(f"Skipping {model_ref}")
                
        # Summarize results
        print("\n======= MODEL DISCOVERY SUMMARY =======")
        for model_type, models in models_by_type.items():
            if models:
                print(f"{model_type}: {len(models)} models")
                for model_name, _ in models:
                    print(f"  - {model_name}")
        
        return models_by_type
    
    def _prompt_for_model_type(self, model_ref: str) -> str:
        """
        Prompt user to select the model type
        
        Args:
            model_ref: Model reference from the workflow
            
        Returns:
            Selected model type
        """
        # Try to guess the model type from the file extension or name
        extension = os.path.splitext(model_ref)[1].lower()
        suggested_type = None
        
        if extension in ('.pt', '.pth'):
            if 'upscale' in model_ref.lower() or 'esrgan' in model_ref.lower():
                suggested_type = "upscale_models"
            elif 'face' in model_ref.lower() or 'gfpgan' in model_ref.lower():
                suggested_type = "facerestore_models"
        elif extension == '.onnx':
            suggested_type = "insightface"
        elif extension in ('.safetensors', '.ckpt'):
            if 'lora' in model_ref.lower():
                suggested_type = "loras"
            elif 'vae' in model_ref.lower():
                suggested_type = "vae"
            elif 'embedding' in model_ref.lower():
                suggested_type = "embeddings"
            elif 'control' in model_ref.lower():
                suggested_type = "controlnet"
            else:
                suggested_type = "checkpoints"
        
        # Present options to the user
        print("What type of model is this?")
        for i, (model_type, description) in enumerate(MODEL_TYPES, 1):
            marker = "→" if model_type == suggested_type else " "
            print(f"{marker} {i}. {description} ({model_type})")
            
        # Get user selection
        while True:
            choice = input(f"\nSelect model type (1-{len(MODEL_TYPES)}): ")
            try:
                index = int(choice) - 1
                if 0 <= index < len(MODEL_TYPES):
                    return MODEL_TYPES[index][0]
                else:
                    print(f"Please enter a number between 1 and {len(MODEL_TYPES)}")
            except ValueError:
                print("Please enter a valid number")
    
    def _interactive_model_search(self, model_ref: str, model_type: str) -> Optional[str]:
        """
        Interactive model search and selection
        
        Args:
            model_ref: Model reference from the workflow
            model_type: Type of the model
            
        Returns:
            Path to the selected model or None if skipped
        """
        # First, try to find models automatically in the search paths
        print(f"Searching for '{model_ref}' in common locations...")
        
        # Normalize model name and get filename
        model_name = os.path.basename(model_ref)
        model_name_lower = model_name.lower()
        model_candidates = []
        
        # Search in the default paths for this model type
        for base_path in self.model_search_paths.get(model_type, []):
            if os.path.exists(base_path):
                # Try the direct path first
                full_path = os.path.join(base_path, model_ref)
                if os.path.exists(full_path):
                    model_candidates.append((1, full_path))
                    
                # Try just the filename
                filename_path = os.path.join(base_path, model_name)
                if os.path.exists(filename_path) and filename_path != full_path:
                    model_candidates.append((2, filename_path))
                
                # Look in subdirectories
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file.lower() == model_name_lower:
                            path = os.path.join(root, file)
                            if path not in [p for _, p in model_candidates]:
                                model_candidates.append((3, path))
                                
        # If we found matches, present them to the user
        if model_candidates:
            print(f"Found {len(model_candidates)} potential matches:")
            model_candidates.sort()  # Sort by match confidence
            
            for i, (_, path) in enumerate(model_candidates, 1):
                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"{i}. {path} ({size_mb:.2f} MB)")
                
            print(f"M. Manually enter path")
            print(f"S. Skip this model")
            
            while True:
                choice = input("Select option: ").strip()
                
                if choice.lower() == 'm':
                    return self._prompt_for_manual_path()
                elif choice.lower() == 's':
                    return None
                    
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(model_candidates):
                        return model_candidates[index][1]
                    else:
                        print(f"Please enter a number between 1 and {len(model_candidates)}")
                except ValueError:
                    print("Please enter a valid option")
        else:
            print("No automatic matches found.")
            
            print("\nOptions:")
            print("1. Enter path manually")
            print("2. Search with glob pattern")
            print("3. Skip this model")
            
            while True:
                choice = input("Select option: ").strip()
                
                if choice == '1':
                    return self._prompt_for_manual_path()
                elif choice == '2':
                    return self._search_with_glob_pattern(model_type)
                elif choice == '3':
                    return None
                else:
                    print("Please enter a valid option (1-3)")
    
    def _prompt_for_manual_path(self) -> Optional[str]:
        """Prompt user to enter a model path manually"""
        while True:
            path = input("Enter full path to model file: ").strip()
            
            if not path:
                return None
            
            # Expand user home directory if needed
            if path.startswith('~'):
                path = os.path.expanduser(path)
            
            # Convert to absolute path
            path = os.path.abspath(path)
            
            if os.path.exists(path) and os.path.isfile(path):
                return path
            else:
                print(f"File not found: {path}")
                retry = input("Try again? (Y/n): ").strip().lower()
                if retry == 'n':
                    return None
    
    def _search_with_glob_pattern(self, model_type: str) -> Optional[str]:
        """Search for models using glob pattern"""
        # Find base directories to search
        base_dirs = self.model_search_paths.get(model_type, [])
        if not base_dirs:
            print("No base directories found for this model type.")
            return self._prompt_for_manual_path()
        
        print("\nEnter a glob pattern to search for the model.")
        print("Examples:")
        print("  *.safetensors")
        print("  *model*.pt")
        print("  **/*lora*.safetensors")
        
        pattern = input("\nPattern: ").strip()
        if not pattern:
            return None
            
        # Search in all base directories
        matches = []
        for base_dir in base_dirs:
            if os.path.exists(base_dir):
                # First try direct glob in base directory
                direct_matches = glob.glob(os.path.join(base_dir, pattern))
                for match in direct_matches:
                    if os.path.isfile(match):
                        size_mb = os.path.getsize(match) / (1024 * 1024)
                        matches.append((match, size_mb))
                        
                # Then try recursive search with **
                if '**' in pattern:
                    recursive_matches = glob.glob(os.path.join(base_dir, pattern), recursive=True)
                    for match in recursive_matches:
                        if os.path.isfile(match) and match not in [m for m, _ in matches]:
                            size_mb = os.path.getsize(match) / (1024 * 1024)
                            matches.append((match, size_mb))
                else:
                    # If no ** in pattern, also try a recursive search
                    recursive_pattern = os.path.join(base_dir, "**", pattern)
                    recursive_matches = glob.glob(recursive_pattern, recursive=True)
                    for match in recursive_matches:
                        if os.path.isfile(match) and match not in [m for m, _ in matches]:
                            size_mb = os.path.getsize(match) / (1024 * 1024)
                            matches.append((match, size_mb))
        
        if not matches:
            print("No matches found.")
            return self._prompt_for_manual_path()
            
        # Display matches
        print(f"\nFound {len(matches)} matches:")
        for i, (path, size_mb) in enumerate(matches, 1):
            print(f"{i}. {path} ({size_mb:.2f} MB)")
            
        # Get user selection
        while True:
            choice = input("\nSelect file (number) or 'M' to enter path manually: ").strip()
            
            if choice.lower() == 'm':
                return self._prompt_for_manual_path()
                
            try:
                index = int(choice) - 1
                if 0 <= index < len(matches):
                    return matches[index][0]
                else:
                    print(f"Please enter a number between 1 and {len(matches)}")
            except ValueError:
                print("Please enter a valid number or 'M'")
    
    def _copy_tree_filtered(self, src: str, dst: str) -> None:
        """
        Copy directory tree while filtering out unnecessary files
        
        Args:
            src: Source directory path
            dst: Destination directory path
        """
        # Create destination directory if it doesn't exist
        os.makedirs(dst, exist_ok=True)
        
        # Directories to skip
        skip_dirs = {
            '.git', '__pycache__', '.github', '.pytest_cache', '.vscode',
            'node_modules', 'dist', 'build', '.ipynb_checkpoints', 'venv',
            'env', '.env', '.venv', '.mypy_cache', '.ruff_cache', '.egg-info',
            '__MACOSX', '.DS_Store'
        }
        
        # File patterns to skip
        skip_patterns = (
            '*.pyc', '*.pyo', '*.so', '*.egg', '*.whl', '*.zip', '*.tar.gz',
            '*.log', '*.db', '*.sqlite', '*.swp', '*~', '*.bak', '*.tmp',
            '*.pth', '*.onnx', '.DS_Store', 'Thumbs.db', '.gitignore',
            '.gitattributes', '.gitmodules', '*.png', '*.jpg', '*.jpeg', 
            '*.webp', '*.gif', '*.mp4', '*.mp3', '*.avi', '*.mov', 
            '.env*', '*.o', '*.a', '*.dll', '*.exe'
        )
        
        # Max single file size to copy (100MB)
        max_file_size = 100 * 1024 * 1024
        
        # Walk the source directory
        for root, dirs, files in os.walk(src):
            # Remove directories to skip in-place (important to modify in-place as walk uses this list)
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            
            # Get relative path
            rel_path = os.path.relpath(root, src)
            if rel_path == '.':
                rel_path = ''
            
            # Create subdirectories in destination
            if rel_path:
                os.makedirs(os.path.join(dst, rel_path), exist_ok=True)
            
            # Copy files
            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(dst, rel_path, file)
                
                # Skip based on patterns
                if any(fnmatch.fnmatch(file, pattern) for pattern in skip_patterns):
                    logger.debug(f"Skipping file (pattern match): {src_file}")
                    continue
                
                # Skip large binary files
                try:
                    file_size = os.path.getsize(src_file)
                    if file_size > max_file_size:
                        # Exceptions for important files regardless of size
                        if not (file.endswith('.py') or file.endswith('.txt') or 
                                file.endswith('.md') or file.endswith('.json') or
                                file.endswith('.yaml') or file.endswith('.yml') or
                                file.endswith('.html') or file.endswith('.js') or
                                file.endswith('.css')):
                            logger.debug(f"Skipping large file ({file_size / 1024 / 1024:.2f}MB): {src_file}")
                            continue
                except Exception:
                    pass
                
                # Copy the file
                try:
                    shutil.copy2(src_file, dst_file)
                except (shutil.SameFileError, PermissionError) as e:
                    logger.warning(f"Error copying {src_file}: {e}")
    
    def _calculate_file_hash(self, file_path: str, chunk_size: int = 1024 * 1024) -> str:
        """
        Calculate MD5 hash of a file
        
        Args:
            file_path: Path to the file to hash
            chunk_size: Size of chunks to read at a time (default: 1MB)
            
        Returns:
            MD5 hash as a hex string
        """
        md5 = hashlib.md5()
        
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                md5.update(data)
                
        return md5.hexdigest()
