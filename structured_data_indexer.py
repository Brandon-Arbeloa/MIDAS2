"""
Structured Data Indexing System for MIDAS RAG - Windows 11 Optimized
Extends document indexing to handle CSV/Excel with preserved relationships
Includes incremental indexing and file monitoring for Windows
"""

import os
import json
import hashlib
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone
import time
import threading
from dataclasses import dataclass, asdict

# Core libraries
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue

# File monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

# Excel support
try:
    import openpyxl
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# Import base classes
from document_indexer import WindowsLogger, WindowsFileHandler


@dataclass
class FileIndexRecord:
    """Record tracking indexed file status"""
    file_path: str
    file_hash: str
    last_modified: datetime
    last_indexed: datetime
    chunk_count: int
    index_status: str  # 'indexed', 'failed', 'pending'
    collection_name: str
    metadata: Dict[str, Any]


class IndexTracker:
    """Track indexed files and their status using SQLite for Windows compatibility"""
    
    def __init__(self, db_path: str = "C:\\MIDAS\\data\\index_tracker.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = WindowsLogger(name="index_tracker")
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for tracking"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS indexed_files (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    last_modified TEXT NOT NULL,
                    last_indexed TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    index_status TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    metadata TEXT
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_last_modified 
                ON indexed_files(last_modified)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_status 
                ON indexed_files(index_status)
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Index tracker database initialized: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """Calculate MD5 hash of file content"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating hash for {file_path}: {e}")
            return None
    
    def needs_indexing(self, file_path: Path) -> Tuple[bool, Optional[FileIndexRecord]]:
        """Check if file needs indexing based on modification time and hash"""
        try:
            file_stat = file_path.stat()
            file_modified = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM indexed_files WHERE file_path = ?",
                (str(file_path),)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                # File never indexed
                return True, None
            
            # Parse existing record
            record = FileIndexRecord(
                file_path=row[0],
                file_hash=row[1],
                last_modified=datetime.fromisoformat(row[2]),
                last_indexed=datetime.fromisoformat(row[3]),
                chunk_count=row[4],
                index_status=row[5],
                collection_name=row[6],
                metadata=json.loads(row[7]) if row[7] else {}
            )
            
            # Check if file was modified since last index
            if file_modified > record.last_modified:
                # Calculate new hash to confirm changes
                current_hash = self._calculate_file_hash(file_path)
                if current_hash and current_hash != record.file_hash:
                    return True, record
            
            return False, record
            
        except Exception as e:
            self.logger.error(f"Error checking indexing status for {file_path}: {e}")
            return True, None  # Default to needing indexing if we can't determine
    
    def update_index_record(self, record: FileIndexRecord):
        """Update or insert index record"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO indexed_files 
                (file_path, file_hash, last_modified, last_indexed, 
                 chunk_count, index_status, collection_name, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.file_path,
                record.file_hash,
                record.last_modified.isoformat(),
                record.last_indexed.isoformat(),
                record.chunk_count,
                record.index_status,
                record.collection_name,
                json.dumps(record.metadata)
            ))
            
            conn.commit()
            conn.close()
            
            self.logger.debug(f"Updated index record for {record.file_path}")
            
        except Exception as e:
            self.logger.error(f"Error updating index record: {e}")
    
    def get_indexed_files(self, status_filter: Optional[str] = None) -> List[FileIndexRecord]:
        """Get all indexed files, optionally filtered by status"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            if status_filter:
                cursor.execute(
                    "SELECT * FROM indexed_files WHERE index_status = ?",
                    (status_filter,)
                )
            else:
                cursor.execute("SELECT * FROM indexed_files")
            
            rows = cursor.fetchall()
            conn.close()
            
            records = []
            for row in rows:
                record = FileIndexRecord(
                    file_path=row[0],
                    file_hash=row[1],
                    last_modified=datetime.fromisoformat(row[2]),
                    last_indexed=datetime.fromisoformat(row[3]),
                    chunk_count=row[4],
                    index_status=row[5],
                    collection_name=row[6],
                    metadata=json.loads(row[7]) if row[7] else {}
                )
                records.append(record)
            
            return records
            
        except Exception as e:
            self.logger.error(f"Error getting indexed files: {e}")
            return []


class StructuredDataProcessor:
    """Process CSV and Excel files with schema preservation"""
    
    def __init__(self):
        self.logger = WindowsLogger(name="structured_data_processor")
        self.file_handler = WindowsFileHandler()
    
    def process_csv_advanced(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Advanced CSV processing with schema detection and relationship preservation"""
        try:
            # Read CSV with multiple encoding attempts
            df = None
            encoding_used = None
            delimiter_used = None
            
            encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'latin1']
            delimiters = [',', ';', '\t', '|']
            
            for encoding in encodings:
                for delimiter in delimiters:
                    try:
                        df = pd.read_csv(
                            file_path, 
                            encoding=encoding, 
                            delimiter=delimiter,
                            on_bad_lines='skip',
                            low_memory=False,
                            dtype=str  # Read as strings first for type detection
                        )
                        if len(df.columns) > 1 and len(df) > 0:
                            encoding_used = encoding
                            delimiter_used = delimiter
                            break
                    except Exception:
                        continue
                if df is not None:
                    break
            
            if df is None or df.empty:
                return None
            
            # Detect data types and schema
            schema_info = self._analyze_dataframe_schema(df)
            
            # Convert appropriate columns to numeric types
            df_typed = self._apply_data_types(df, schema_info['column_types'])
            
            # Generate indexable content
            content_variations = self._generate_csv_content_variations(df_typed, schema_info)
            
            # Get file metadata
            file_metadata = self.file_handler.get_file_metadata(file_path)
            
            result = {
                'content_variations': content_variations,
                'schema_info': schema_info,
                'dataframe_stats': {
                    'rows': len(df_typed),
                    'columns': len(df_typed.columns),
                    'memory_usage': df_typed.memory_usage(deep=True).sum(),
                    'encoding': encoding_used,
                    'delimiter': delimiter_used
                },
                'file_metadata': file_metadata,
                'processing_metadata': {
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                    'processor_type': 'structured_csv'
                }
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing CSV {file_path}: {e}")
            return None
    
    def process_excel_advanced(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Advanced Excel processing with multiple sheets and schema preservation"""
        if not EXCEL_AVAILABLE:
            self.logger.error("openpyxl not available for Excel processing")
            return None
        
        try:
            # Read all sheets
            excel_data = pd.read_excel(file_path, sheet_name=None, dtype=str)
            
            if not excel_data:
                return None
            
            all_content_variations = []
            all_schemas = {}
            
            for sheet_name, df in excel_data.items():
                if df.empty:
                    continue
                
                # Analyze schema for this sheet
                schema_info = self._analyze_dataframe_schema(df)
                schema_info['sheet_name'] = sheet_name
                all_schemas[sheet_name] = schema_info
                
                # Apply data types
                df_typed = self._apply_data_types(df, schema_info['column_types'])
                
                # Generate content variations for this sheet
                sheet_variations = self._generate_csv_content_variations(
                    df_typed, schema_info, sheet_prefix=sheet_name
                )
                all_content_variations.extend(sheet_variations)
            
            # Get file metadata
            file_metadata = self.file_handler.get_file_metadata(file_path)
            
            result = {
                'content_variations': all_content_variations,
                'schema_info': all_schemas,
                'dataframe_stats': {
                    'sheets': len(excel_data),
                    'total_rows': sum(len(df) for df in excel_data.values()),
                    'total_columns': sum(len(df.columns) for df in excel_data.values()),
                },
                'file_metadata': file_metadata,
                'processing_metadata': {
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                    'processor_type': 'structured_excel'
                }
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing Excel {file_path}: {e}")
            return None
    
    def _analyze_dataframe_schema(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze DataFrame schema and detect data types"""
        schema = {
            'column_names': list(df.columns),
            'column_types': {},
            'numeric_columns': [],
            'date_columns': [],
            'categorical_columns': [],
            'unique_values': {},
            'null_counts': {},
            'sample_values': {}
        }
        
        for column in df.columns:
            col_data = df[column].dropna()
            
            if len(col_data) == 0:
                schema['column_types'][column] = 'empty'
                continue
            
            # Get sample values
            schema['sample_values'][column] = col_data.head(5).tolist()
            schema['null_counts'][column] = df[column].isnull().sum()
            
            # Attempt type detection
            detected_type = self._detect_column_type(col_data)
            schema['column_types'][column] = detected_type
            
            # Categorize columns
            if detected_type in ['int', 'float']:
                schema['numeric_columns'].append(column)
            elif detected_type == 'datetime':
                schema['date_columns'].append(column)
            elif len(col_data.unique()) < min(50, len(col_data) * 0.5):
                schema['categorical_columns'].append(column)
            
            # Store unique value counts for categorical columns
            if column in schema['categorical_columns']:
                schema['unique_values'][column] = col_data.value_counts().head(20).to_dict()
        
        return schema
    
    def _detect_column_type(self, series: pd.Series) -> str:
        """Detect the most appropriate data type for a column"""
        # Try numeric conversion
        try:
            pd.to_numeric(series, errors='raise')
            # Check if it's integer
            if series.str.contains(r'\.').any():
                return 'float'
            else:
                return 'int'
        except (ValueError, TypeError, AttributeError):
            pass
        
        # Try datetime conversion
        try:
            pd.to_datetime(series, errors='raise')
            return 'datetime'
        except (ValueError, TypeError):
            pass
        
        # Check for boolean
        unique_vals = series.str.lower().unique()
        if len(unique_vals) <= 2 and all(val in ['true', 'false', '1', '0', 'yes', 'no', 't', 'f'] 
                                        for val in unique_vals if pd.notna(val)):
            return 'boolean'
        
        return 'string'
    
    def _apply_data_types(self, df: pd.DataFrame, column_types: Dict[str, str]) -> pd.DataFrame:
        """Apply detected data types to DataFrame"""
        df_typed = df.copy()
        
        for column, dtype in column_types.items():
            if column not in df_typed.columns:
                continue
                
            try:
                if dtype == 'int':
                    df_typed[column] = pd.to_numeric(df_typed[column], errors='coerce').astype('Int64')
                elif dtype == 'float':
                    df_typed[column] = pd.to_numeric(df_typed[column], errors='coerce')
                elif dtype == 'datetime':
                    df_typed[column] = pd.to_datetime(df_typed[column], errors='coerce')
                elif dtype == 'boolean':
                    df_typed[column] = df_typed[column].str.lower().map({
                        'true': True, 'false': False, '1': True, '0': False,
                        'yes': True, 'no': False, 't': True, 'f': False
                    })
                # 'string' remains as is
            except Exception as e:
                self.logger.warning(f"Could not convert column {column} to {dtype}: {e}")
        
        return df_typed
    
    def _generate_csv_content_variations(self, df: pd.DataFrame, schema_info: Dict[str, Any], 
                                       sheet_prefix: str = "") -> List[Dict[str, Any]]:
        """Generate multiple content variations for different indexing strategies"""
        variations = []
        
        prefix = f"{sheet_prefix}: " if sheet_prefix else ""
        
        # 1. Row-wise indexing - each row as a document
        for idx, row in df.iterrows():
            row_content_parts = []
            row_metadata = {
                'indexing_strategy': 'row_wise',
                'row_index': int(idx),
                'sheet_name': sheet_prefix if sheet_prefix else 'default'
            }
            
            # Create readable row content
            for column, value in row.items():
                if pd.notna(value):
                    row_content_parts.append(f"{column}: {value}")
                    
                    # Add to metadata for filtering
                    if schema_info['column_types'].get(column) in ['int', 'float']:
                        row_metadata[f"numeric_{column.lower().replace(' ', '_')}"] = float(value) if pd.notna(value) else None
                    else:
                        row_metadata[f"text_{column.lower().replace(' ', '_')}"] = str(value)
            
            if row_content_parts:
                variations.append({
                    'content': f"{prefix}Row {idx + 1}: " + " | ".join(row_content_parts),
                    'metadata': row_metadata,
                    'content_type': 'structured_row'
                })
        
        # 2. Column-wise indexing - each column as a document
        for column in df.columns:
            col_data = df[column].dropna()
            if len(col_data) == 0:
                continue
            
            col_content_parts = [f"Column: {column}"]
            
            # Add column statistics
            if schema_info['column_types'].get(column) in ['int', 'float']:
                try:
                    stats = col_data.describe()
                    col_content_parts.append(f"Statistics: Mean={stats['mean']:.2f}, "
                                           f"Min={stats['min']}, Max={stats['max']}")
                except:
                    pass
            
            # Add sample values
            sample_values = col_data.head(10).astype(str).tolist()
            col_content_parts.append(f"Sample values: {', '.join(sample_values)}")
            
            # Add unique values for categorical columns
            if column in schema_info.get('categorical_columns', []):
                unique_vals = col_data.value_counts().head(5)
                unique_desc = [f"{val} ({count})" for val, count in unique_vals.items()]
                col_content_parts.append(f"Top values: {', '.join(unique_desc)}")
            
            col_metadata = {
                'indexing_strategy': 'column_wise',
                'column_name': column,
                'column_type': schema_info['column_types'].get(column, 'string'),
                'unique_count': len(col_data.unique()),
                'null_count': int(schema_info['null_counts'].get(column, 0)),
                'sheet_name': sheet_prefix if sheet_prefix else 'default'
            }
            
            variations.append({
                'content': f"{prefix}" + " | ".join(col_content_parts),
                'metadata': col_metadata,
                'content_type': 'structured_column'
            })
        
        # 3. Summary indexing - overall table description
        summary_parts = [
            f"Data summary for {sheet_prefix if sheet_prefix else 'table'}:",
            f"Rows: {len(df)}, Columns: {len(df.columns)}",
            f"Column names: {', '.join(df.columns)}",
        ]
        
        # Add numeric column summaries
        if schema_info['numeric_columns']:
            summary_parts.append(f"Numeric columns: {', '.join(schema_info['numeric_columns'])}")
        
        # Add categorical column summaries  
        if schema_info['categorical_columns']:
            summary_parts.append(f"Categorical columns: {', '.join(schema_info['categorical_columns'])}")
        
        summary_metadata = {
            'indexing_strategy': 'summary',
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'numeric_columns': schema_info['numeric_columns'],
            'categorical_columns': schema_info['categorical_columns'],
            'sheet_name': sheet_prefix if sheet_prefix else 'default'
        }
        
        variations.append({
            'content': " | ".join(summary_parts),
            'metadata': summary_metadata,
            'content_type': 'structured_summary'
        })
        
        return variations


class MultiCollectionQdrantIndexer:
    """Qdrant indexer with support for multiple collections by data type"""
    
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.host = host
        self.port = port
        self.logger = WindowsLogger(name="multi_collection_indexer")
        
        # Initialize Qdrant client
        try:
            self.client = QdrantClient(host=host, port=port)
            self.logger.info(f"Connected to Qdrant at {host}:{port}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise
        
        # Initialize sentence transformer
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.vector_size = self.model.get_sentence_embedding_dimension()
            self.logger.info(f"Loaded embedding model with dimension: {self.vector_size}")
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {e}")
            raise
        
        # Collection configurations
        self.collection_configs = {
            'documents': {'description': 'General text documents'},
            'structured_data': {'description': 'CSV and Excel structured data'},
            'structured_rows': {'description': 'Individual rows from structured data'},
            'structured_columns': {'description': 'Column descriptions and statistics'},
            'structured_summaries': {'description': 'Table and sheet summaries'}
        }
        
        # Ensure all collections exist
        self._ensure_collections()
    
    def _ensure_collections(self):
        """Ensure all required collections exist"""
        try:
            existing_collections = {col.name for col in self.client.get_collections().collections}
            
            for collection_name, config in self.collection_configs.items():
                if collection_name not in existing_collections:
                    self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=self.vector_size,
                            distance=Distance.COSINE
                        )
                    )
                    self.logger.info(f"Created collection: {collection_name}")
                else:
                    self.logger.info(f"Collection exists: {collection_name}")
        except Exception as e:
            self.logger.error(f"Error ensuring collections: {e}")
            raise
    
    def index_content_variations(self, content_variations: List[Dict[str, Any]], 
                               base_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Index content variations into appropriate collections"""
        results = {
            'total_variations': len(content_variations),
            'successful_indexes': 0,
            'failed_indexes': 0,
            'collections_used': set(),
            'processing_time': 0
        }
        
        start_time = time.time()
        
        try:
            for i, variation in enumerate(content_variations):
                try:
                    # Determine target collection
                    content_type = variation.get('content_type', 'documents')
                    collection_name = self._map_content_type_to_collection(content_type)
                    
                    # Generate embedding
                    embedding = self.model.encode([variation['content']])[0]
                    
                    # Prepare payload
                    payload = {
                        'text': variation['content'],
                        'content_type': content_type,
                        **base_metadata,
                        **variation.get('metadata', {}),
                        'indexed_at': datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Create point
                    point = PointStruct(
                        id=int(time.time() * 1000000) + i,  # Unique ID
                        vector=embedding.tolist(),
                        payload=payload
                    )
                    
                    # Upload to appropriate collection
                    self.client.upsert(
                        collection_name=collection_name,
                        points=[point]
                    )
                    
                    results['successful_indexes'] += 1
                    results['collections_used'].add(collection_name)
                    
                except Exception as e:
                    self.logger.error(f"Error indexing variation {i}: {e}")
                    results['failed_indexes'] += 1
        
        except Exception as e:
            self.logger.error(f"Batch indexing error: {e}")
            results['error'] = str(e)
        
        results['processing_time'] = time.time() - start_time
        results['collections_used'] = list(results['collections_used'])
        
        return results
    
    def _map_content_type_to_collection(self, content_type: str) -> str:
        """Map content type to appropriate collection"""
        mapping = {
            'structured_row': 'structured_rows',
            'structured_column': 'structured_columns', 
            'structured_summary': 'structured_summaries',
            'structured_data': 'structured_data'
        }
        return mapping.get(content_type, 'documents')
    
    def search_across_collections(self, query: str, collections: List[str] = None, 
                                limit_per_collection: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Search across multiple collections"""
        if collections is None:
            collections = list(self.collection_configs.keys())
        
        results = {}
        query_embedding = self.model.encode([query])[0]
        
        for collection in collections:
            try:
                search_result = self.client.search(
                    collection_name=collection,
                    query_vector=query_embedding.tolist(),
                    limit=limit_per_collection,
                    score_threshold=0.6
                )
                
                collection_results = []
                for hit in search_result:
                    collection_results.append({
                        'id': hit.id,
                        'score': hit.score,
                        'text': hit.payload.get('text', ''),
                        'content_type': hit.payload.get('content_type', ''),
                        'collection': collection,
                        'metadata': hit.payload
                    })
                
                results[collection] = collection_results
                
            except Exception as e:
                self.logger.error(f"Error searching collection {collection}: {e}")
                results[collection] = []
        
        return results


class WindowsFileMonitor:
    """File system monitor for Windows using watchdog"""
    
    def __init__(self, watch_directories: List[str], callback_function, 
                 file_extensions: Set[str] = None):
        self.watch_directories = [Path(d) for d in watch_directories]
        self.callback_function = callback_function
        self.file_extensions = file_extensions or {'.csv', '.xlsx', '.xls'}
        self.logger = WindowsLogger(name="file_monitor")
        
        if not WATCHDOG_AVAILABLE:
            self.logger.error("Watchdog not available for file monitoring")
            return
        
        self.observer = Observer()
        self.is_monitoring = False
        
        # Set up event handler
        self.event_handler = self.WindowsFileEventHandler(
            self.callback_function, 
            self.file_extensions, 
            self.logger
        )
    
    class WindowsFileEventHandler(FileSystemEventHandler):
        """Windows-specific file event handler"""
        
        def __init__(self, callback, extensions, logger):
            self.callback = callback
            self.extensions = extensions
            self.logger = logger
            self.processing_files = set()  # Avoid duplicate processing
            
        def on_modified(self, event):
            if event.is_directory:
                return
                
            file_path = Path(event.src_path)
            
            # Check file extension
            if file_path.suffix.lower() not in self.extensions:
                return
            
            # Avoid duplicate processing
            if str(file_path) in self.processing_files:
                return
                
            self.processing_files.add(str(file_path))
            
            try:
                # Wait a moment for file operations to complete
                time.sleep(0.5)
                
                # Check if file is accessible (not locked)
                if WindowsFileHandler.is_file_locked(file_path):
                    self.logger.warning(f"File locked, skipping: {file_path}")
                    return
                
                self.logger.info(f"File modified: {file_path}")
                self.callback(file_path, 'modified')
                
            except Exception as e:
                self.logger.error(f"Error processing file event for {file_path}: {e}")
            finally:
                # Remove from processing set after delay
                threading.Timer(5.0, lambda: self.processing_files.discard(str(file_path))).start()
        
        def on_created(self, event):
            if event.is_directory:
                return
                
            file_path = Path(event.src_path)
            
            if file_path.suffix.lower() in self.extensions:
                # Wait for file to be fully written
                time.sleep(1.0)
                
                if not WindowsFileHandler.is_file_locked(file_path):
                    self.logger.info(f"File created: {file_path}")
                    self.callback(file_path, 'created')
    
    def start_monitoring(self):
        """Start file system monitoring"""
        if not WATCHDOG_AVAILABLE:
            self.logger.error("Cannot start monitoring: watchdog not available")
            return False
        
        try:
            for directory in self.watch_directories:
                if directory.exists():
                    self.observer.schedule(
                        self.event_handler, 
                        str(directory), 
                        recursive=True
                    )
                    self.logger.info(f"Monitoring directory: {directory}")
                else:
                    self.logger.warning(f"Directory does not exist: {directory}")
            
            self.observer.start()
            self.is_monitoring = True
            self.logger.info("File monitoring started")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting file monitor: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop file system monitoring"""
        if self.is_monitoring and self.observer:
            self.observer.stop()
            self.observer.join()
            self.is_monitoring = False
            self.logger.info("File monitoring stopped")


class StructuredDataIndexingSystem:
    """Complete structured data indexing system with incremental updates and monitoring"""
    
    def __init__(self,
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 enable_file_monitoring: bool = True,
                 watch_directories: List[str] = None):
        
        self.logger = WindowsLogger(name="structured_indexing_system")
        
        # Initialize components
        self.processor = StructuredDataProcessor()
        self.indexer = MultiCollectionQdrantIndexer(host=qdrant_host, port=qdrant_port)
        self.tracker = IndexTracker()
        
        # File monitoring setup
        self.enable_file_monitoring = enable_file_monitoring and WATCHDOG_AVAILABLE
        self.watch_directories = watch_directories or []
        self.file_monitor = None
        
        if self.enable_file_monitoring and self.watch_directories:
            self.file_monitor = WindowsFileMonitor(
                self.watch_directories, 
                self._on_file_change,
                file_extensions={'.csv', '.xlsx', '.xls'}
            )
        
        self.logger.info("Structured data indexing system initialized")
    
    def start_file_monitoring(self) -> bool:
        """Start file system monitoring"""
        if self.file_monitor:
            return self.file_monitor.start_monitoring()
        return False
    
    def stop_file_monitoring(self):
        """Stop file system monitoring"""
        if self.file_monitor:
            self.file_monitor.stop_monitoring()
    
    def _on_file_change(self, file_path: Path, event_type: str):
        """Handle file system events"""
        self.logger.info(f"File {event_type}: {file_path}")
        
        # Process the changed file
        try:
            result = self.index_structured_file(str(file_path), force_reindex=True)
            if result['success']:
                self.logger.info(f"Successfully re-indexed {file_path.name}")
            else:
                self.logger.error(f"Failed to re-index {file_path.name}: {result.get('message', 'Unknown error')}")
        except Exception as e:
            self.logger.error(f"Error processing file change for {file_path}: {e}")
    
    def index_structured_file(self, file_path: str, force_reindex: bool = False) -> Dict[str, Any]:
        """Index a single structured data file with incremental update support"""
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {'success': False, 'message': f'File does not exist: {file_path}'}
        
        # Check if indexing is needed (unless forced)
        if not force_reindex:
            needs_indexing, existing_record = self.tracker.needs_indexing(file_path)
            if not needs_indexing:
                return {
                    'success': True,
                    'message': 'File already up to date',
                    'skipped': True,
                    'existing_record': asdict(existing_record) if existing_record else None
                }
        
        start_time = time.time()
        
        try:
            # Process the file
            if file_path.suffix.lower() == '.csv':
                processed_data = self.processor.process_csv_advanced(file_path)
                collection_base = 'structured_data'
            elif file_path.suffix.lower() in ['.xlsx', '.xls']:
                processed_data = self.processor.process_excel_advanced(file_path)
                collection_base = 'structured_data'
            else:
                return {'success': False, 'message': f'Unsupported file type: {file_path.suffix}'}
            
            if not processed_data:
                return {'success': False, 'message': 'Failed to process structured data'}
            
            # Index content variations
            base_metadata = {
                'file_path': str(file_path),
                'file_name': file_path.name,
                'file_extension': file_path.suffix.lower(),
                **processed_data.get('file_metadata', {}),
                **processed_data.get('processing_metadata', {})
            }
            
            indexing_result = self.indexer.index_content_variations(
                processed_data['content_variations'],
                base_metadata
            )
            
            # Update tracking record
            file_stat = file_path.stat()
            file_hash = self.tracker._calculate_file_hash(file_path)
            
            record = FileIndexRecord(
                file_path=str(file_path),
                file_hash=file_hash or '',
                last_modified=datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc),
                last_indexed=datetime.now(timezone.utc),
                chunk_count=indexing_result['successful_indexes'],
                index_status='indexed' if indexing_result['failed_indexes'] == 0 else 'partial',
                collection_name=collection_base,
                metadata={
                    'schema_info': processed_data.get('schema_info', {}),
                    'dataframe_stats': processed_data.get('dataframe_stats', {}),
                    'indexing_result': indexing_result
                }
            )
            
            self.tracker.update_index_record(record)
            
            result = {
                'success': True,
                'file_path': str(file_path),
                'processing_time': time.time() - start_time,
                'content_variations': len(processed_data['content_variations']),
                'indexed_variations': indexing_result['successful_indexes'],
                'failed_variations': indexing_result['failed_indexes'],
                'collections_used': indexing_result['collections_used'],
                'schema_info': processed_data.get('schema_info', {}),
                'index_record': asdict(record)
            }
            
            self.logger.info(f"Structured file indexed: {file_path.name} - "
                           f"{result['indexed_variations']}/{result['content_variations']} variations")
            
            return result
            
        except Exception as e:
            # Update tracking record with error
            try:
                file_stat = file_path.stat()
                error_record = FileIndexRecord(
                    file_path=str(file_path),
                    file_hash='',
                    last_modified=datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc),
                    last_indexed=datetime.now(timezone.utc),
                    chunk_count=0,
                    index_status='failed',
                    collection_name='none',
                    metadata={'error': str(e)}
                )
                self.tracker.update_index_record(error_record)
            except:
                pass
            
            self.logger.error(f"Error indexing structured file {file_path}: {e}")
            return {
                'success': False,
                'file_path': str(file_path),
                'message': str(e),
                'processing_time': time.time() - start_time
            }
    
    def index_structured_directory(self, directory_path: str, recursive: bool = True) -> Dict[str, Any]:
        """Index all structured data files in a directory with incremental updates"""
        directory = Path(directory_path)
        
        if not directory.exists():
            return {'success': False, 'message': f'Directory does not exist: {directory_path}'}
        
        # Find structured data files
        supported_extensions = {'.csv', '.xlsx', '.xls'}
        files_to_process = []
        
        try:
            if recursive:
                search_pattern = "**/*"
            else:
                search_pattern = "*"
            
            for file_path in directory.glob(search_pattern):
                if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                    files_to_process.append(file_path)
        except Exception as e:
            return {'success': False, 'message': f'Error finding files: {e}'}
        
        if not files_to_process:
            return {'success': False, 'message': 'No structured data files found'}
        
        # Process files
        results = {
            'success': True,
            'directory': str(directory),
            'total_files': len(files_to_process),
            'processed_files': 0,
            'skipped_files': 0,
            'failed_files': 0,
            'total_variations': 0,
            'indexed_variations': 0,
            'processing_time': 0,
            'file_results': []
        }
        
        start_time = time.time()
        
        for file_path in files_to_process:
            file_result = self.index_structured_file(str(file_path))
            results['file_results'].append(file_result)
            
            if file_result['success']:
                if file_result.get('skipped', False):
                    results['skipped_files'] += 1
                else:
                    results['processed_files'] += 1
                    results['total_variations'] += file_result.get('content_variations', 0)
                    results['indexed_variations'] += file_result.get('indexed_variations', 0)
            else:
                results['failed_files'] += 1
        
        results['processing_time'] = time.time() - start_time
        
        self.logger.info(f"Directory indexing complete: {results['processed_files']} processed, "
                        f"{results['skipped_files']} skipped, {results['failed_files']} failed")
        
        return results
    
    def search_structured_data(self, query: str, search_strategy: str = 'all', 
                             limit_per_collection: int = 5) -> Dict[str, Any]:
        """Search structured data with different strategies"""
        
        if search_strategy == 'all':
            collections = ['structured_rows', 'structured_columns', 'structured_summaries']
        elif search_strategy == 'rows':
            collections = ['structured_rows']
        elif search_strategy == 'columns':
            collections = ['structured_columns']
        elif search_strategy == 'summaries':
            collections = ['structured_summaries']
        else:
            collections = ['structured_data']
        
        try:
            search_results = self.indexer.search_across_collections(
                query, collections, limit_per_collection
            )
            
            # Combine and rank results
            all_results = []
            for collection, results in search_results.items():
                for result in results:
                    result['search_collection'] = collection
                    all_results.append(result)
            
            # Sort by score
            all_results.sort(key=lambda x: x['score'], reverse=True)
            
            return {
                'success': True,
                'query': query,
                'strategy': search_strategy,
                'total_results': len(all_results),
                'results_by_collection': search_results,
                'top_results': all_results[:limit_per_collection * 2],
                'collections_searched': collections
            }
            
        except Exception as e:
            self.logger.error(f"Error searching structured data: {e}")
            return {
                'success': False,
                'message': str(e),
                'query': query,
                'strategy': search_strategy
            }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            # Get indexed files statistics
            indexed_files = self.tracker.get_indexed_files()
            status_counts = {}
            for record in indexed_files:
                status_counts[record.index_status] = status_counts.get(record.index_status, 0) + 1
            
            # Get collection information
            collections_info = {}
            for collection in self.indexer.collection_configs.keys():
                try:
                    info = self.indexer.client.get_collection(collection)
                    collections_info[collection] = {
                        'points_count': info.points_count,
                        'vectors_count': info.vectors_count,
                        'status': info.status
                    }
                except:
                    collections_info[collection] = {'error': 'Could not retrieve info'}
            
            return {
                'status': 'operational',
                'indexed_files': {
                    'total': len(indexed_files),
                    'by_status': status_counts,
                    'recent_files': [
                        {
                            'file_path': record.file_path,
                            'last_indexed': record.last_indexed.isoformat(),
                            'status': record.index_status,
                            'chunk_count': record.chunk_count
                        }
                        for record in sorted(indexed_files, key=lambda x: x.last_indexed, reverse=True)[:5]
                    ]
                },
                'collections': collections_info,
                'file_monitoring': {
                    'enabled': self.enable_file_monitoring,
                    'active': self.file_monitor.is_monitoring if self.file_monitor else False,
                    'watch_directories': [str(d) for d in self.watch_directories]
                },
                'supported_extensions': ['.csv', '.xlsx', '.xls'],
                'embedding_model': 'all-MiniLM-L6-v2',
                'vector_dimension': self.indexer.vector_size
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }