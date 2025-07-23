"""
Embedding Cache Service for MIDAS
Optimized for Windows file system with intelligent embedding storage
"""

import numpy as np
import pickle
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import asyncio
import aiofiles
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.core.config import settings
from .cache_manager import cache_manager

@dataclass
class EmbeddingMetadata:
    """Metadata for cached embeddings"""
    model_name: str
    dimensions: int
    created_at: datetime
    content_hash: str
    file_size: int

class EmbeddingCache:
    """High-performance embedding cache optimized for Windows"""
    
    def __init__(self):
        self.cache_dir = settings.APPDATA_DIR / "embeddings"
        self.metadata_dir = self.cache_dir / "metadata"
        self.vector_dir = self.cache_dir / "vectors"
        self.index_file = self.cache_dir / "index.pkl"
        
        # Windows-specific optimization
        self._init_cache_structure()
        
        # In-memory index for fast lookups
        self._memory_index: Dict[str, EmbeddingMetadata] = {}
        self._load_index()
    
    def _init_cache_structure(self):
        """Initialize Windows-optimized cache directory structure"""
        directories = [
            self.cache_dir,
            self.metadata_dir,
            self.vector_dir,
        ]
        
        # Create subdirectories for hash distribution (better NTFS performance)
        for i in range(256):
            directories.extend([
                self.vector_dir / f"{i:02x}",
                self.metadata_dir / f"{i:02x}"
            ])
        
        for dir_path in directories:
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Windows-specific optimizations
            if hasattr(dir_path, 'chmod'):
                try:
                    # Set permissions for optimal access
                    dir_path.chmod(0o755)
                except:
                    pass
    
    def _get_content_hash(self, text: str) -> str:
        """Generate content hash for caching"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _get_embedding_paths(self, content_hash: str) -> Tuple[Path, Path]:
        """Get file paths for embedding storage"""
        # Use first two characters for directory distribution
        subdir = content_hash[:2]
        
        vector_path = self.vector_dir / subdir / f"{content_hash}.npy"
        metadata_path = self.metadata_dir / subdir / f"{content_hash}.meta"
        
        return vector_path, metadata_path
    
    async def _load_index(self):
        """Load the embedding index into memory"""
        if self.index_file.exists():
            try:
                async with aiofiles.open(self.index_file, 'rb') as f:
                    data = await f.read()
                    self._memory_index = pickle.loads(data)
                print(f"📚 Loaded {len(self._memory_index)} embeddings from cache index")
            except Exception as e:
                print(f"⚠️  Error loading embedding index: {e}")
                self._memory_index = {}
        else:
            # Build index from existing files
            await self._rebuild_index()
    
    async def _save_index(self):
        """Save the in-memory index to disk"""
        try:
            data = pickle.dumps(self._memory_index)
            async with aiofiles.open(self.index_file, 'wb') as f:
                await f.write(data)
        except Exception as e:
            print(f"⚠️  Error saving embedding index: {e}")
    
    async def _rebuild_index(self):
        """Rebuild index from existing cache files"""
        print("🔄 Rebuilding embedding cache index...")
        self._memory_index = {}
        
        # Scan all metadata files
        for metadata_file in self.metadata_dir.rglob("*.meta"):
            try:
                async with aiofiles.open(metadata_file, 'rb') as f:
                    data = await f.read()
                    metadata = pickle.loads(data)
                    
                content_hash = metadata_file.stem
                self._memory_index[content_hash] = metadata
                
            except Exception as e:
                print(f"⚠️  Error reading metadata file {metadata_file}: {e}")
        
        await self._save_index()
        print(f"✅ Rebuilt embedding index with {len(self._memory_index)} entries")
    
    async def get_embedding(
        self, 
        text: str, 
        model_name: str
    ) -> Optional[np.ndarray]:
        """Get cached embedding for text"""
        content_hash = self._get_content_hash(text)
        
        # Check in-memory index first
        metadata = self._memory_index.get(content_hash)
        if not metadata or metadata.model_name != model_name:
            return None
        
        vector_path, _ = self._get_embedding_paths(content_hash)
        
        try:
            if vector_path.exists():
                # Load numpy array efficiently
                async with aiofiles.open(vector_path, 'rb') as f:
                    data = await f.read()
                    embedding = np.frombuffer(data, dtype=np.float32)
                    return embedding.reshape(-1, metadata.dimensions) if len(embedding.shape) == 1 else embedding
        except Exception as e:
            print(f"⚠️  Error loading embedding {content_hash}: {e}")
            # Remove corrupted entry from index
            self._memory_index.pop(content_hash, None)
        
        return None
    
    async def store_embedding(
        self, 
        text: str, 
        embedding: np.ndarray, 
        model_name: str
    ) -> bool:
        """Store embedding in cache"""
        content_hash = self._get_content_hash(text)
        vector_path, metadata_path = self._get_embedding_paths(content_hash)
        
        try:
            # Ensure parent directories exist
            vector_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Store vector as binary numpy array
            embedding_bytes = embedding.astype(np.float32).tobytes()
            async with aiofiles.open(vector_path, 'wb') as f:
                await f.write(embedding_bytes)
            
            # Store metadata
            metadata = EmbeddingMetadata(
                model_name=model_name,
                dimensions=embedding.shape[-1],
                created_at=datetime.now(),
                content_hash=content_hash,
                file_size=len(embedding_bytes)
            )
            
            metadata_bytes = pickle.dumps(metadata)
            async with aiofiles.open(metadata_path, 'wb') as f:
                await f.write(metadata_bytes)
            
            # Update in-memory index
            self._memory_index[content_hash] = metadata
            
            # Periodically save index (every 100 entries)
            if len(self._memory_index) % 100 == 0:
                await self._save_index()
            
            return True
            
        except Exception as e:
            print(f"⚠️  Error storing embedding {content_hash}: {e}")
            return False
    
    async def batch_get_embeddings(
        self, 
        texts: List[str], 
        model_name: str
    ) -> Dict[str, Optional[np.ndarray]]:
        """Get multiple embeddings in batch for better performance"""
        results = {}
        
        # Parallel loading for better I/O performance on Windows
        tasks = []
        for text in texts:
            task = asyncio.create_task(self.get_embedding(text, model_name))
            tasks.append((text, task))
        
        # Wait for all tasks
        for text, task in tasks:
            results[text] = await task
        
        return results
    
    async def batch_store_embeddings(
        self,
        text_embedding_pairs: List[Tuple[str, np.ndarray]],
        model_name: str
    ) -> List[bool]:
        """Store multiple embeddings in batch"""
        tasks = []
        for text, embedding in text_embedding_pairs:
            task = asyncio.create_task(self.store_embedding(text, embedding, model_name))
            tasks.append(task)
        
        return await asyncio.gather(*tasks)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get embedding cache statistics"""
        stats = {
            "total_embeddings": len(self._memory_index),
            "models": {},
            "storage": {
                "total_size_mb": 0,
                "vector_files": 0,
                "metadata_files": 0
            },
            "performance": {
                "hit_rate": 0.0,
                "avg_file_size": 0
            }
        }
        
        # Analyze models and sizes
        total_size = 0
        model_counts = {}
        
        for content_hash, metadata in self._memory_index.items():
            model_counts[metadata.model_name] = model_counts.get(metadata.model_name, 0) + 1
            total_size += metadata.file_size
        
        stats["models"] = model_counts
        stats["storage"]["total_size_mb"] = total_size / (1024 * 1024)
        stats["performance"]["avg_file_size"] = total_size / len(self._memory_index) if self._memory_index else 0
        
        # Count actual files
        stats["storage"]["vector_files"] = len(list(self.vector_dir.rglob("*.npy")))
        stats["storage"]["metadata_files"] = len(list(self.metadata_dir.rglob("*.meta")))
        
        return stats
    
    async def cleanup_expired(self, max_age_days: int = 30) -> int:
        """Clean up old embedding cache entries"""
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        cleaned_count = 0
        
        expired_hashes = []
        for content_hash, metadata in self._memory_index.items():
            if metadata.created_at < cutoff_time:
                expired_hashes.append(content_hash)
        
        for content_hash in expired_hashes:
            vector_path, metadata_path = self._get_embedding_paths(content_hash)
            
            try:
                if vector_path.exists():
                    vector_path.unlink()
                if metadata_path.exists():
                    metadata_path.unlink()
                
                self._memory_index.pop(content_hash, None)
                cleaned_count += 1
                
            except Exception as e:
                print(f"⚠️  Error cleaning up {content_hash}: {e}")
        
        if cleaned_count > 0:
            await self._save_index()
        
        return cleaned_count
    
    async def optimize_for_windows(self):
        """Apply Windows-specific optimizations"""
        if hasattr(self, '_windows_optimized'):
            return
        
        try:
            # Defragment cache directory (Windows only)
            if hasattr(__import__('os'), 'system'):
                import subprocess
                
                # Run disk defragmentation on cache directory
                cache_drive = str(self.cache_dir).split(':')[0] + ':'
                subprocess.run([
                    'defrag', cache_drive, '/A'
                ], capture_output=True, text=True)
            
            self._windows_optimized = True
            
        except Exception as e:
            print(f"⚠️  Windows optimization error: {e}")

# Global embedding cache instance
embedding_cache = EmbeddingCache()