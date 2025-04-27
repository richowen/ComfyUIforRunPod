#!/usr/bin/env python3
"""
Optimized ComfyUI Model Downloader
A streamlined script for reliable model downloads with Civitai API support

Features:
- Robust download with retry mechanism
- Efficient Civitai API integration
- Hash verification for data integrity
- Progress reporting with ETA
- Parallel download capability
- Non-interactive operation for server environments
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import shutil
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ModelDownloader")

# Attempt to import requests, install if not available
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("Requests module not found, attempting installation...")
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        REQUESTS_AVAILABLE = True
        logger.info("Successfully installed requests.")
    except Exception as e:
        logger.warning(f"Could not install requests: {e}. Will use urllib instead.")


class ModelDownloader:
    """Handles downloading models with proper error handling and retry logic"""
    
    def __init__(self, base_dir: str, config_path: Optional[str] = None, max_workers: int = 1):
        """
        Initialize the model downloader
        
        Args:
            base_dir: Base directory where ComfyUI is installed
            config_path: Path to the config.json file (optional)
            max_workers: Maximum number of concurrent downloads (default: 1)
        """
        self.base_dir = os.path.abspath(base_dir)
        self.config_path = config_path
        self.max_workers = max_workers
        self.models_dir = self._ensure_models_directory()
        self.civitai_api_key = self._get_civitai_api_key()
        self.session = self._create_robust_session() if REQUESTS_AVAILABLE else None
        
    def _ensure_models_directory(self) -> str:
        """Ensure the models directory structure exists"""
        models_dir = os.path.join(self.base_dir, "models")
        
        # Create if it doesn't exist
        os.makedirs(models_dir, exist_ok=True)
        
        # Create standard subdirectories
        model_types = [
            "checkpoints", "loras", "controlnet", "vae", 
            "embeddings", "insightface", "ultralytics", 
            "clip", "clip_vision", "upscale_models", 
            "facerestore_models", "hypernetworks", "configs"
        ]
        
        for subdir in model_types:
            os.makedirs(os.path.join(models_dir, subdir), exist_ok=True)
        
        return models_dir
    
    def _get_civitai_api_key(self) -> Optional[str]:
        """Get Civitai API key from environment variable or config file"""
        # First try environment variable
        api_key = os.environ.get("CIVITAI_API_KEY")
        if api_key:
            logger.info("Using Civitai API key from environment variable")
            return api_key
        
        # Then try config files
        config_paths = [
            os.path.join(self.base_dir, "civitai_config.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "civitai_config.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "civitai_config.json")
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        if config.get("api_key"):
                            logger.info(f"Using Civitai API key from {config_path}")
                            return config["api_key"]
                except Exception as e:
                    logger.warning(f"Error reading Civitai config file {config_path}: {e}")
        
        logger.warning("No Civitai API key found. Some downloads may fail.")
        return None
    
    def _create_robust_session(self) -> requests.Session:
        """Create a requests session with retry logic"""
        session = requests.Session()
        
        # Configure retry strategy
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        
        # Mount the adapter with our retry strategy for all http/https requests
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))
        
        # Add default headers including user agent
        session.headers.update({
            "User-Agent": "ComfyUI-ModelDownloader/1.0"
        })
        
        return session
    
    def _get_headers_for_url(self, url: str) -> Dict[str, str]:
        """Get headers for a specific URL, including API keys if needed"""
        headers = {}
        
        # Add Civitai API key if this is a Civitai URL and we have a key
        if "civitai.com" in url and self.civitai_api_key:
            headers["Authorization"] = f"Bearer {self.civitai_api_key}"
            
        return headers
    
    def download_with_requests(self, url: str, dest_path: str, display_name: str) -> bool:
        """Download file using requests with progress reporting and retry"""
        if not self.session:
            logger.error("Requests session not available")
            return False
        
        # Create temporary directory for downloading
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, os.path.basename(dest_path))
        
        try:
            # Create directory structure if needed
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Get headers for this URL
            headers = self._get_headers_for_url(url)
            
            # Start download
            response = self.session.get(url, headers=headers, stream=True)
            if response.status_code != 200:
                logger.error(f"Error: Received status code {response.status_code} from server.")
                if "civitai.com" in url and response.status_code in [401, 403]:
                    logger.error("This may be due to missing or invalid Civitai API key.")
                return False
                
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            
            with open(temp_file, 'wb') as file:
                for data in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
                    downloaded += len(data)
                    file.write(data)
                    
                    # Display progress with ETA
                    elapsed = time.time() - start_time
                    rate = downloaded / elapsed if elapsed > 0 else 0
                    eta = (total_size - downloaded) / rate if rate > 0 else 0
                    
                    if total_size > 0:
                        percent = downloaded / total_size * 100
                        bar_len = 40
                        filled_len = int(bar_len * downloaded // total_size)
                        bar = '=' * filled_len + ' ' * (bar_len - filled_len)
                        
                        sys.stdout.write(f"\r{display_name}: [{bar}] {percent:.1f}% | "
                                        f"{downloaded/1024/1024:.1f}/{total_size/1024/1024:.1f}MB | "
                                        f"ETA: {eta:.0f}s")
                    else:
                        sys.stdout.write(f"\r{display_name}: {downloaded/1024/1024:.1f}MB downloaded")
                    
                    sys.stdout.flush()
            
            # Move from temp to final destination
            shutil.move(temp_file, dest_path)
            print(f"\nDownload complete: {display_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {display_name}: {e}")
            return False
            
        finally:
            # Clean up temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def download_with_urllib(self, url: str, dest_path: str, display_name: str) -> bool:
        """Fallback download method using urllib"""
        from urllib.request import urlopen, Request
        import ssl
        
        # Create a temporary file for downloading
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, os.path.basename(dest_path))
        
        # Create context to avoid SSL issues
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Prepare request with headers
        request = Request(url)
        if "civitai.com" in url and self.civitai_api_key:
            request.add_header("Authorization", f"Bearer {self.civitai_api_key}")
        
        try:
            # Create directory structure if needed
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Start download with retry logic
            retry_count = 0
            max_retries = 5
            
            while retry_count < max_retries:
                try:
                    # Start download
                    with urlopen(request, context=ctx) as response:
                        total = int(response.info().get('Content-Length', 0))
                        downloaded = 0
                        start_time = time.time()
                        
                        with open(temp_file, 'wb') as f:
                            while True:
                                chunk = response.read(1024*1024)  # 1MB chunks
                                if not chunk:
                                    break
                                downloaded += len(chunk)
                                f.write(chunk)
                                
                                # Display progress with ETA
                                elapsed = time.time() - start_time
                                rate = downloaded / elapsed if elapsed > 0 else 0
                                eta = (total - downloaded) / rate if rate > 0 else 0
                                
                                if total > 0:
                                    percent = downloaded / total * 100
                                    bar_len = 40
                                    filled_len = int(bar_len * downloaded // total)
                                    bar = '=' * filled_len + ' ' * (bar_len - filled_len)
                                    
                                    sys.stdout.write(f"\r{display_name}: [{bar}] {percent:.1f}% | "
                                                    f"{downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB | "
                                                    f"ETA: {eta:.0f}s")
                                else:
                                    sys.stdout.write(f"\r{display_name}: {downloaded/1024/1024:.1f}MB downloaded")
                                
                                sys.stdout.flush()
                    
                    # If we get here, download completed successfully
                    break
                    
                except (ssl.SSLError, ConnectionError, OSError) as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count  # Exponential backoff
                        logger.warning(f"Download failed, retrying in {wait_time}s... ({retry_count}/{max_retries})")
                        logger.warning(f"Error: {str(e)}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Maximum retries reached. Download failed.")
                        return False
            
            # Move from temp to final destination
            shutil.move(temp_file, dest_path)
            print(f"\nDownload complete: {display_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {display_name}: {e}")
            return False
            
        finally:
            # Clean up temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def verify_hash(self, file_path: str, expected_hash: str) -> bool:
        """Verify the MD5 hash of a file"""
        logger.info(f"Verifying file integrity for {os.path.basename(file_path)}...")
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        actual_hash = hash_md5.hexdigest()
        
        if actual_hash.lower() == expected_hash.lower():
            logger.info("Hash verification successful")
            return True
        else:
            logger.warning(f"Hash verification failed! Expected {expected_hash}, got {actual_hash}")
            return False
    
    def download_model(self, url: str, dest_path: str, display_name: str, expected_hash: Optional[str] = None) -> bool:
        """Download a model using the best available method"""
        # Create any necessary directories
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Check if file already exists and has correct hash
        if os.path.exists(dest_path):
            # If hash is provided, verify existing file
            if expected_hash:
                if self.verify_hash(dest_path, expected_hash):
                    logger.info(f"File already exists with correct hash: {display_name}. Skipping download.")
                    return True
                else:
                    logger.warning(f"Hash mismatch for existing file. Re-downloading {display_name}...")
            else:
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                logger.info(f"File already exists ({size_mb:.2f}MB): {display_name}. Skipping download.")
                return True
        
        # Choose download method
        if REQUESTS_AVAILABLE and self.session:
            success = self.download_with_requests(url, dest_path, display_name)
        else:
            success = self.download_with_urllib(url, dest_path, display_name)
        
        # Verify hash if provided and download succeeded
        if success and expected_hash and not self.verify_hash(dest_path, expected_hash):
            logger.warning(f"Hash verification failed for {display_name}. The download may be corrupted.")
            return False
        
        return success
    
    def process_model(self, model: Dict[str, Any], index: int, total: int) -> bool:
        """Process a single model download"""
        try:
            name = model["name"]
            model_type = model["type"]
            url = model["url"]
            expected_hash = model.get("hash")
            path_component = model.get("path", "")
            
            logger.info(f"[{index}/{total}] Processing {name}")
            
            # Determine destination path
            dest_dir = os.path.join(self.models_dir, model_type)
            if path_component:
                path_dir = os.path.dirname(path_component)
                if path_dir:
                    dest_dir = os.path.join(dest_dir, path_dir)
            
            dest_path = os.path.join(dest_dir, os.path.basename(path_component) if path_component else name)
            
            # Download the model
            return self.download_model(url, dest_path, name, expected_hash)
            
        except KeyError as e:
            logger.error(f"Error: Missing required field in model definition: {e}")
            return False
        except Exception as e:
            logger.error(f"Error processing model {index}: {e}")
            return False
    
    def download_models_from_config(self) -> bool:
        """Process model downloads from a config file"""
        if not self.config_path:
            logger.error("No config file specified")
            return False
        
        # Load config
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return False
        
        # Check for models
        if "external_models" not in config or not config["external_models"]:
            logger.info("No external models found in config")
            return True
        
        models = config["external_models"]
        logger.info(f"Found {len(models)} external models to download")
        
        # Track results
        results = []
        
        # Process models in parallel if requested
        if self.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for i, model in enumerate(models, 1):
                    futures.append(executor.submit(self.process_model, model, i, len(models)))
                
                # Collect results
                for future in futures:
                    results.append(future.result())
        else:
            # Process sequentially
            for i, model in enumerate(models, 1):
                result = self.process_model(model, i, len(models))
                results.append(result)
        
        # Print summary
        success_count = results.count(True)
        failure_count = len(results) - success_count
        
        logger.info("\nDownload summary:")
        logger.info(f"  Total models: {len(models)}")
        logger.info(f"  Successfully downloaded/found: {success_count}")
        logger.info(f"  Failed: {failure_count}")
        
        return failure_count == 0


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Optimized ComfyUI Model Downloader")
    parser.add_argument("--comfyui-dir", help="Path to ComfyUI directory", 
                        default=os.environ.get("COMFYUI_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parser.add_argument("--config", help="Path to config.json file", default=None)
    parser.add_argument("--parallel", type=int, help="Number of parallel downloads (default: 1)", default=1)
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimize output")
    args = parser.parse_args()
    
    # Configure logging based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Set ComfyUI dir and look for config
    comfyui_dir = args.comfyui_dir
    config_path = args.config
    
    # If config path not provided, look in standard locations
    if not config_path:
        locations = [
            os.path.join(comfyui_dir, "config.json"),
            os.path.join(comfyui_dir, "package_config.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        ]
        
        for loc in locations:
            if os.path.exists(loc):
                config_path = loc
                break
    
    if not config_path or not os.path.exists(config_path):
        logger.error("Error: Cannot find config.json file.")
        logger.error(f"Looked in: {', '.join(locations if 'locations' in locals() else ['--config argument'])}")
        return 1
    
    logger.info(f"Using ComfyUI directory: {comfyui_dir}")
    logger.info(f"Using config file: {config_path}")
    
    # Create downloader and run
    downloader = ModelDownloader(
        base_dir=comfyui_dir,
        config_path=config_path,
        max_workers=args.parallel
    )
    
    # Start downloads
    success = downloader.download_models_from_config()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
