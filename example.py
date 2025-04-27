#!/usr/bin/env python3
"""
ComfyUI RunPod Package System - Main Entry Point
This script provides a unified interface for creating and deploying ComfyUI workflow packages.
"""

import os
import sys
import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ComfyUIPackager")

# Add local module search path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

# Import local modules
try:
    from interactive_package_creator import InteractivePackageCreator, MODEL_TYPES
    from simplified_workflow_parser import WorkflowParser
except ImportError as e:
    logger.error(f"Error importing required modules: {e}")
    logger.error("Make sure you're running this script from the project root directory.")
    sys.exit(1)


def create_package(args: argparse.Namespace) -> str:
    """
    Create a ComfyUI workflow package
    
    Args:
        args: Command line arguments
        
    Returns:
        Path to the created package file
    """
    logger.info(f"Creating package for workflow: {args.workflow}")
    
    # Validate ComfyUI path
    comfyui_path = os.path.abspath(args.comfyui_dir)
    if not os.path.exists(comfyui_path):
        logger.error(f"ComfyUI directory not found: {comfyui_path}")
        sys.exit(1)
    
    # Create package creator instance
    creator = InteractivePackageCreator(comfyui_path)
    
    # Get Civitai API key from environment or argument
    civitai_api_key = args.civitai_key or os.environ.get("CIVITAI_API_KEY")
    
    # Create the package
    try:
        package_path = creator.create_package(
            workflow_path=args.workflow,
            output_name=args.output,
            output_dir=args.output_dir,
            civitai_api_key=civitai_api_key,
            size_threshold_gb=args.size_threshold,
            include_manager=not args.no_manager
        )
        
        if package_path:
            logger.info(f"Package created successfully: {package_path}")
            return package_path
        else:
            logger.error("Failed to create package")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error creating package: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def analyze_workflow(args: argparse.Namespace) -> None:
    """
    Analyze a ComfyUI workflow without creating a package
    
    Args:
        args: Command line arguments
    """
    logger.info(f"Analyzing workflow: {args.workflow}")
    
    # Validate ComfyUI path
    comfyui_path = os.path.abspath(args.comfyui_dir)
    if not os.path.exists(comfyui_path):
        logger.error(f"ComfyUI directory not found: {comfyui_path}")
        sys.exit(1)
    
    # Create workflow parser instance
    parser = WorkflowParser(comfyui_path)
    
    # Parse the workflow
    try:
        dependencies = parser.parse_workflow(args.workflow)
        
        # Print results
        print("\n=== Workflow Analysis Results ===")
        
        print("\nCustom Nodes:")
        if dependencies['custom_nodes']:
            for name, path in dependencies['custom_nodes']:
                print(f"  - {name}")
        else:
            print("  No custom nodes found")
        
        print("\nModel References:")
        if dependencies['model_references']:
            for model in dependencies['model_references']:
                print(f"  - {model}")
        else:
            print("  No model references found")
        
        print("\nAnalysis complete.")
    except Exception as e:
        logger.error(f"Error analyzing workflow: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_installation(args: argparse.Namespace) -> None:
    """
    Test ComfyUI installation
    
    Args:
        args: Command line arguments
    """
    logger.info(f"Testing ComfyUI installation at: {args.comfyui_dir}")
    
    try:
        # Import the test module
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from test_installation import ComfyUIInstallationTester
        
        # Run tests
        tester = ComfyUIInstallationTester(args.comfyui_dir)
        success = tester.run_tests()
        
        if success:
            logger.info("✓ All tests passed! ComfyUI installation looks good.")
        else:
            logger.error("✗ Some tests failed. See logs above for details.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error testing installation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def generate_install_command(package_path: str) -> str:
    """
    Generate a command to install the package on a RunPod server
    
    Args:
        package_path: Path to the package file
        
    Returns:
        Installation command
    """
    # The install command assumes the package is uploaded to a web-accessible location
    # Replace this with the actual URL where the package will be hosted
    placeholder_url = "https://example.com/path/to/your-package.zip"
    
    install_command = (
        f"bash -c \"$(curl -sSL https://raw.githubusercontent.com/yourusername/comfyui/main/install_package.sh)\" "
        f"-- --package {placeholder_url}"
    )
    
    return install_command


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="ComfyUI RunPod Package System")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create package command
    create_parser = subparsers.add_parser("create", help="Create a package from a workflow")
    create_parser.add_argument("workflow", help="Path to workflow JSON file")
    create_parser.add_argument("--comfyui-dir", help="Path to ComfyUI installation", 
                              default=os.environ.get("COMFYUI_DIR", "."))
    create_parser.add_argument("--output", help="Name for the output package", default=None)
    create_parser.add_argument("--output-dir", help="Directory to save the package", default=None)
    create_parser.add_argument("--civitai-key", help="Civitai API key", default=None)
    create_parser.add_argument("--size-threshold", type=float, help="Size threshold in GB for large models", default=2.0)
    create_parser.add_argument("--no-manager", action="store_true", help="Don't include ComfyUI Manager")
    
    # Analyze workflow command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a workflow without creating a package")
    analyze_parser.add_argument("workflow", help="Path to workflow JSON file")
    analyze_parser.add_argument("--comfyui-dir", help="Path to ComfyUI installation", 
                               default=os.environ.get("COMFYUI_DIR", "."))
    
    # Test installation command
    test_parser = subparsers.add_parser("test", help="Test ComfyUI installation")
    test_parser.add_argument("--comfyui-dir", help="Path to ComfyUI installation", 
                            default=os.environ.get("COMFYUI_DIR", "."))
    
    # Global options
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Execute the requested command
    if args.command == "create":
        package_path = create_package(args)
        
        # Generate and display installation command
        install_command = generate_install_command(package_path)
        print("\n=== Installation Command ===")
        print("Upload your package to a web-accessible location, then run this command on your RunPod server:")
        print(f"\n{install_command}\n")
        print("Replace the URL with the actual location where you uploaded the package.")
        
    elif args.command == "analyze":
        analyze_workflow(args)
        
    elif args.command == "test":
        test_installation(args)
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
