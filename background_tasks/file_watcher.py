"""
File Watching System for MIDAS
Monitors document directories and triggers background processing
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, List, Optional
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from celery import group

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
from celery_config import app
from background_tasks.document_tasks import process_document_file, extract_document_metadata

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    '.pdf', '.docx', '.doc', '.txt', '.rtf', '.odt',
    '.csv', '.xlsx', '.xls', '.json', '.xml', '.html',
    '.md', '.log', '.msg', '.eml'
}

# Default directories to watch
DEFAULT_WATCH_DIRS = [
    Path.home() / 'Documents' / 'MIDAS_Uploads',
    Path.home() / 'Downloads',
    Path.home() / 'Desktop',
]

class DocumentEventHandler(FileSystemEventHandler):
    """
    Handles file system events for document processing
    """
    
    def __init__(self, process_immediately: bool = True, 
                 batch_size: int = 10, batch_timeout: int = 60):
        """
        Initialize the event handler
        
        Args:
            process_immediately: Process files immediately or batch them
            batch_size: Maximum batch size before processing
            batch_timeout: Maximum time to wait before processing batch (seconds)
        """
        super().__init__()
        self.process_immediately = process_immediately
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_files: List[str] = []
        self.last_batch_time = time.time()
        self.processed_files: Set[str] = set()
        self.processing_lock = False
        
        # Load processed files history
        self._load_history()
    
    def _load_history(self):
        """Load previously processed files from history"""
        history_file = Path(__file__).parent / 'data' / 'processed_files.json'
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    data = json.load(f)
                    self.processed_files = set(data.get('processed_files', []))
                    logger.info(f"Loaded {len(self.processed_files)} processed files from history")
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Save processed files to history"""
        history_file = Path(__file__).parent / 'data' / 'processed_files.json'
        history_file.parent.mkdir(exist_ok=True)
        
        try:
            # Keep only last 10000 entries to prevent unbounded growth
            recent_files = list(self.processed_files)[-10000:]
            with open(history_file, 'w') as f:
                json.dump({
                    'processed_files': recent_files,
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def _is_supported_file(self, file_path: str) -> bool:
        """Check if file has supported extension"""
        path = Path(file_path)
        return (
            path.suffix.lower() in SUPPORTED_EXTENSIONS and
            path.exists() and
            path.is_file() and
            not path.name.startswith('~')  # Ignore temporary files
        )
    
    def _should_process_file(self, file_path: str) -> bool:
        """Check if file should be processed"""
        if not self._is_supported_file(file_path):
            return False
        
        # Check if already processed
        file_hash = self._get_file_identifier(file_path)
        if file_hash in self.processed_files:
            logger.debug(f"File already processed: {file_path}")
            return False
        
        # Check file size
        file_size = Path(file_path).stat().st_size
        if file_size == 0:
            logger.warning(f"Skipping empty file: {file_path}")
            return False
        
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            logger.warning(f"File too large ({file_size} bytes): {file_path}")
            return False
        
        return True
    
    def _get_file_identifier(self, file_path: str) -> str:
        """Get unique identifier for file"""
        path = Path(file_path)
        stat = path.stat()
        return f"{path.name}_{stat.st_size}_{stat.st_mtime}"
    
    def on_created(self, event):
        """Handle file creation events"""
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            self._handle_file_event(event.src_path, "created")
    
    def on_modified(self, event):
        """Handle file modification events"""
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            # Wait a bit to ensure file write is complete
            time.sleep(0.5)
            self._handle_file_event(event.src_path, "modified")
    
    def _handle_file_event(self, file_path: str, event_type: str):
        """Handle a file event"""
        logger.info(f"File {event_type}: {file_path}")
        
        if not self._should_process_file(file_path):
            return
        
        if self.process_immediately:
            self._process_file_now(file_path)
        else:
            self._add_to_batch(file_path)
    
    def _process_file_now(self, file_path: str):
        """Process file immediately"""
        try:
            # Extract metadata first
            metadata_task = extract_document_metadata.delay(file_path)
            logger.info(f"Metadata extraction queued for {file_path}")
            
            # Queue main processing task
            process_task = process_document_file.delay(
                file_path,
                options={'source': 'file_watcher'}
            )
            logger.info(f"Processing queued for {file_path} - Task ID: {process_task.id}")
            
            # Mark as processed
            file_hash = self._get_file_identifier(file_path)
            self.processed_files.add(file_hash)
            self._save_history()
            
        except Exception as e:
            logger.error(f"Failed to queue processing for {file_path}: {e}")
    
    def _add_to_batch(self, file_path: str):
        """Add file to batch for processing"""
        self.pending_files.append(file_path)
        logger.info(f"Added to batch: {file_path} (batch size: {len(self.pending_files)})")
        
        # Check if batch should be processed
        if (len(self.pending_files) >= self.batch_size or
            time.time() - self.last_batch_time > self.batch_timeout):
            self._process_batch()
    
    def _process_batch(self):
        """Process pending batch of files"""
        if not self.pending_files or self.processing_lock:
            return
        
        self.processing_lock = True
        try:
            batch_files = self.pending_files.copy()
            self.pending_files.clear()
            self.last_batch_time = time.time()
            
            logger.info(f"Processing batch of {len(batch_files)} files")
            
            # Create group of tasks
            job = group(
                process_document_file.s(
                    file_path,
                    options={'source': 'file_watcher', 'batch': True}
                )
                for file_path in batch_files
                if self._should_process_file(file_path)
            )
            
            # Execute group
            result = job.apply_async()
            logger.info(f"Batch processing queued - Group ID: {result.id}")
            
            # Mark files as processed
            for file_path in batch_files:
                file_hash = self._get_file_identifier(file_path)
                self.processed_files.add(file_hash)
            
            self._save_history()
            
        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
        finally:
            self.processing_lock = False
    
    def check_pending(self):
        """Check if there are pending files to process"""
        if self.pending_files and not self.process_immediately:
            if time.time() - self.last_batch_time > self.batch_timeout:
                self._process_batch()

class FileWatcher:
    """
    Main file watcher class that manages observers
    """
    
    def __init__(self, directories: List[Path] = None, 
                 recursive: bool = True,
                 process_immediately: bool = True):
        """
        Initialize file watcher
        
        Args:
            directories: List of directories to watch
            recursive: Watch directories recursively
            process_immediately: Process files immediately or batch them
        """
        self.directories = directories or DEFAULT_WATCH_DIRS
        self.recursive = recursive
        self.observer = Observer()
        self.event_handler = DocumentEventHandler(
            process_immediately=process_immediately
        )
        self.running = False
        
        # Ensure directories exist
        for directory in self.directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def start(self):
        """Start watching directories"""
        logger.info("Starting file watcher...")
        
        for directory in self.directories:
            if directory.exists():
                self.observer.schedule(
                    self.event_handler,
                    str(directory),
                    recursive=self.recursive
                )
                logger.info(f"Watching directory: {directory}")
            else:
                logger.warning(f"Directory not found: {directory}")
        
        self.observer.start()
        self.running = True
        logger.info("File watcher started successfully")
    
    def stop(self):
        """Stop watching directories"""
        logger.info("Stopping file watcher...")
        self.running = False
        self.observer.stop()
        self.observer.join()
        logger.info("File watcher stopped")
    
    def run_forever(self):
        """Run the watcher forever"""
        try:
            self.start()
            
            while self.running:
                time.sleep(5)
                # Check for pending batch processing
                self.event_handler.check_pending()
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()

@app.task(name='tasks.monitoring.check_document_folder')
def check_document_folder():
    """
    Periodic task to check for new documents
    Called by Celery beat scheduler
    """
    logger.info("Running periodic document folder check")
    
    results = {
        'checked_dirs': [],
        'new_files': 0,
        'queued_files': 0,
        'errors': []
    }
    
    for directory in DEFAULT_WATCH_DIRS:
        if not directory.exists():
            continue
        
        results['checked_dirs'].append(str(directory))
        
        try:
            # Get list of files modified in last hour
            cutoff_time = time.time() - 3600
            
            for file_path in directory.rglob('*'):
                if (file_path.is_file() and 
                    file_path.suffix.lower() in SUPPORTED_EXTENSIONS and
                    file_path.stat().st_mtime > cutoff_time):
                    
                    results['new_files'] += 1
                    
                    # Queue for processing if not already processed
                    # (In production, would check against database)
                    try:
                        process_document_file.delay(
                            str(file_path),
                            options={'source': 'periodic_check'}
                        )
                        results['queued_files'] += 1
                    except Exception as e:
                        results['errors'].append(f"{file_path}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error checking directory {directory}: {e}")
            results['errors'].append(f"{directory}: {str(e)}")
    
    logger.info(f"Folder check complete: {results['queued_files']} files queued")
    return results

def main():
    """Main entry point for file watcher"""
    import argparse
    
    parser = argparse.ArgumentParser(description='MIDAS File Watcher')
    parser.add_argument(
        '--directories', '-d',
        nargs='+',
        help='Directories to watch (space-separated)'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Batch process files instead of immediate processing'
    )
    parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Do not watch directories recursively'
    )
    
    args = parser.parse_args()
    
    # Parse directories
    directories = None
    if args.directories:
        directories = [Path(d) for d in args.directories]
    
    # Create and run watcher
    watcher = FileWatcher(
        directories=directories,
        recursive=not args.no_recursive,
        process_immediately=not args.batch
    )
    
    try:
        watcher.run_forever()
    except Exception as e:
        logger.error(f"File watcher error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()