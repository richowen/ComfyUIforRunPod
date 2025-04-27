#!/usr/bin/env python3
"""
ComfyUI RunPod Installation Test
Tests that the ComfyUI installation and custom package are working correctly.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InstallationTest")


class ComfyUIInstallationTester:
    """Tests a ComfyUI installation for correct setup and functioning"""
    
    def __init__(self, comfyui_dir: str):
        """
        Initialize the tester with ComfyUI directory
        
        Args:
            comfyui_dir: Path to ComfyUI installation
        """
        self.comfyui_dir = os.path.abspath(comfyui_dir)
        logger.info(f"Testing ComfyUI installation at: {self.comfyui_dir}")
    
    def run_tests(self) -> bool:
        """
        Run all installation tests
        
        Returns:
            True if all tests pass, False otherwise
        """
        tests = [
            self.test_comfyui_exists,
            self.test_core_files,
            self.test_model_directories,
            self.test_custom_nodes,
            self.test_workflows,
            self.test_python_dependencies,
            self.test_gpu_availability
        ]
        
        test_results = []
        for test in tests:
            try:
                result = test()
                test_results.append(result)
                if not result:
                    logger.warning(f"Test failed: {test.__name__}")
            except Exception as e:
                logger.error(f"Error in test {test.__name__}: {e}")
                test_results.append(False)
        
        # Print summary
        passed = sum(1 for result in test_results if result)
        total = len(test_results)
        logger.info(f"Test Summary: {passed}/{total} tests passed")
        
        return all(test_results)
    
    def test_comfyui_exists(self) -> bool:
        """Check if ComfyUI directory exists and has basic structure"""
        if not os.path.isdir(self.comfyui_dir):
            logger.error(f"ComfyUI directory not found: {self.comfyui_dir}")
            return False
            
        logger.info("✓ ComfyUI directory exists")
        return True
    
    def test_core_files(self) -> bool:
        """Check if core ComfyUI files exist"""
        core_files = [
            "main.py",
            "comfy/sd.py",
            "web/index.html"
        ]
        
        missing_files = []
        for file in core_files:
            file_path = os.path.join(self.comfyui_dir, file)
            if not os.path.exists(file_path):
                missing_files.append(file)
        
        if missing_files:
            logger.error(f"Missing core files: {', '.join(missing_files)}")
            return False
            
        logger.info("✓ Core ComfyUI files exist")
        return True
    
    def test_model_directories(self) -> bool:
        """Check if model directories exist and are readable"""
        model_dirs = [
            "models/checkpoints",
            "models/loras",
            "models/vae",
            "models/controlnet",
            "models/embeddings"
        ]
        
        missing_dirs = []
        for dir_path in model_dirs:
            full_path = os.path.join(self.comfyui_dir, dir_path)
            if not os.path.isdir(full_path):
                missing_dirs.append(dir_path)
                continue
                
            # Check if directory is readable
            try:
                os.listdir(full_path)
            except PermissionError:
                logger.error(f"Directory not readable: {dir_path}")
                return False
        
        if missing_dirs:
            logger.error(f"Missing model directories: {', '.join(missing_dirs)}")
            return False
            
        logger.info("✓ Model directories exist and are readable")
        return True
    
    def test_custom_nodes(self) -> bool:
        """Check if custom_nodes directory exists and has content"""
        custom_nodes_dir = os.path.join(self.comfyui_dir, "custom_nodes")
        
        if not os.path.isdir(custom_nodes_dir):
            logger.error(f"Custom nodes directory not found: {custom_nodes_dir}")
            return False
            
        # Check if there are any custom nodes installed
        custom_nodes = [d for d in os.listdir(custom_nodes_dir) 
                      if os.path.isdir(os.path.join(custom_nodes_dir, d))]
                      
        if not custom_nodes:
            logger.warning("No custom nodes found in custom_nodes directory")
            
        logger.info(f"✓ Found {len(custom_nodes)} custom node packages")
        for node in custom_nodes:
            logger.info(f"  - {node}")
            
        return True
    
    def test_workflows(self) -> bool:
        """Check if workflows directory exists and has content"""
        workflows_dir = os.path.join(self.comfyui_dir, "user/default/workflows")
        
        if not os.path.isdir(workflows_dir):
            logger.warning(f"Workflows directory not found: {workflows_dir}")
            os.makedirs(workflows_dir, exist_ok=True)
            logger.info("Created workflows directory")
            return True
            
        # Check if there are any workflows
        workflow_files = [f for f in os.listdir(workflows_dir) 
                        if f.endswith('.json') and os.path.isfile(os.path.join(workflows_dir, f))]
                        
        if not workflow_files:
            logger.warning("No workflow files found in workflows directory")
        else:
            logger.info(f"✓ Found {len(workflow_files)} workflow files")
            
        return True
    
    def test_python_dependencies(self) -> bool:
        """Check for required Python dependencies"""
        required_packages = [
            "torch",
            "numpy",
            "pillow"
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            logger.error(f"Missing Python packages: {', '.join(missing_packages)}")
            return False
            
        logger.info("✓ Required Python packages are installed")
        return True
    
    def test_gpu_availability(self) -> bool:
        """Check if GPU is available"""
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                for i in range(gpu_count):
                    device_name = torch.cuda.get_device_name(i)
                    logger.info(f"✓ GPU {i}: {device_name}")
                return True
            else:
                logger.warning("No CUDA GPUs available! ComfyUI will run slowly on CPU.")
                return True  # Return True as this might be expected in some environments
        except ImportError:
            logger.error("Could not check GPU availability (torch not installed)")
            return False
        except Exception as e:
            logger.error(f"Error checking GPU availability: {e}")
            return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="ComfyUI RunPod Installation Test")
    parser.add_argument("--comfyui-dir", help="Path to ComfyUI directory", 
                       default=os.environ.get("COMFYUI_DIR", "/workspace/ComfyUI"))
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run tests
    tester = ComfyUIInstallationTester(args.comfyui_dir)
    success = tester.run_tests()
    
    if success:
        logger.info("✓ All tests passed! ComfyUI installation looks good.")
        return 0
    else:
        logger.error("✗ Some tests failed. See logs above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
