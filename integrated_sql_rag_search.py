"""
MIDAS Integrated SQL-RAG Search
Combines database query results with document search
"""

import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Sentence transformers for embeddings
from sentence_transformers import SentenceTransformer

# Local imports
from database_connection_manager import DatabaseConnectionManager
from database_schema_indexer import DatabaseSchemaIndexer
from sql_query_generator import SQLQueryGenerator, SQLQuery
from query_cache_manager import QueryCacheManager, QueryResultPaginator
from document_indexer import DocumentIndexingSystem
from qdrant_search_engine import QdrantSearchEngine

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Unified search result"""
    source_type: str  # 'database' or 'document'
    source_name: str
    content: Union[str, pd.DataFrame]
    relevance_score: float
    metadata: Dict[str, Any]
    preview: str

class IntegratedSQLRAGSearch:
    """Integrates SQL database search with document RAG search"""
    
    def __init__(self,
                 embedding_model: str = "all-MiniLM-L6-v2",
                 enable_caching: bool = True,
                 cache_ttl: int = 3600):
        
        # Initialize components
        self.embedding_model = SentenceTransformer(embedding_model)
        self.db_manager = DatabaseConnectionManager()
        self.schema_indexer = DatabaseSchemaIndexer(embedding_model=embedding_model)
        self.query_generator = SQLQueryGenerator(schema_indexer=self.schema_indexer)
        self.doc_search = QdrantSearchEngine()
        
        # Caching
        self.enable_caching = enable_caching
        if enable_caching:
            self.cache_manager = QueryCacheManager(default_ttl=cache_ttl)
        
        # Pagination
        self.paginator = QueryResultPaginator()
        
        # Thread pool for parallel execution
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def search(self, 
              query: str,
              search_databases: bool = True,
              search_documents: bool = True,
              database_names: Optional[List[str]] = None,
              limit: int = 10,
              page: int = 1) -> Dict[str, Any]:
        """
        Unified search across databases and documents
        
        Args:
            query: Natural language search query
            search_databases: Whether to search in databases
            search_documents: Whether to search in documents
            database_names: Specific databases to search (None for all)
            limit: Maximum results per source
            page: Page number for pagination
        
        Returns:
            Dictionary with search results and metadata
        """
        
        start_time = datetime.now()
        results = {
            'query': query,
            'database_results': [],
            'document_results': [],
            'total_results': 0,
            'search_time_ms': 0,
            'page': page,
            'errors': []
        }
        
        # Execute searches in parallel
        futures = []
        
        if search_databases:
            futures.append(
                self.executor.submit(
                    self._search_databases, 
                    query, 
                    database_names, 
                    limit
                )
            )
        
        if search_documents:
            futures.append(
                self.executor.submit(
                    self._search_documents,
                    query,
                    limit
                )
            )
        
        # Collect results
        for future in futures:
            try:
                result_type, result_data = future.result(timeout=30)
                if result_type == 'database':
                    results['database_results'] = result_data
                elif result_type == 'document':
                    results['document_results'] = result_data
            except Exception as e:
                logger.error(f"Search error: {e}")
                results['errors'].append(str(e))
        
        # Calculate total results and search time
        results['total_results'] = (
            len(results['database_results']) + 
            len(results['document_results'])
        )
        results['search_time_ms'] = (datetime.now() - start_time).total_seconds() * 1000
        
        # Rank combined results
        results['ranked_results'] = self._rank_combined_results(
            results['database_results'],
            results['document_results'],
            query
        )
        
        return results
    
    def _search_databases(self, 
                         query: str,
                         database_names: Optional[List[str]],
                         limit: int) -> Tuple[str, List[SearchResult]]:
        """Search in databases"""
        
        db_results = []
        
        # Get available databases
        if database_names is None:
            database_names = list(self.db_manager.configs.keys())
        
        for db_name in database_names:
            try:
                # Generate SQL query
                sql_query = self.query_generator.generate_query(
                    query,
                    database_name=db_name
                )
                
                if not sql_query.query:
                    continue
                
                # Check cache first
                cached_result = None
                if self.enable_caching:
                    cached_result = self.cache_manager.get(
                        sql_query.query,
                        db_name
                    )
                
                if cached_result is not None:
                    df = cached_result
                    logger.info(f"Using cached result for {db_name}")
                else:
                    # Execute query
                    df = self.db_manager.execute_query(
                        db_name,
                        sql_query.query,
                        limit=limit
                    )
                    
                    # Cache result
                    if self.enable_caching and len(df) > 0:
                        self.cache_manager.set(
                            sql_query.query,
                            db_name,
                            df
                        )
                
                # Create search result
                if len(df) > 0:
                    result = SearchResult(
                        source_type='database',
                        source_name=f"{db_name}.{sql_query.tables[0] if sql_query.tables else 'unknown'}",
                        content=df,
                        relevance_score=sql_query.confidence,
                        metadata={
                            'query': sql_query.query,
                            'row_count': len(df),
                            'column_count': len(df.columns),
                            'tables': sql_query.tables
                        },
                        preview=self._generate_dataframe_preview(df)
                    )
                    
                    db_results.append(result)
                    
            except Exception as e:
                logger.error(f"Database search error for {db_name}: {e}")
        
        return 'database', db_results
    
    def _search_documents(self, query: str, limit: int) -> Tuple[str, List[SearchResult]]:
        """Search in documents"""
        
        doc_results = []
        
        try:
            # Search documents using Qdrant
            search_results = self.doc_search.search(
                query=query,
                limit=limit
            )
            
            # Convert to SearchResult format
            for result in search_results:
                doc_result = SearchResult(
                    source_type='document',
                    source_name=result['metadata'].get('file_path', 'Unknown'),
                    content=result['content'],
                    relevance_score=result['score'],
                    metadata=result['metadata'],
                    preview=result['content'][:200] + '...' if len(result['content']) > 200 else result['content']
                )
                
                doc_results.append(doc_result)
                
        except Exception as e:
            logger.error(f"Document search error: {e}")
        
        return 'document', doc_results
    
    def _generate_dataframe_preview(self, df: pd.DataFrame, max_rows: int = 3) -> str:
        """Generate text preview of DataFrame"""
        if df.empty:
            return "No data"
        
        preview_rows = min(len(df), max_rows)
        preview_df = df.head(preview_rows)
        
        # Convert to string representation
        preview_lines = []
        preview_lines.append(f"Columns: {', '.join(df.columns)}")
        preview_lines.append(f"Rows: {len(df)}")
        preview_lines.append("")
        
        # Add sample rows
        for idx, row in preview_df.iterrows():
            row_str = ", ".join([f"{col}={val}" for col, val in row.items()])
            preview_lines.append(f"Row {idx + 1}: {row_str}")
        
        if len(df) > max_rows:
            preview_lines.append(f"... and {len(df) - max_rows} more rows")
        
        return "\n".join(preview_lines)
    
    def _rank_combined_results(self,
                             db_results: List[SearchResult],
                             doc_results: List[SearchResult],
                             query: str) -> List[SearchResult]:
        """Rank combined results from different sources"""
        
        all_results = []
        
        # Normalize scores for database results
        if db_results:
            max_db_score = max(r.relevance_score for r in db_results)
            for result in db_results:
                # Boost database results if they have high row counts
                boost = 1.0
                if isinstance(result.content, pd.DataFrame):
                    row_count = len(result.content)
                    if row_count > 100:
                        boost = 1.2
                    elif row_count > 1000:
                        boost = 1.5
                
                result.relevance_score = (result.relevance_score / max_db_score) * boost
                all_results.append(result)
        
        # Document results already have normalized scores
        all_results.extend(doc_results)
        
        # Sort by relevance score
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return all_results
    
    def get_sql_for_query(self, query: str, database_name: str) -> SQLQuery:
        """Get generated SQL for a natural language query"""
        return self.query_generator.generate_query(query, database_name)
    
    def execute_sql(self, 
                   sql: str, 
                   database_name: str,
                   use_cache: bool = True,
                   limit: int = 1000) -> pd.DataFrame:
        """Execute raw SQL query"""
        
        # Check cache
        if use_cache and self.enable_caching:
            cached = self.cache_manager.get(sql, database_name)
            if cached is not None:
                return cached
        
        # Execute query
        df = self.db_manager.execute_query(database_name, sql, limit=limit)
        
        # Cache result
        if use_cache and self.enable_caching and len(df) > 0:
            self.cache_manager.set(sql, database_name, df)
        
        return df
    
    def export_results(self, 
                      results: List[SearchResult],
                      format: str = 'csv',
                      output_path: str = None) -> str:
        """Export search results to file"""
        
        if format == 'csv':
            # Combine all DataFrames
            all_data = []
            
            for result in results:
                if isinstance(result.content, pd.DataFrame):
                    df = result.content.copy()
                    df['_source'] = result.source_name
                    df['_relevance'] = result.relevance_score
                    all_data.append(df)
                else:
                    # Convert text results to DataFrame
                    text_df = pd.DataFrame([{
                        'content': result.content,
                        '_source': result.source_name,
                        '_relevance': result.relevance_score
                    }])
                    all_data.append(text_df)
            
            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                
                if output_path:
                    combined_df.to_csv(output_path, index=False)
                    return output_path
                else:
                    return combined_df.to_csv(index=False)
        
        elif format == 'json':
            # Convert to JSON format
            json_data = []
            
            for result in results:
                if isinstance(result.content, pd.DataFrame):
                    data = result.content.to_dict('records')
                else:
                    data = {'content': result.content}
                
                json_data.append({
                    'source': result.source_name,
                    'type': result.source_type,
                    'relevance': result.relevance_score,
                    'data': data,
                    'metadata': result.metadata
                })
            
            import json
            if output_path:
                with open(output_path, 'w') as f:
                    json.dump(json_data, f, indent=2)
                return output_path
            else:
                return json.dumps(json_data, indent=2)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get search system statistics"""
        stats = {
            'databases': {
                'connected': len(self.db_manager.connections),
                'configured': len(self.db_manager.configs),
                'indexed_schemas': self.schema_indexer.get_schema_statistics()
            },
            'documents': {
                'collections': self.doc_search.get_collection_stats() if hasattr(self.doc_search, 'get_collection_stats') else {}
            }
        }
        
        if self.enable_caching:
            stats['cache'] = self.cache_manager.get_cache_stats()
        
        return stats

# Example usage
if __name__ == "__main__":
    # Initialize integrated search
    search_system = IntegratedSQLRAGSearch()
    
    # Test search queries
    test_queries = [
        "Find customer orders with high value",
        "Show products in electronics category",
        "What are the sales trends?",
        "Find documentation about API endpoints"
    ]
    
    for query in test_queries:
        print(f"\nSearching for: {query}")
        results = search_system.search(query, limit=5)
        
        print(f"Found {results['total_results']} results in {results['search_time_ms']:.2f}ms")
        
        # Show top results
        for i, result in enumerate(results['ranked_results'][:3]):
            print(f"\n{i+1}. {result.source_type.upper()} - {result.source_name}")
            print(f"   Relevance: {result.relevance_score:.3f}")
            print(f"   Preview: {result.preview[:100]}...")
    
    # Get statistics
    stats = search_system.get_statistics()
    print(f"\nSystem Statistics: {json.dumps(stats, indent=2)}")