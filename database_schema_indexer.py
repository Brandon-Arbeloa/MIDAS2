"""
MIDAS Database Schema Indexer
Generates embeddings for database schemas and sample data
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

# Embeddings
from sentence_transformers import SentenceTransformer

# Vector storage
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue
)

# Local imports
from database_connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)

@dataclass
class SchemaEmbedding:
    """Schema embedding data"""
    database_name: str
    table_name: str
    schema_text: str
    sample_data_text: str
    metadata: Dict[str, Any]
    embedding: List[float]

class DatabaseSchemaIndexer:
    """Indexes database schemas and generates embeddings"""
    
    def __init__(self, 
                 embedding_model: str = "all-MiniLM-L6-v2",
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 collection_name: str = "database_schemas"):
        
        self.embedding_model = SentenceTransformer(embedding_model)
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection_name = collection_name
        self.db_manager = DatabaseConnectionManager()
        
        # Initialize collection
        self._init_collection()
    
    def _init_collection(self):
        """Initialize Qdrant collection for schemas"""
        try:
            collections = self.qdrant_client.get_collections()
            if self.collection_name not in [c.name for c in collections.collections]:
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=384,  # all-MiniLM-L6-v2 embedding size
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
    
    def generate_schema_text(self, database_name: str, table_name: str, 
                           table_info: Dict[str, Any]) -> str:
        """Generate natural language description of table schema"""
        lines = []
        
        # Table header
        lines.append(f"Table: {table_name} in database {database_name}")
        lines.append(f"Total rows: {table_info.get('row_count', 0):,}")
        lines.append("")
        
        # Columns
        lines.append("Columns:")
        for col in table_info['columns']:
            col_desc = f"- {col['name']} ({col['type']})"
            if col.get('primary_key'):
                col_desc += " [PRIMARY KEY]"
            if not col.get('nullable', True):
                col_desc += " NOT NULL"
            if col.get('default'):
                col_desc += f" DEFAULT {col['default']}"
            lines.append(col_desc)
        
        # Primary keys
        if table_info.get('primary_keys'):
            lines.append(f"\nPrimary Key: {', '.join(table_info['primary_keys'])}")
        
        # Foreign keys
        if table_info.get('foreign_keys'):
            lines.append("\nForeign Keys:")
            for fk in table_info['foreign_keys']:
                lines.append(
                    f"- {', '.join(fk['columns'])} -> "
                    f"{fk['referred_table']}({', '.join(fk['referred_columns'])})"
                )
        
        # Indexes
        if table_info.get('indexes'):
            lines.append("\nIndexes:")
            for idx in table_info['indexes']:
                idx_type = "UNIQUE " if idx.get('unique') else ""
                lines.append(f"- {idx_type}{idx['name']} on ({', '.join(idx['columns'])})")
        
        return "\n".join(lines)
    
    def generate_sample_data_text(self, sample_df: pd.DataFrame, 
                                max_rows: int = 5) -> str:
        """Generate text representation of sample data"""
        if sample_df.empty:
            return "No sample data available"
        
        lines = []
        lines.append(f"Sample data ({min(len(sample_df), max_rows)} rows):")
        
        # Get first few rows
        sample = sample_df.head(max_rows)
        
        # Format each row
        for idx, row in sample.iterrows():
            row_parts = []
            for col, val in row.items():
                if pd.notna(val):
                    if isinstance(val, (int, float)):
                        row_parts.append(f"{col}={val}")
                    else:
                        val_str = str(val)[:50]  # Truncate long values
                        if len(str(val)) > 50:
                            val_str += "..."
                        row_parts.append(f"{col}='{val_str}'")
            
            lines.append(f"Row {idx + 1}: {', '.join(row_parts)}")
        
        # Add column statistics
        lines.append("\nColumn statistics:")
        for col in sample_df.columns:
            dtype = sample_df[col].dtype
            if dtype in ['int64', 'float64']:
                lines.append(
                    f"- {col}: min={sample_df[col].min()}, "
                    f"max={sample_df[col].max()}, "
                    f"mean={sample_df[col].mean():.2f}"
                )
            else:
                unique_count = sample_df[col].nunique()
                lines.append(f"- {col}: {unique_count} unique values")
        
        return "\n".join(lines)
    
    def index_table(self, database_name: str, table_name: str) -> SchemaEmbedding:
        """Index a single table schema"""
        logger.info(f"Indexing table: {database_name}.{table_name}")
        
        try:
            # Get table information
            table_info = self.db_manager.get_table_info(database_name, table_name)
            
            # Generate schema text
            schema_text = self.generate_schema_text(database_name, table_name, table_info)
            
            # Get sample data
            try:
                sample_df = self.db_manager.get_sample_data(database_name, table_name, 100)
                sample_data_text = self.generate_sample_data_text(sample_df)
            except Exception as e:
                logger.warning(f"Failed to get sample data: {e}")
                sample_data_text = "Sample data not available"
            
            # Combine texts for embedding
            combined_text = f"{schema_text}\n\n{sample_data_text}"
            
            # Generate embedding
            embedding = self.embedding_model.encode(combined_text).tolist()
            
            # Create metadata
            metadata = {
                'database_name': database_name,
                'table_name': table_name,
                'column_count': len(table_info['columns']),
                'row_count': table_info['row_count'],
                'has_primary_key': bool(table_info.get('primary_keys')),
                'foreign_key_count': len(table_info.get('foreign_keys', [])),
                'index_count': len(table_info.get('indexes', [])),
                'indexed_at': datetime.now().isoformat()
            }
            
            # Add column names to metadata for filtering
            metadata['column_names'] = [col['name'] for col in table_info['columns']]
            
            schema_embedding = SchemaEmbedding(
                database_name=database_name,
                table_name=table_name,
                schema_text=schema_text,
                sample_data_text=sample_data_text,
                metadata=metadata,
                embedding=embedding
            )
            
            # Store in Qdrant
            self._store_embedding(schema_embedding)
            
            return schema_embedding
            
        except Exception as e:
            logger.error(f"Failed to index table {database_name}.{table_name}: {e}")
            raise
    
    def _store_embedding(self, schema_embedding: SchemaEmbedding):
        """Store schema embedding in Qdrant"""
        # Create unique ID
        point_id = hash(f"{schema_embedding.database_name}.{schema_embedding.table_name}") % (2**63)
        
        # Create payload
        payload = {
            'database_name': schema_embedding.database_name,
            'table_name': schema_embedding.table_name,
            'schema_text': schema_embedding.schema_text,
            'sample_data_text': schema_embedding.sample_data_text[:1000],  # Truncate for storage
            **schema_embedding.metadata
        }
        
        # Create point
        point = PointStruct(
            id=point_id,
            vector=schema_embedding.embedding,
            payload=payload
        )
        
        # Upsert to Qdrant
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        logger.info(f"Stored embedding for {schema_embedding.database_name}.{schema_embedding.table_name}")
    
    def index_database(self, database_name: str) -> List[SchemaEmbedding]:
        """Index all tables in a database"""
        logger.info(f"Indexing database: {database_name}")
        
        embeddings = []
        tables = self.db_manager.get_table_list(database_name)
        
        for table in tables:
            try:
                embedding = self.index_table(database_name, table)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to index table {table}: {e}")
        
        logger.info(f"Indexed {len(embeddings)} tables from {database_name}")
        return embeddings
    
    def search_schemas(self, query: str, limit: int = 5,
                      database_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for relevant table schemas"""
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # Build filter
        filter_conditions = []
        if database_filter:
            filter_conditions.append(
                FieldCondition(
                    key="database_name",
                    match=MatchValue(value=database_filter)
                )
            )
        
        # Search
        results = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
            query_filter=Filter(must=filter_conditions) if filter_conditions else None
        )
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                'database_name': result.payload['database_name'],
                'table_name': result.payload['table_name'],
                'score': result.score,
                'schema_text': result.payload['schema_text'],
                'metadata': {
                    k: v for k, v in result.payload.items()
                    if k not in ['database_name', 'table_name', 'schema_text', 'sample_data_text']
                }
            })
        
        return formatted_results
    
    def find_tables_with_columns(self, column_names: List[str],
                                database_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find tables containing specific columns"""
        # Build search query from column names
        query = f"Table with columns: {', '.join(column_names)}"
        
        # Search using embeddings
        results = self.search_schemas(query, limit=10, database_filter=database_filter)
        
        # Filter results to ensure they contain the requested columns
        filtered_results = []
        for result in results:
            table_columns = result['metadata'].get('column_names', [])
            if all(col.lower() in [tc.lower() for tc in table_columns] for col in column_names):
                filtered_results.append(result)
        
        return filtered_results
    
    def get_schema_statistics(self) -> Dict[str, Any]:
        """Get statistics about indexed schemas"""
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            
            # Get all points to analyze
            points = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                limit=1000
            )[0]
            
            # Analyze databases and tables
            databases = {}
            total_columns = 0
            total_rows = 0
            
            for point in points:
                db_name = point.payload['database_name']
                if db_name not in databases:
                    databases[db_name] = {
                        'tables': 0,
                        'total_columns': 0,
                        'total_rows': 0
                    }
                
                databases[db_name]['tables'] += 1
                databases[db_name]['total_columns'] += point.payload.get('column_count', 0)
                databases[db_name]['total_rows'] += point.payload.get('row_count', 0)
                
                total_columns += point.payload.get('column_count', 0)
                total_rows += point.payload.get('row_count', 0)
            
            return {
                'total_schemas': collection_info.points_count,
                'total_databases': len(databases),
                'total_columns': total_columns,
                'total_rows': total_rows,
                'databases': databases,
                'collection_size': collection_info.indexed_vectors_count
            }
            
        except Exception as e:
            logger.error(f"Failed to get schema statistics: {e}")
            return {}

def create_test_sqlite_db():
    """Create a test SQLite database for demonstration"""
    import sqlite3
    
    db_path = Path.home() / "Documents" / "midas_test.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            total_amount REAL,
            order_date DATE,
            status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL,
            category TEXT,
            stock_quantity INTEGER
        )
    """)
    
    # Insert sample data
    cursor.executemany(
        "INSERT OR IGNORE INTO customers (name, email) VALUES (?, ?)",
        [
            ("John Doe", "john@example.com"),
            ("Jane Smith", "jane@example.com"),
            ("Bob Johnson", "bob@example.com")
        ]
    )
    
    cursor.executemany(
        "INSERT OR IGNORE INTO products (name, price, category, stock_quantity) VALUES (?, ?, ?, ?)",
        [
            ("Laptop", 999.99, "Electronics", 50),
            ("Mouse", 29.99, "Electronics", 200),
            ("Desk", 299.99, "Furniture", 30)
        ]
    )
    
    conn.commit()
    conn.close()
    
    logger.info(f"Created test database at: {db_path}")
    return str(db_path)

if __name__ == "__main__":
    # Create test database
    test_db_path = create_test_sqlite_db()
    
    # Initialize indexer
    indexer = DatabaseSchemaIndexer()
    
    # Index the test database
    embeddings = indexer.index_database("local_sqlite")
    
    # Test search
    results = indexer.search_schemas("Find tables with customer information")
    for result in results:
        print(f"\nTable: {result['database_name']}.{result['table_name']}")
        print(f"Score: {result['score']:.3f}")
        print(f"Schema: {result['schema_text'][:200]}...")
    
    # Get statistics
    stats = indexer.get_schema_statistics()
    print(f"\nSchema Statistics: {json.dumps(stats, indent=2)}")