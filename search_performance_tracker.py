"""
MIDAS Search Performance Tracker
Tracks and analyzes search performance metrics for Qdrant and document indexing
"""

import time
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import statistics
import pandas as pd
from contextlib import contextmanager

# Create database directory
db_dir = Path(__file__).parent / 'data' / 'metrics'
db_dir.mkdir(parents=True, exist_ok=True)

@dataclass
class SearchMetric:
    """Data class for search metrics"""
    timestamp: str
    query: str
    collection: str
    num_results: int
    search_time_ms: float
    vector_search_time_ms: float
    post_processing_time_ms: float
    total_documents_searched: int
    filter_conditions: Dict[str, Any]
    error: Optional[str] = None

@dataclass
class IndexingMetric:
    """Data class for indexing metrics"""
    timestamp: str
    document_path: str
    document_type: str
    file_size_bytes: int
    chunks_created: int
    vectors_created: int
    indexing_time_ms: float
    embedding_time_ms: float
    storage_time_ms: float
    error: Optional[str] = None

class PerformanceDatabase:
    """SQLite database for performance metrics"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or db_dir / 'search_performance.db'
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            # Search metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    query TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    num_results INTEGER,
                    search_time_ms REAL,
                    vector_search_time_ms REAL,
                    post_processing_time_ms REAL,
                    total_documents_searched INTEGER,
                    filter_conditions TEXT,
                    error TEXT
                )
            """)
            
            # Indexing metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexing_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    document_path TEXT NOT NULL,
                    document_type TEXT,
                    file_size_bytes INTEGER,
                    chunks_created INTEGER,
                    vectors_created INTEGER,
                    indexing_time_ms REAL,
                    embedding_time_ms REAL,
                    storage_time_ms REAL,
                    error TEXT
                )
            """)
            
            # Create indices
            conn.execute("CREATE INDEX IF NOT EXISTS idx_search_timestamp ON search_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_search_collection ON search_metrics(collection)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_indexing_timestamp ON indexing_metrics(timestamp)")
            
            conn.commit()
    
    def record_search(self, metric: SearchMetric):
        """Record a search metric"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO search_metrics (
                    timestamp, query, collection, num_results,
                    search_time_ms, vector_search_time_ms, post_processing_time_ms,
                    total_documents_searched, filter_conditions, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.timestamp, metric.query, metric.collection,
                metric.num_results, metric.search_time_ms,
                metric.vector_search_time_ms, metric.post_processing_time_ms,
                metric.total_documents_searched,
                json.dumps(metric.filter_conditions),
                metric.error
            ))
            conn.commit()
    
    def record_indexing(self, metric: IndexingMetric):
        """Record an indexing metric"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO indexing_metrics (
                    timestamp, document_path, document_type, file_size_bytes,
                    chunks_created, vectors_created, indexing_time_ms,
                    embedding_time_ms, storage_time_ms, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.timestamp, metric.document_path, metric.document_type,
                metric.file_size_bytes, metric.chunks_created, metric.vectors_created,
                metric.indexing_time_ms, metric.embedding_time_ms, metric.storage_time_ms,
                metric.error
            ))
            conn.commit()
    
    def get_search_metrics(self, hours: int = 24) -> pd.DataFrame:
        """Get search metrics for the specified time period"""
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query("""
                SELECT * FROM search_metrics
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            """, conn, params=(cutoff_time,))
        
        return df
    
    def get_indexing_metrics(self, hours: int = 24) -> pd.DataFrame:
        """Get indexing metrics for the specified time period"""
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query("""
                SELECT * FROM indexing_metrics
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            """, conn, params=(cutoff_time,))
        
        return df

class SearchPerformanceTracker:
    """Main performance tracking class"""
    
    def __init__(self):
        self.db = PerformanceDatabase()
        self._current_search_start = None
        self._current_indexing_start = None
        self._search_stages = {}
        self._indexing_stages = {}
    
    @contextmanager
    def track_search(self, query: str, collection: str, filters: Dict[str, Any] = None):
        """Context manager to track search performance"""
        self._current_search_start = time.time()
        self._search_stages = {
            'vector_search': 0,
            'post_processing': 0
        }
        
        metric = SearchMetric(
            timestamp=datetime.now().isoformat(),
            query=query,
            collection=collection,
            num_results=0,
            search_time_ms=0,
            vector_search_time_ms=0,
            post_processing_time_ms=0,
            total_documents_searched=0,
            filter_conditions=filters or {}
        )
        
        try:
            yield metric
            
            # Calculate total time
            total_time = (time.time() - self._current_search_start) * 1000
            metric.search_time_ms = total_time
            metric.vector_search_time_ms = self._search_stages.get('vector_search', 0)
            metric.post_processing_time_ms = self._search_stages.get('post_processing', 0)
            
            # Record metric
            self.db.record_search(metric)
            
        except Exception as e:
            metric.error = str(e)
            metric.search_time_ms = (time.time() - self._current_search_start) * 1000
            self.db.record_search(metric)
            raise
    
    def mark_search_stage(self, stage: str):
        """Mark the completion of a search stage"""
        if self._current_search_start and stage not in self._search_stages:
            self._search_stages[stage] = (time.time() - self._current_search_start) * 1000
    
    @contextmanager
    def track_indexing(self, document_path: str, document_type: str, file_size: int):
        """Context manager to track indexing performance"""
        self._current_indexing_start = time.time()
        self._indexing_stages = {
            'embedding': 0,
            'storage': 0
        }
        
        metric = IndexingMetric(
            timestamp=datetime.now().isoformat(),
            document_path=document_path,
            document_type=document_type,
            file_size_bytes=file_size,
            chunks_created=0,
            vectors_created=0,
            indexing_time_ms=0,
            embedding_time_ms=0,
            storage_time_ms=0
        )
        
        try:
            yield metric
            
            # Calculate total time
            total_time = (time.time() - self._current_indexing_start) * 1000
            metric.indexing_time_ms = total_time
            metric.embedding_time_ms = self._indexing_stages.get('embedding', 0)
            metric.storage_time_ms = self._indexing_stages.get('storage', 0)
            
            # Record metric
            self.db.record_indexing(metric)
            
        except Exception as e:
            metric.error = str(e)
            metric.indexing_time_ms = (time.time() - self._current_indexing_start) * 1000
            self.db.record_indexing(metric)
            raise
    
    def mark_indexing_stage(self, stage: str):
        """Mark the completion of an indexing stage"""
        if self._current_indexing_start and stage not in self._indexing_stages:
            self._indexing_stages[stage] = (time.time() - self._current_indexing_start) * 1000
    
    def get_search_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get search performance summary"""
        df = self.db.get_search_metrics(hours)
        
        if df.empty:
            return {}
        
        # Filter successful searches
        successful = df[df['error'].isna()]
        
        summary = {
            'total_searches': len(df),
            'successful_searches': len(successful),
            'failed_searches': len(df) - len(successful),
            'collections': df['collection'].unique().tolist(),
            'time_period_hours': hours
        }
        
        if not successful.empty:
            summary.update({
                'avg_search_time_ms': successful['search_time_ms'].mean(),
                'median_search_time_ms': successful['search_time_ms'].median(),
                'p95_search_time_ms': successful['search_time_ms'].quantile(0.95),
                'avg_results_returned': successful['num_results'].mean(),
                'avg_vector_search_time_ms': successful['vector_search_time_ms'].mean(),
                'avg_post_processing_time_ms': successful['post_processing_time_ms'].mean()
            })
            
            # Performance by collection
            collection_stats = []
            for collection in successful['collection'].unique():
                coll_data = successful[successful['collection'] == collection]
                collection_stats.append({
                    'collection': collection,
                    'searches': len(coll_data),
                    'avg_time_ms': coll_data['search_time_ms'].mean(),
                    'p95_time_ms': coll_data['search_time_ms'].quantile(0.95)
                })
            
            summary['collection_performance'] = collection_stats
        
        return summary
    
    def get_indexing_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get indexing performance summary"""
        df = self.db.get_indexing_metrics(hours)
        
        if df.empty:
            return {}
        
        # Filter successful indexing
        successful = df[df['error'].isna()]
        
        summary = {
            'total_documents': len(df),
            'successful_documents': len(successful),
            'failed_documents': len(df) - len(successful),
            'time_period_hours': hours
        }
        
        if not successful.empty:
            summary.update({
                'total_chunks_created': successful['chunks_created'].sum(),
                'total_vectors_created': successful['vectors_created'].sum(),
                'avg_indexing_time_ms': successful['indexing_time_ms'].mean(),
                'avg_chunks_per_doc': successful['chunks_created'].mean(),
                'avg_embedding_time_ms': successful['embedding_time_ms'].mean(),
                'avg_storage_time_ms': successful['storage_time_ms'].mean(),
                'total_bytes_processed': successful['file_size_bytes'].sum(),
                'indexing_throughput_mb_per_sec': (
                    successful['file_size_bytes'].sum() / (1024 * 1024) /
                    (successful['indexing_time_ms'].sum() / 1000)
                    if successful['indexing_time_ms'].sum() > 0 else 0
                )
            })
            
            # Performance by document type
            type_stats = []
            for doc_type in successful['document_type'].unique():
                type_data = successful[successful['document_type'] == doc_type]
                type_stats.append({
                    'document_type': doc_type,
                    'count': len(type_data),
                    'avg_time_ms': type_data['indexing_time_ms'].mean(),
                    'avg_size_bytes': type_data['file_size_bytes'].mean()
                })
            
            summary['document_type_performance'] = type_stats
        
        return summary
    
    def get_performance_trends(self, metric_type: str = 'search', 
                             hours: int = 24, interval: str = 'hour') -> pd.DataFrame:
        """Get performance trends over time"""
        if metric_type == 'search':
            df = self.db.get_search_metrics(hours)
            time_column = 'search_time_ms'
        else:
            df = self.db.get_indexing_metrics(hours)
            time_column = 'indexing_time_ms'
        
        if df.empty:
            return pd.DataFrame()
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        # Resample by interval
        if interval == 'hour':
            freq = 'H'
        elif interval == 'minute':
            freq = 'T'
        else:
            freq = 'D'
        
        # Calculate aggregates
        trends = df.resample(freq).agg({
            time_column: ['mean', 'median', 'count', 'std'],
            'error': lambda x: (x.notna()).sum()  # Count of errors
        })
        
        # Flatten column names
        trends.columns = ['_'.join(col).strip() for col in trends.columns.values]
        
        return trends
    
    def export_metrics(self, output_path: Path, format: str = 'csv', hours: int = 168):
        """Export metrics to file"""
        search_df = self.db.get_search_metrics(hours)
        indexing_df = self.db.get_indexing_metrics(hours)
        
        if format == 'csv':
            search_df.to_csv(output_path / 'search_metrics.csv', index=False)
            indexing_df.to_csv(output_path / 'indexing_metrics.csv', index=False)
        
        elif format == 'excel':
            with pd.ExcelWriter(output_path / 'performance_metrics.xlsx') as writer:
                search_df.to_excel(writer, sheet_name='Search Metrics', index=False)
                indexing_df.to_excel(writer, sheet_name='Indexing Metrics', index=False)
                
                # Add summary sheets
                search_summary = pd.DataFrame([self.get_search_performance_summary(hours)])
                search_summary.to_excel(writer, sheet_name='Search Summary', index=False)
                
                indexing_summary = pd.DataFrame([self.get_indexing_performance_summary(hours)])
                indexing_summary.to_excel(writer, sheet_name='Indexing Summary', index=False)

# Global tracker instance
performance_tracker = SearchPerformanceTracker()

# Example usage functions
def track_qdrant_search(query: str, collection: str = "documents"):
    """Example function to track Qdrant search"""
    with performance_tracker.track_search(query, collection) as metric:
        # Simulate vector search
        time.sleep(0.05)  # 50ms vector search
        performance_tracker.mark_search_stage('vector_search')
        
        # Set results
        metric.num_results = 10
        metric.total_documents_searched = 1000
        
        # Simulate post-processing
        time.sleep(0.02)  # 20ms post-processing
        performance_tracker.mark_search_stage('post_processing')

def track_document_indexing(doc_path: str, doc_type: str, file_size: int):
    """Example function to track document indexing"""
    with performance_tracker.track_indexing(doc_path, doc_type, file_size) as metric:
        # Simulate chunking
        metric.chunks_created = 10
        
        # Simulate embedding
        time.sleep(0.1)  # 100ms embedding
        performance_tracker.mark_indexing_stage('embedding')
        metric.vectors_created = 10
        
        # Simulate storage
        time.sleep(0.03)  # 30ms storage
        performance_tracker.mark_indexing_stage('storage')