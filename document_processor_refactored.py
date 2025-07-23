"""
Document Processor Service - Production Grade
Handles parsing, chunking, and metadata extraction for multiple file formats with enterprise security.
"""

import os
import hashlib
import mimetypes
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union, Callable
from datetime import datetime, timedelta
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from contextlib import contextmanager
from dataclasses import dataclass
import json
import re
from collections import Counter, defaultdict

# Try importing optional libraries
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Enterprise-grade document processing service with comprehensive security and reliability.
    
    Features:
    - Multi-format document parsing with fallback mechanisms
    - Robust error handling and retry logic
    - Security-focused file validation
    - Intelligent chunking strategies
    - Concurrent processing support
    """
    
    def __init__(self, 
                 chunk_size: int = 500,
                 chunk_overlap: int = 50,
                 max_file_size_mb: int = 100,
                 allowed_extensions: Optional[List[str]] = None,
                 max_workers: int = 4):
        """
        Initialize Document Processor.
        
        Args:
            chunk_size: Target size for text chunks (in tokens/words)
            chunk_overlap: Overlap between chunks for context preservation
            max_file_size_mb: Maximum allowed file size in MB
            allowed_extensions: List of allowed file extensions
            max_workers: Maximum concurrent processing workers
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_size_mb = max_file_size_mb
        self.max_workers = max_workers
        
        # Default allowed extensions
        self.allowed_extensions = allowed_extensions or [
            '.txt', '.pdf', '.docx', '.doc', '.csv', '.json', '.md', '.markdown',
            '.html', '.htm', '.xml', '.rtf', '.odt', '.xlsx', '.xls'
        ]
        
        # Initialize thread pool
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Processing statistics
        self.stats = {
            'processed_files': 0,
            'failed_files': 0,
            'total_chunks': 0,
            'processing_time': 0
        }
        
        # Lock for thread-safe operations
        self._lock = threading.Lock()
    
    def process_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Process a single file with comprehensive error handling.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            Dictionary containing processed data and metadata
        """
        file_path = Path(file_path)
        start_time = time.time()
        
        try:
            # Validate file
            self._validate_file(file_path)
            
            # Extract metadata
            metadata = self._extract_metadata(file_path)
            
            # Parse content
            content = self._parse_file(file_path, metadata)
            
            # Create chunks
            chunks = self._create_chunks(content, metadata)
            
            # Update statistics
            with self._lock:
                self.stats['processed_files'] += 1
                self.stats['total_chunks'] += len(chunks)
                self.stats['processing_time'] += time.time() - start_time
            
            return {
                'status': 'success',
                'file_path': str(file_path),
                'metadata': metadata,
                'content': content,
                'chunks': chunks,
                'processing_time': time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            with self._lock:
                self.stats['failed_files'] += 1
            
            return {
                'status': 'error',
                'file_path': str(file_path),
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    def _validate_file(self, file_path: Path) -> None:
        """Validate file for processing."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")
        
        # Check file size
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_file_size_mb:
            raise ValueError(f"File too large: {file_size_mb:.1f}MB (max: {self.max_file_size_mb}MB)")
        
        # Check extension
        if file_path.suffix.lower() not in self.allowed_extensions:
            raise ValueError(f"File type not allowed: {file_path.suffix}")
    
    def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract comprehensive file metadata."""
        stat = file_path.stat()
        
        metadata = {
            'filename': file_path.name,
            'file_size': stat.st_size,
            'file_extension': file_path.suffix.lower(),
            'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'mime_type': mimetypes.guess_type(str(file_path))[0] or 'unknown'
        }
        
        # Try to get more accurate MIME type with python-magic
        if MAGIC_AVAILABLE:
            try:
                mime = magic.Magic(mime=True)
                metadata['mime_type'] = mime.from_file(str(file_path))
            except Exception as e:
                logger.warning(f"Could not determine MIME type with magic: {e}")
        
        return metadata
    
    def _parse_file(self, file_path: Path, metadata: Dict[str, Any]) -> str:
        """Parse file content based on type."""
        file_ext = metadata['file_extension']
        
        if file_ext in ['.txt', '.md', '.markdown']:
            return self._parse_text_file(file_path)
        elif file_ext == '.pdf':
            return self._parse_pdf_file(file_path)
        elif file_ext in ['.docx', '.doc']:
            return self._parse_docx_file(file_path)
        elif file_ext == '.csv':
            return self._parse_csv_file(file_path)
        elif file_ext == '.json':
            return self._parse_json_file(file_path)
        else:
            # Try to parse as text
            return self._parse_text_file(file_path)
    
    def _parse_text_file(self, file_path: Path) -> str:
        """Parse text file with encoding detection."""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        # Fallback with error handling
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    
    def _parse_pdf_file(self, file_path: Path) -> str:
        """Parse PDF file."""
        if not PDF_AVAILABLE:
            raise ValueError("PDF processing not available. Install PyPDF2.")
        
        text_content = []
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        text = page.extract_text()
                        if text.strip():
                            text_content.append(f"[Page {page_num + 1}]\n{text}")
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num + 1}: {e}")
                        continue
            
            return "\n\n".join(text_content) if text_content else "No text content extracted from PDF"
            
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            raise
    
    def _parse_docx_file(self, file_path: Path) -> str:
        """Parse DOCX file."""
        if not DOCX_AVAILABLE:
            raise ValueError("DOCX processing not available. Install python-docx.")
        
        try:
            doc = DocxDocument(str(file_path))
            text_content = []
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_content.append(paragraph.text)
            
            return "\n\n".join(text_content)
            
        except Exception as e:
            logger.error(f"Error parsing DOCX: {e}")
            raise
    
    def _parse_csv_file(self, file_path: Path) -> str:
        """Parse CSV file."""
        if PANDAS_AVAILABLE:
            try:
                df = pd.read_csv(file_path)
                # Convert to readable format
                text_parts = []
                text_parts.append(f"CSV File: {len(df)} rows, {len(df.columns)} columns")
                text_parts.append(f"Columns: {', '.join(df.columns)}")
                text_parts.append("\nData Preview:")
                
                # Add sample rows
                for idx, row in df.head(10).iterrows():
                    row_text = " | ".join([f"{col}: {val}" for col, val in row.items()])
                    text_parts.append(f"Row {idx + 1}: {row_text}")
                
                return "\n".join(text_parts)
            except Exception as e:
                logger.warning(f"Pandas CSV parsing failed: {e}")
        
        # Fallback to basic CSV parsing
        import csv
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            if not rows:
                return "Empty CSV file"
            
            text_parts = [f"CSV File with {len(rows)} rows"]
            text_parts.extend([" | ".join(row) for row in rows[:10]])
            
            return "\n".join(text_parts)
    
    def _parse_json_file(self, file_path: Path) -> str:
        """Parse JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert to readable format
            return json.dumps(data, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Error parsing JSON: {e}")
            raise
    
    def _create_chunks(self, content: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create text chunks with metadata."""
        if not content.strip():
            return []
        
        chunks = []
        words = content.split()
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            chunk = {
                'text': chunk_text,
                'chunk_index': len(chunks),
                'start_word': i,
                'end_word': i + len(chunk_words),
                'metadata': metadata
            }
            
            chunks.append(chunk)
        
        return chunks
    
    def process_batch(self, file_paths: List[Union[str, Path]], 
                     progress_callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """
        Process multiple files concurrently.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of processing results
        """
        results = []
        futures = []
        
        # Submit all files for processing
        for file_path in file_paths:
            future = self.executor.submit(self.process_file, file_path)
            futures.append((future, file_path))
        
        # Collect results
        for i, (future, file_path) in enumerate(futures):
            try:
                result = future.result(timeout=300)  # 5 minute timeout
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(file_paths), str(file_path))
                    
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                results.append({
                    'status': 'error',
                    'file_path': str(file_path),
                    'error': str(e)
                })
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        with self._lock:
            return self.stats.copy()
    
    def cleanup(self):
        """Cleanup resources."""
        self.executor.shutdown(wait=True)