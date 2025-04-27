#!/usr/bin/env python3
"""
Simplified ComfyUI Workflow Parser
Extracts model references from ComfyUI workflow files without trying to resolve paths.
"""

import json
import os
import re
from typing import Dict, List, Set, Any

class WorkflowParser:
    """Parses ComfyUI workflows to extract model references and custom node dependencies"""
    
    def __init__(self, comfyui_path: str):
        """
        Initialize the workflow parser with the ComfyUI installation directory
        
        Args:
            comfyui_path: Path to the ComfyUI installation
        """
        self.comfyui_path = os.path.abspath(comfyui_path)
        self.custom_node_packages = self._get_custom_node_packages()
        
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
                                r'NODE_CLASS_MAPPINGS\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]',
                                r'cnr_id["\s\']+:\s*["\']([^"\']+)["\']',
                                r'aux_id["\s\']+:\s*["\']([^"\']+)["\']',
                                r'id_mapping\s*=\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                r'ID\s*=\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                r'class\s+([\w\d_]+)\s*\([\w\d_\.]+Node\s*\)',
                                r'@inertia\.aat\(\s*[\'"]([\w\d_\-\/]+)[\'"]',
                                r'register_node\s*\(\s*[\'"]([\w\d_\-\/]+)[\'"]',
                            ]
                            
                            for pattern in id_patterns:
                                matches = re.findall(pattern, content)
                                for match in matches:
                                    custom_node_packages[match.lower()] = package_path
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
                    custom_node_packages[f"unknown/{variation}"] = package_path
        
        return custom_node_packages
    
    def parse_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """
        Parse a workflow file to extract model references and custom node dependencies
        
        Args:
            workflow_path: Path to the workflow JSON file
            
        Returns:
            Dictionary with parsed dependencies:
            {
                'custom_nodes': [(package_id, package_path), ...],
                'model_references': [model_reference_string, ...]
            }
        """
        result = {
            'custom_nodes': [],
            'model_references': []
        }
        
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
            model_references = set()
            
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
                
                # Extract model references from widgets
                if 'widgets_values' in node and isinstance(node['widgets_values'], list):
                    values = node['widgets_values']
                    
                    # Check if any widget value looks like a model path
                    for value in values:
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
                            model_references.add(value)
            
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
            result['model_references'] = list(model_references)
            
            return result
            
        except Exception as e:
            print(f"Error parsing workflow: {e}")
            import traceback
            traceback.print_exc()
            return result


def main():
    """Simple command-line script to extract model references from a workflow"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ComfyUI Simplified Workflow Parser")
    parser.add_argument("comfyui_path", help="Path to ComfyUI installation")
    parser.add_argument("workflow_path", help="Path to workflow JSON file")
    
    args = parser.parse_args()
    
    parser = WorkflowParser(args.comfyui_path)
    result = parser.parse_workflow(args.workflow_path)
    
    print("\nCustom Nodes:")
    for package_name, path in result['custom_nodes']:
        print(f"  - {package_name}: {path}")
        
    print("\nModel References Found:")
    for model_ref in result['model_references']:
        print(f"  - {model_ref}")


if __name__ == "__main__":
    import sys
    sys.exit(main())
