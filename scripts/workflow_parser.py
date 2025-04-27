#!/usr/bin/env python3
"""
Optimized ComfyUI Workflow Parser
Extracts model and custom node dependencies from ComfyUI workflow files with improved accuracy.

Key features:
- Better handling of extra_model_paths.yaml
- Improved custom node detection
- More accurate model type identification
- Support for multiple workflow formats
"""

import json
import os
import re
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any, Union


class WorkflowParser:
    """Parses ComfyUI workflows to extract model and custom node dependencies"""
    
    def __init__(self, comfyui_path: str):
        """
        Initialize the workflow parser with the ComfyUI installation directory
        
        Args:
            comfyui_path: Path to the ComfyUI installation
        """
        self.comfyui_path = os.path.abspath(comfyui_path)
        self.model_paths = self._load_model_paths()
        self.custom_node_packages = self._get_custom_node_packages()
        
    def _load_model_paths(self) -> Dict[str, List[str]]:
        """
        Load model paths from ComfyUI's default locations and extra_model_paths.yaml
        
        Returns:
            Dictionary mapping model types to lists of possible paths
        """
        # Default ComfyUI model paths - keep these as fallbacks
        model_paths = {
            "checkpoints": [os.path.join(self.comfyui_path, "models", "checkpoints")],
            "vae": [os.path.join(self.comfyui_path, "models", "vae")],
            "loras": [os.path.join(self.comfyui_path, "models", "loras")],
            "embeddings": [os.path.join(self.comfyui_path, "models", "embeddings")],
            "controlnet": [os.path.join(self.comfyui_path, "models", "controlnet")],
            "clip": [os.path.join(self.comfyui_path, "models", "clip")],
            "clip_vision": [os.path.join(self.comfyui_path, "models", "clip_vision")],
            "upscale_models": [os.path.join(self.comfyui_path, "models", "upscale_models")],
            "facerestore_models": [os.path.join(self.comfyui_path, "models", "facerestore_models")],
            "insightface": [os.path.join(self.comfyui_path, "models", "insightface")],
            "ultralytics": [os.path.join(self.comfyui_path, "models", "ultralytics")],
            "unet": [os.path.join(self.comfyui_path, "models", "unet")],
            "diffusion_models": [os.path.join(self.comfyui_path, "models", "diffusion_models")],
            "text_encoders": [os.path.join(self.comfyui_path, "models", "text_encoders")],
            "llm": [os.path.join(self.comfyui_path, "models", "LLM")],
            "configs": [os.path.join(self.comfyui_path, "models", "configs")],
            "vae_approx": [os.path.join(self.comfyui_path, "models", "vae_approx")],
            "sams": [os.path.join(self.comfyui_path, "models", "sams")],
            "gligen": [os.path.join(self.comfyui_path, "models", "gligen")],
            "hypernetworks": [os.path.join(self.comfyui_path, "models", "hypernetworks")],
        }
        
        # Look for extra_model_paths.yaml in multiple locations
        extra_paths_locations = [
            os.path.join(self.comfyui_path, "extra_model_paths.yaml"),
            # Sometimes it might be in the parent directory if the script is run from a subdir
            os.path.join(os.path.dirname(self.comfyui_path), "extra_model_paths.yaml"),
            # Current working directory
            os.path.join(os.getcwd(), "extra_model_paths.yaml"),
        ]
        
        # Debug output to help troubleshoot
        print("Searching for extra_model_paths.yaml in:")
        for path in extra_paths_locations:
            print(f" - {path} {'(FOUND)' if os.path.exists(path) else '(not found)'}")
        
        extra_paths_file = None
        for path in extra_paths_locations:
            if os.path.exists(path):
                extra_paths_file = path
                break
        
        if extra_paths_file:
            try:
                print(f"Loading model paths from {extra_paths_file}")
                with open(extra_paths_file, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                
                if yaml_data:
                    # Process each UI configuration
                    for ui_name, ui_config in yaml_data.items():
                        if not isinstance(ui_config, dict) or 'base_path' not in ui_config:
                            print(f"Warning: Invalid configuration for {ui_name}, skipping")
                            continue
                            
                        # Get and normalize base path
                        base_path = ui_config['base_path']
                        
                        # Expand home directory if needed
                        if base_path.startswith('~'):
                            base_path = os.path.expanduser(base_path)
                            
                        # Convert to absolute path if it's not already
                        if not os.path.isabs(base_path):
                            # If it's a relative path, make it relative to the YAML file location
                            yaml_dir = os.path.dirname(os.path.abspath(extra_paths_file))
                            base_path = os.path.normpath(os.path.join(yaml_dir, base_path))
                            
                        # Verify the base path exists
                        if not os.path.exists(base_path):
                            print(f"Warning: Base path does not exist: {base_path}")
                            continue
                            
                        is_default = ui_config.get('is_default', False)
                        print(f"Using base path for {ui_name}: {base_path} (default: {is_default})")
                        
                        # Process each model type in the UI config
                        for model_type, rel_path in ui_config.items():
                            if model_type in ('base_path', 'is_default'):
                                continue
                                
                            # Normalize model type for consistency
                            model_type_normalized = model_type.lower()
                            
                            # Initialize list for this model type if not exists
                            if model_type_normalized not in model_paths:
                                model_paths[model_type_normalized] = []
                            
                            # Handle multi-line paths (YAML pipe character)
                            if isinstance(rel_path, str):
                                paths = []
                                if '\n' in rel_path:
                                    paths = [p.strip() for p in rel_path.split('\n') if p.strip()]
                                else:
                                    paths = [rel_path.strip()]
                                    
                                # Add each path to our model_paths
                                for path in paths:
                                    # Handle absolute and relative paths correctly
                                    if os.path.isabs(path):
                                        full_path = path
                                    else:
                                        full_path = os.path.abspath(os.path.join(base_path, path))
                                    
                                    print(f" - Adding path for {model_type}: {full_path}")
                                    
                                    # If this is the default UI, prioritize its paths
                                    if is_default:
                                        model_paths[model_type_normalized].insert(0, full_path)
                                    else:
                                        model_paths[model_type_normalized].append(full_path)
            except Exception as e:
                print(f"Error loading extra_model_paths.yaml: {e}")
                import traceback
                traceback.print_exc()
                
        return model_paths
    
    def _get_custom_node_packages(self) -> Dict[str, str]:
        """
        Get mapping of custom node identifiers to their installation paths
        
        Returns:
            Dictionary mapping custom node IDs to their paths
        """
        custom_nodes_dir = os.path.join(self.comfyui_path, "custom_nodes")
        custom_node_packages = {}
        
        if not os.path.exists(custom_nodes_dir):
            return custom_node_packages
        
        for node_package in os.listdir(custom_nodes_dir):
            package_path = os.path.join(custom_nodes_dir, node_package)
            if not os.path.isdir(package_path):
                continue
                
            # Use the folder name as an identifier (lowercase for case-insensitive matching)
            custom_node_packages[node_package.lower()] = package_path
            
            # Look for any metadata or configuration files that might have node IDs
            metadata_files = [
                os.path.join(package_path, "node_info.json"),
                os.path.join(package_path, "manifest.json"),
                os.path.join(package_path, "config.json"),
                os.path.join(package_path, "package.json"),
            ]
            
            for metadata_file in metadata_files:
                if os.path.exists(metadata_file):
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            
                        # Extract ID information from metadata
                        if isinstance(data, dict):
                            for key in ['id', 'identifier', 'name', 'package_name']:
                                if key in data and isinstance(data[key], str):
                                    custom_node_packages[data[key].lower()] = package_path
                                    
                    except Exception:
                        pass
            
            # Search Python files for node IDs
            for root, _, files in os.walk(package_path):
                for file in files:
                    if file.endswith('.py'):
                        try:
                            file_path = os.path.join(root, file)
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                
                            # Various patterns for node IDs in Python code
                            id_patterns = [
                                # Common pattern for ComfyUI node class mappings
                                r'NODE_CLASS_MAPPINGS\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]',
                                
                                # Node identifiers
                                r'cnr_id["\s\']+:\s*["\']([^"\']+)["\']',
                                r'aux_id["\s\']+:\s*["\']([^"\']+)["\']',
                                r'id_mapping\s*=\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                r'ID\s*=\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                
                                # Class definitions that often correspond to node names
                                r'class\s+([\w\d_]+)\s*\([\w\d_\.]+Node\s*\)',
                                
                                # Less specific patterns, but might catch some node IDs
                                r'@inertia\.aat\(\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                r'register_node\s*\(\s*[\'"]([\w\d_\-\/]+)[\'"]',
                            ]
                            
                            for pattern in id_patterns:
                                matches = re.findall(pattern, content)
                                for match in matches:
                                    custom_node_packages[match.lower()] = package_path
                                    # Also add with common prefixes/suffixes for better matching
                                    if "/" not in match:
                                        custom_node_packages[f"{node_package.lower()}/{match.lower()}"] = package_path
                        except:
                            # Silently ignore errors in reading files
                            pass
                            
            # Add commonly used naming patterns based on folder name
            package_name_lower = node_package.lower()
            common_prefixes = ["", "comfyui-", "comfyui_", "sd-", "sd_"]
            common_suffixes = ["", "-nodes", "_nodes", "-comfyui", "_comfyui"]
            
            for prefix in common_prefixes:
                for suffix in common_suffixes:
                    variation = f"{prefix}{package_name_lower}{suffix}"
                    if variation != package_name_lower:
                        custom_node_packages[variation] = package_path
                        
                    # GitHub format: username/repo-name
                    custom_node_packages[f"unknown/{variation}"] = package_path
        
        return custom_node_packages
    
    def parse_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """
        Parse a workflow file to extract model and custom node dependencies
        
        Args:
            workflow_path: Path to the workflow JSON file
            
        Returns:
            Dictionary with parsed dependencies:
            {
                'custom_nodes': [(package_id, package_path), ...],
                'models': {
                    'checkpoints': [(model_name, model_path), ...],
                    'vae': [...],
                    ...
                }
            }
        """
        result = {
            'custom_nodes': [],
            'models': {}
        }
        
        # Initialize model types
        for model_type in self.model_paths.keys():
            result['models'][model_type] = []
        
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            # Handle different workflow formats
            if isinstance(workflow, dict):
                if 'nodes' in workflow:
                    # Standard ComfyUI format
                    nodes = workflow['nodes']
                elif 'workflow' in workflow and isinstance(workflow['workflow'], dict) and 'nodes' in workflow['workflow']:
                    # Nested format sometimes used
                    nodes = workflow['workflow']['nodes']
                else:
                    # Try to find an array of nodes at any top level key
                    nodes = None
                    for key, value in workflow.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and 'type' in value[0]:
                            nodes = value
                            break
                    
                    if nodes is None:
                        print(f"Warning: Could not identify nodes structure in {workflow_path}")
                        return result
            elif isinstance(workflow, list) and len(workflow) > 0 and isinstance(workflow[0], dict):
                # Some workflows might just be an array of nodes
                nodes = workflow
            else:
                print(f"Warning: Unknown workflow format in {workflow_path}")
                return result
                
            # Track custom node IDs and models
            custom_node_ids = set()
            found_models = {}
            
            # Track node types to find custom nodes that don't explicitly declare themselves
            node_types = set()
            
            # Process each node
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                
                # Keep track of all node types
                if 'type' in node:
                    node_types.add(node['type'].lower())
                
                # Extract custom node package ID
                if 'properties' in node and isinstance(node['properties'], dict):
                    props = node['properties']
                    
                    # Look for custom node identifiers in properties
                    for id_key in ['cnr_id', 'aux_id', 'Node name for S&R', 'custom_node_id', 'node_id']:
                        if id_key in props and props[id_key]:
                            node_id = props[id_key]
                            if isinstance(node_id, str) and node_id.strip():
                                custom_node_ids.add(node_id.lower())
                
                # Extract model paths from widgets
                if 'widgets_values' in node and isinstance(node['widgets_values'], list):
                    values = node['widgets_values']
                    
                    # Determine model type from node type
                    node_type = node.get('type', '').lower()
                    model_type = self._guess_model_type(node_type)
                    
                    # Check if any widget value looks like a model path
                    for value_idx, value in enumerate(values):
                        if not isinstance(value, str) or not value:
                            continue
                            
                        # Skip values that are clearly not model files
                        if value.lower() in ('randomize', 'true', 'false', 'enable', 'disable', 'none'):
                            continue
                        
                        # Skip very short values
                        if len(value) < 5:
                            continue
                            
                        # If it has a file extension that looks like a model, add it
                        model_extensions = ('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx', '.msgpack')
                        if any(value.lower().endswith(ext) for ext in model_extensions):
                            # If we didn't guess the model type from the node, try from the extension
                            if not model_type:
                                model_type = self._guess_model_type_from_filename(value)
                            
                            if model_type:
                                # Store model in the category
                                if model_type not in found_models:
                                    found_models[model_type] = set()
                                found_models[model_type].add(value)
                                
                                # Try to determine model type based on widget index and node type
                                # This helps with nodes that load multiple model types
                                alt_type = self._refine_model_type(node_type, value_idx, len(values), value)
                                if alt_type and alt_type != model_type:
                                    if alt_type not in found_models:
                                        found_models[alt_type] = set()
                                    found_models[alt_type].add(value)
            
            # Check node types against known custom nodes
            # Some custom nodes don't declare themselves but have distinct node types
            for node_type in node_types:
                # Skip basic node types likely to be part of core ComfyUI
                if node_type in ('note', 'reroute', 'primitive', 'output', 'input'):
                    continue
                    
                # Add variations of the node type as potential custom node IDs
                custom_node_ids.add(node_type)
                
                # Some common patterns for node types
                parts = node_type.split('_')
                if len(parts) > 1:
                    # Try prefix as potential package name
                    custom_node_ids.add(parts[0])
                    custom_node_ids.add(f"{parts[0]}/{node_type}")
                    
                    # If 3+ parts, try first two as package
                    if len(parts) >= 3:
                        prefix = f"{parts[0]}_{parts[1]}"
                        custom_node_ids.add(prefix)
                        custom_node_ids.add(f"{prefix}/{node_type}")
            
            # Resolve custom node paths from IDs
            resolved_nodes = set()
            for node_id in custom_node_ids:
                # Check for direct match
                if node_id in self.custom_node_packages:
                    path = self.custom_node_packages[node_id]
                    package_name = os.path.basename(path)
                    resolved_nodes.add((package_name, path))
                else:
                    # Check for partial matches
                    for package_id, path in self.custom_node_packages.items():
                        # Various matching strategies
                        if (node_id in package_id or package_id in node_id or
                            node_id.replace('-', '_') == package_id.replace('-', '_') or
                            node_id.split('/')[-1] == package_id.split('/')[-1]):
                            package_name = os.path.basename(path)
                            resolved_nodes.add((package_name, path))
                            break
            
            result['custom_nodes'] = list(resolved_nodes)
            
            # Resolve model paths - convert sets to lists with paths
            for model_type, model_names in found_models.items():
                resolved_models = []
                for model_name in model_names:
                    resolved_path = self._resolve_model_path(model_type, model_name)
                    if resolved_path:
                        resolved_models.append((model_name, resolved_path))
                        
                if model_type in result['models']:
                    result['models'][model_type] = resolved_models
            
            return result
            
        except Exception as e:
            print(f"Error parsing workflow: {e}")
            import traceback
            traceback.print_exc()
            return result
    
    def _guess_model_type(self, node_type: str) -> Optional[str]:
        """
        Guess the model type based on the node type.
        
        Args:
            node_type: The type of the node
            
        Returns:
            The guessed model type or None
        """
        node_type = node_type.lower()
        
        # Map node types to model types - expanded for better coverage
        type_mapping = {
            # Checkpoints
            'checkpoint': 'checkpoints',
            'checkpointloader': 'checkpoints', 
            'load': 'checkpoints',
            'sdxl': 'checkpoints',
            'model': 'checkpoints',
            'loadcheckpoint': 'checkpoints',
            'diffus': 'checkpoints',
            
            # VAEs
            'vae': 'vae',
            'vaeloader': 'vae',
            'loadvae': 'vae',
            'variational': 'vae',
            'encoder': 'vae',
            'decoder': 'vae',
            
            # CLIP models
            'clip': 'clip',
            'loadclip': 'clip',
            'cliploader': 'clip',
            
            # CLIP Vision
            'clipvision': 'clip_vision',
            'visionloader': 'clip_vision',
            'loadcv': 'clip_vision',
            
            # LoRAs
            'lora': 'loras',
            'loraloader': 'loras',
            'loadlora': 'loras',
            'loha': 'loras',
            'lycoris': 'loras',
            
            # Embeddings
            'embedding': 'embeddings',
            'textualinversion': 'embeddings',
            'loadembedding': 'embeddings',
            'ti': 'embeddings',
            
            # Hypernetworks
            'hypernetwork': 'hypernetworks',
            'loadhyper': 'hypernetworks',
            
            # ControlNet
            'controlnet': 'controlnet',
            'loadcontrol': 'controlnet',
            'control': 'controlnet',
            
            # Upscalers
            'upscale': 'upscale_models',
            'upscaler': 'upscale_models',
            'esrgan': 'upscale_models',
            'loadupscale': 'upscale_models',
            
            # Face models
            'facedetection': 'insightface',
            'insightface': 'insightface',
            'facerestore': 'facerestore_models',
            'gfpgan': 'facerestore_models',
            'codeformer': 'facerestore_models',
            
            # Object detection
            'ultralytics': 'ultralytics',
            'yolo': 'ultralytics',
            'detection': 'ultralytics',
            
            # Text models
            'llm': 'llm',
            'textgen': 'llm',
            'languagemodel': 'llm',
            
            # Segmentation
            'sam': 'sams',
            'segment': 'sams',
            'segmentanything': 'sams',
        }
        
        for key, value in type_mapping.items():
            if key in node_type:
                return value
                
        return None
    
    def _guess_model_type_from_filename(self, filename: str) -> Optional[str]:
        """
        Guess the model type based on the filename.
        
        Args:
            filename: The filename to analyze
            
        Returns:
            The guessed model type or None
        """
        filename = filename.lower()
        
        # Checkpoints and LoRAs usually have these extensions
        if filename.endswith('.safetensors') or filename.endswith('.ckpt'):
            # Try to determine by filename patterns
            if 'lora' in filename:
                return 'loras'
            elif 'vae' in filename:
                return 'vae'
            elif 'embedding' in filename or 'embed' in filename or '/embeddings/' in filename:
                return 'embeddings'
            elif 'controlnet' in filename or 'control_' in filename or '/control/' in filename:
                return 'controlnet'
            elif 'inpaint' in filename and not ('sd15_inpaint' in filename or 'sd_inpaint' in filename):
                # Likely a controlnet inpaint model
                return 'controlnet'
            elif 'clip' in filename and ('vision' in filename or '/clip_vision/' in filename):
                return 'clip_vision'
            elif 'clip' in filename or '/clip/' in filename:
                return 'clip'
            else:
                return 'checkpoints'  # Default for .safetensors/.ckpt
        
        # Other model types
        elif filename.endswith('.pt') or filename.endswith('.pth'):
            if 'sam' in filename or '/sam/' in filename:
                return 'sams'
            elif ('gfpgan' in filename or 'codeformer' in filename or 
                  'face' in filename or '/facerestore/' in filename):
                return 'facerestore_models'
            elif ('upscale' in filename or 'esrgan' in filename or 
                 '/upscaler/' in filename or '/upscale_models/' in filename):
                return 'upscale_models'
            
        elif filename.endswith('.onnx'):
            if 'inswapper' in filename or 'insight' in filename or '/insightface/' in filename:
                return 'insightface'
                
        # When in doubt, default to checkpoints
        return 'checkpoints'
    
    def _refine_model_type(self, node_type: str, value_idx: int, total_values: int, value: str) -> Optional[str]:
        """
        Refine model type based on widget position and other heuristics
        
        Args:
            node_type: Type of the node
            value_idx: Index of the value in the widgets list
            total_values: Total number of widget values
            value: The model filename or path
            
        Returns:
            Refined model type or None
        """
        node_type = node_type.lower()
        value = value.lower()
        
        # Handle multi-model nodes like LoRA loaders
        if ('lora' in node_type or 'lycoris' in node_type) and total_values >= 3:
            # First value in LoRA nodes is usually the model/checkpoint
            if value_idx == 0 and ('checkpoint' in value or not any(x in value for x in ['lora', 'lyco'])):
                return 'checkpoints'
            # LoRA files themselves
            elif ('lora' in value or 'lyco' in value) or value_idx in [1, 2]:
                return 'loras'
        
        # ControlNet nodes often have the controlnet as one param and the model as another
        elif 'control' in node_type and total_values >= 2:
            if value_idx == 0 and ('sd' in value or 'stable' in value):
                return 'checkpoints'
            elif 'control' in value or value_idx == 1:
                return 'controlnet'
        
        # Upscalers often have multiple models
        elif 'upscale' in node_type and total_values >= 2:
            return 'upscale_models'
            
        # Some nodes handle multiple model types
        elif 'loader' in node_type and total_values >= 2:
            # Try to determine from value itself
            if 'vae' in value:
                return 'vae'
            elif 'lora' in value:
                return 'loras'
            elif 'control' in value:
                return 'controlnet'
            elif 'embed' in value:
                return 'embeddings'
        
        return None
    
    def _resolve_model_path(self, model_type: str, model_name: str) -> Optional[str]:
        """
        Resolve a model name to its actual file path.
        
        Args:
            model_type: Type of the model (checkpoints, vae, etc.)
            model_name: Name of the model file
            
        Returns:
            Full path to the model file or None if not found
        """
        # Debug information
        print(f"Trying to locate model '{model_name}' of type '{model_type}'...")
        
        # Special case: if it's an absolute path and exists, return it directly
        if os.path.isabs(model_name) and os.path.exists(model_name):
            print(f"  Found as absolute path: {model_name}")
            return model_name
        
        # Check if the type is available in our paths
        if model_type not in self.model_paths:
            # Try alternate types for common confusions
            alternate_types = []
            if model_type == 'checkpoints':
                alternate_types = ['checkpoint', 'stable-diffusion', 'sd']
            elif model_type == 'loras':
                alternate_types = ['lora', 'locon', 'lycoris']
            elif model_type == 'vae':
                alternate_types = ['vae_approx', 'vaes']
            
            # Check if any alternates exist in our paths
            for alt_type in alternate_types:
                if alt_type in self.model_paths:
                    print(f"  Using alternate type {alt_type} instead of {model_type}")
                    model_type = alt_type
                    break
            
            # If still not available
            if model_type not in self.model_paths:
                print(f"  No paths configured for model type: {model_type}")
                return None
        
        # Normalize model type
        model_type = model_type.lower()
        
        # Handle path separators based on operating system
        # We need to handle both normal path separators (/ or \) and the literal \\ string 
        # that might come from JSON serialization
        if '\\' in model_name:
            model_name = model_name.replace('\\\\', '\\')
            
        # Special handling for paths with directories
        has_subdir = ('/' in model_name or '\\' in model_name)
        model_subdir = ''
        base_filename = model_name
        
        # If this is a path with subdirectories, extract them
        if has_subdir:
            model_subdir = os.path.dirname(model_name)
            base_filename = os.path.basename(model_name)
            print(f"  Model appears to be in subdirectory: {model_subdir}")
        
        # Create a list of possible filenames (to handle case sensitivity and minor differences)
        possible_filenames = [
            base_filename,                                # Original filename
            base_filename.lower(),                        # Lowercase
            base_filename.replace(' ', '_'),              # Replace spaces with underscores
            base_filename.lower().replace(' ', '_'),      # Lowercase + underscores
            base_filename.replace('_', ' '),              # Replace underscores with spaces
            base_filename.lower().replace('_', ' '),      # Lowercase + spaces
            # Add model extensions if not present
            f"{os.path.splitext(base_filename)[0]}.safetensors" if not base_filename.endswith('.safetensors') else None,
            f"{os.path.splitext(base_filename)[0]}.ckpt" if not base_filename.endswith('.ckpt') else None,
            f"{os.path.splitext(base_filename)[0]}.pt" if not base_filename.endswith('.pt') else None,
        ]
        # Filter out None values
        possible_filenames = [f for f in possible_filenames if f]
        
        # Step 1: First try exact match with the full path including subdirectory
        print(f"  Trying exact match with {len(self.model_paths[model_type])} base paths...")
        for base_path in self.model_paths[model_type]:
            # Try exact path first
            model_path = os.path.join(base_path, model_name)
            if os.path.exists(model_path):
                print(f"  Found exact match: {model_path}")
                return model_path
        
        # Step 2: If we have a subdirectory, try looking for it specifically
        if has_subdir:
            print(f"  Checking for subdirectory '{model_subdir}' in base paths...")
            for base_path in self.model_paths[model_type]:
                potential_dir = os.path.join(base_path, model_subdir)
                if os.path.isdir(potential_dir):
                    for possible_name in possible_filenames:
                        file_path = os.path.join(potential_dir, possible_name)
                        if os.path.exists(file_path):
                            print(f"  Found in subdirectory: {file_path}")
                            return file_path
        
        # Step 3: Check direct match for the filename in base directories
        print(f"  Trying all {len(possible_filenames)} filename variations directly in base dirs...")
        for base_path in self.model_paths[model_type]:
            for possible_name in possible_filenames:
                direct_path = os.path.join(base_path, possible_name)
                if os.path.exists(direct_path):
                    print(f"  Found direct match: {direct_path}")
                    return direct_path
                
        # Step 4: Try searching for subdirectories with similar names
        if has_subdir:
            print(f"  Checking for similar subdirectory names...")
            subdir_lower = model_subdir.lower()
            for base_path in self.model_paths[model_type]:
                # Skip if base path doesn't exist
                if not os.path.exists(base_path):
                    continue
                    
                try:
                    # Look for subdirectories with names that are similar
                    for item in os.listdir(base_path):
                        if os.path.isdir(os.path.join(base_path, item)) and item.lower() == subdir_lower:
                            potential_dir = os.path.join(base_path, item)
                            for possible_name in possible_filenames:
                                file_path = os.path.join(potential_dir, possible_name)
                                if os.path.exists(file_path):
                                    print(f"  Found in similar subdirectory: {file_path}")
                                    return file_path
                except Exception as e:
                    print(f"  Error checking subdirectories in {base_path}: {e}")
        
        # Step 5: Look in any immediate subdirectories (one level)  
        print("  Checking immediate subdirectories...")
        for base_path in self.model_paths[model_type]:
            try:
                if not os.path.exists(base_path):
                    continue
                    
                for item in os.listdir(base_path):
                    subdir = os.path.join(base_path, item)
                    if os.path.isdir(subdir):
                        for possible_name in possible_filenames:
                            subdir_path = os.path.join(subdir, possible_name)
                            if os.path.exists(subdir_path):
                                print(f"  Found in immediate subdirectory: {subdir_path}")
                                return subdir_path
                                
                        # If we have a subdirectory in the model name, also check in this subdir
                        if has_subdir:
                            nested_dir = os.path.join(subdir, model_subdir)
                            if os.path.isdir(nested_dir):
                                for possible_name in possible_filenames:
                                    nested_path = os.path.join(nested_dir, possible_name)
                                    if os.path.exists(nested_path):
                                        print(f"  Found in nested subdirectory: {nested_path}")
                                        return nested_path
            except Exception as e:
                print(f"  Error checking subdirectories in {base_path}: {e}")
                
        # Step 6: Deep search - walk the directory structure
        print("  Starting deep recursive search for model file...")
        for base_path in self.model_paths[model_type]:
            try:
                if not os.path.exists(base_path):
                    print(f"  Base path does not exist: {base_path}")
                    continue
                    
                # When searching for a model with a subdirectory, we've got two search strategies:
                
                # 1. Search for the exact file in any subdirectory
                for root, dirs, files in os.walk(base_path):
                    for file in files:
                        if file in possible_filenames or file.lower() in [f.lower() for f in possible_filenames]:
                            found_path = os.path.join(root, file)
                            # If looking for a file in a subdirectory, check if we found it in that subdir
                            if has_subdir:
                                # Get relative path from base
                                rel_dir = os.path.relpath(os.path.dirname(found_path), base_path)
                                # Check if the directory name matches or contains our subdirectory
                                if (model_subdir.lower() in rel_dir.lower() or 
                                    os.path.basename(rel_dir).lower() == os.path.basename(model_subdir).lower()):
                                    print(f"  Found in expected subdirectory structure: {found_path}")
                                    return found_path
                            else:
                                # Not looking for a subdirectory, just return the match
                                print(f"  Found in recursive search: {found_path}")
                                return found_path
                
                # 2. If we're looking for a subdirectory, try to find it first
                if has_subdir:
                    print(f"  Looking specifically for subdirectory '{model_subdir}'...")
                    for root, dirs, _ in os.walk(base_path):
                        # Check if any directory matches our subdirectory
                        for dir_name in dirs:
                            if dir_name.lower() == os.path.basename(model_subdir).lower():
                                potential_dir = os.path.join(root, dir_name)
                                # Check for the file in this directory
                                for possible_name in possible_filenames:
                                    file_path = os.path.join(potential_dir, possible_name)
                                    if os.path.exists(file_path):
                                        print(f"  Found in matching directory: {file_path}")
                                        return file_path
            except Exception as e:
                print(f"  Error in recursive search of {base_path}: {e}")
        
        # Step 7: Try alternate model types
        alternate_types = {
            'checkpoints': ['loras', 'vae', 'diffusion_models'],
            'loras': ['checkpoints', 'embedding'],
            'vae': ['checkpoints'],
            'embedding': ['loras'],
            'controlnet': ['checkpoints']
        }
        
        if model_type in alternate_types:
            print(f"  Model not found. Trying alternate types: {alternate_types[model_type]}")
            for alt_type in alternate_types[model_type]:
                if alt_type in self.model_paths:
                    for base_path in self.model_paths[alt_type]:
                        # Try direct match in the alternate type directory
                        if has_subdir:
                            # Check with subdirectory
                            potential_dir = os.path.join(base_path, model_subdir)
                            if os.path.isdir(potential_dir):
                                for possible_name in possible_filenames:
                                    file_path = os.path.join(potential_dir, possible_name)
                                    if os.path.exists(file_path):
                                        print(f"  Found in alternate type {alt_type} with subdirectory: {file_path}")
                                        return file_path
                        
                        # Try without subdirectory
                        for possible_name in possible_filenames:
                            file_path = os.path.join(base_path, possible_name)
                            if os.path.exists(file_path):
                                print(f"  Found with alternate type {alt_type}: {file_path}")
                                return file_path
                        
                        # Try recursive search in alternate type for just the filename
                        if os.path.exists(base_path):
                            for root, _, files in os.walk(base_path):
                                for file in files:
                                    if file in possible_filenames or file.lower() in [f.lower() for f in possible_filenames]:
                                        found_path = os.path.join(root, file)
                                        print(f"  Found in {alt_type} recursive search: {found_path}")
                                        return found_path
        
        # If we get here, the model wasn't found
        print(f"Warning: Could not locate model: {model_name} (type: {model_type})")
        return None


def main():
    """Simple example usage and CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ComfyUI Workflow Parser")
    parser.add_argument("comfyui_path", help="Path to ComfyUI installation")
    parser.add_argument("workflow_path", help="Path to workflow JSON file")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--yaml", action="store_true", help="Output results as YAML")
    
    args = parser.parse_args()
    
    parser = WorkflowParser(args.comfyui_path)
    dependencies = parser.parse_workflow(args.workflow_path)
    
    if args.json:
        # Convert to serializable format
        serializable = {
            'custom_nodes': [{'name': name, 'path': path} for name, path in dependencies['custom_nodes']],
            'models': {}
        }
        
        for model_type, models in dependencies['models'].items():
            if models:
                serializable['models'][model_type] = [{'name': name, 'path': path} for name, path in models]
                
        import json
        print(json.dumps(serializable, indent=2))
        
    elif args.yaml:
        # Convert to serializable format for YAML
        serializable = {
            'custom_nodes': [{'name': name, 'path': path} for name, path in dependencies['custom_nodes']],
            'models': {}
        }
        
        for model_type, models in dependencies['models'].items():
            if models:
                serializable['models'][model_type] = [{'name': name, 'path': path} for name, path in models]
                
        import yaml
        print(yaml.dump(serializable, default_flow_style=False))
        
    else:
        # Print in human-readable format
        print("\nCustom Nodes:")
        for package_name, path in dependencies['custom_nodes']:
            print(f"  - {package_name}: {path}")
            
        print("\nModels:")
        for model_type, models in dependencies['models'].items():
            if models:
                print(f"  {model_type}:")
                for model_name, model_path in models:
                    print(f"    - {model_name}: {model_path}")


if __name__ == "__main__":
    sys.exit(main())
