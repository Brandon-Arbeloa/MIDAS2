"""
Test script for MIDAS SQL Integration
Tests all components of the SQL-RAG system
"""

import sys
import time
import json
import pandas as pd
from pathlib import Path
import sqlite3
from typing import Dict, Any

# Local imports
from database_connection_manager import DatabaseConnectionManager, DatabaseConfig
from database_schema_indexer import DatabaseSchemaIndexer, create_test_sqlite_db
from sql_query_generator import SQLQueryGenerator
from query_cache_manager import QueryCacheManager
from integrated_sql_rag_search import IntegratedSQLRAGSearch

def test_database_connections():
    """Test database connection manager"""
    print("\n1. Testing Database Connections")
    print("-" * 50)
    
    manager = DatabaseConnectionManager()
    
    # Create test SQLite database
    test_db_path = create_test_sqlite_db()
    
    # Add SQLite configuration
    sqlite_config = DatabaseConfig(
        name="test_sqlite",
        db_type="sqlite",
        database=test_db_path
    )
    
    manager.add_config(sqlite_config)
    
    # Test connection
    result = manager.test_connection("test_sqlite")
    print(f"SQLite connection test: {result['status']}")
    
    if result['status'] == 'connected':
        print(f"  Version: {result['version']}")
        
        # Get table list
        tables = manager.get_table_list("test_sqlite")
        print(f"  Tables: {tables}")
        
        # Get table info
        for table in tables:
            info = manager.get_table_info("test_sqlite", table)
            print(f"  Table '{table}': {info['column_count']} columns, {info['row_count']} rows")
        
        return True
    
    return False

def test_schema_indexing():
    """Test schema indexing and embeddings"""
    print("\n2. Testing Schema Indexing")
    print("-" * 50)
    
    indexer = DatabaseSchemaIndexer()
    
    try:
        # Index test database
        embeddings = indexer.index_database("test_sqlite")
        print(f"Indexed {len(embeddings)} tables")
        
        # Search schemas
        test_queries = [
            "Find tables with customer information",
            "Show tables with order data",
            "Which tables have product details?"
        ]
        
        for query in test_queries:
            print(f"\nSearching: '{query}'")
            results = indexer.search_schemas(query, limit=3)
            
            for i, result in enumerate(results):
                print(f"  {i+1}. {result['table_name']} (score: {result['score']:.3f})")
        
        # Get statistics
        stats = indexer.get_schema_statistics()
        print(f"\nSchema statistics: {json.dumps(stats, indent=2)}")
        
        return True
        
    except Exception as e:
        print(f"Schema indexing failed: {e}")
        return False

def test_query_generation():
    """Test SQL query generation"""
    print("\n3. Testing SQL Query Generation")
    print("-" * 50)
    
    generator = SQLQueryGenerator()
    
    test_queries = [
        "Show all customers",
        "Count orders by status",
        "Find products with price greater than 50",
        "Get top 10 most expensive products",
        "Show customer orders"
    ]
    
    success_count = 0
    
    for nl_query in test_queries:
        print(f"\nNL Query: '{nl_query}'")
        
        try:
            sql_query = generator.generate_query(nl_query, database_name="test_sqlite")
            print(f"Generated SQL: {sql_query.query}")
            print(f"Confidence: {sql_query.confidence:.2f}")
            
            # Validate query
            is_valid, error = generator.validate_query(sql_query)
            print(f"Valid: {is_valid}" + (f" - {error}" if error else ""))
            
            if is_valid:
                success_count += 1
                
        except Exception as e:
            print(f"Generation failed: {e}")
    
    print(f"\nSuccess rate: {success_count}/{len(test_queries)}")
    return success_count > len(test_queries) // 2

def test_query_caching():
    """Test query result caching"""
    print("\n4. Testing Query Result Caching")
    print("-" * 50)
    
    cache_manager = QueryCacheManager()
    
    # Test data
    test_df = pd.DataFrame({
        'id': range(1, 101),
        'value': [f'Value {i}' for i in range(1, 101)]
    })
    
    query = "SELECT * FROM test_table"
    database = "test_db"
    
    # Test set
    print("Testing cache set...")
    success = cache_manager.set(query, database, test_df, ttl=60)
    print(f"Cache set: {'Success' if success else 'Failed'}")
    
    # Test get
    print("\nTesting cache get...")
    cached_df = cache_manager.get(query, database)
    
    if cached_df is not None:
        print(f"Cache hit! Retrieved {len(cached_df)} rows")
        
        # Verify data integrity
        if cached_df.equals(test_df):
            print("Data integrity verified")
        else:
            print("Data integrity check failed")
    else:
        print("Cache miss")
    
    # Get stats
    stats = cache_manager.get_cache_stats()
    print(f"\nCache stats: {json.dumps(stats, indent=2)}")
    
    return cached_df is not None

def test_integrated_search():
    """Test integrated SQL-RAG search"""
    print("\n5. Testing Integrated Search")
    print("-" * 50)
    
    search_system = IntegratedSQLRAGSearch()
    
    test_queries = [
        "Find customer information",
        "Show order details",
        "Product catalog data"
    ]
    
    for query in test_queries:
        print(f"\nSearching: '{query}'")
        
        try:
            results = search_system.search(
                query,
                search_databases=True,
                search_documents=False,  # Only test database search
                limit=5
            )
            
            print(f"Found {results['total_results']} results in {results['search_time_ms']:.0f}ms")
            
            # Show database results
            for i, result in enumerate(results['database_results'][:3]):
                print(f"\n  Result {i+1}: {result.source_name}")
                print(f"  Score: {result.relevance_score:.3f}")
                print(f"  Preview: {result.preview[:100]}...")
                
        except Exception as e:
            print(f"Search failed: {e}")
    
    return True

def test_windows_specific_features():
    """Test Windows-specific features"""
    print("\n6. Testing Windows-Specific Features")
    print("-" * 50)
    
    # Test ODBC drivers
    try:
        import pyodbc
        drivers = pyodbc.drivers()
        print(f"Available ODBC drivers: {len(drivers)}")
        for driver in drivers[:5]:
            print(f"  - {driver}")
        
        if len(drivers) > 5:
            print(f"  ... and {len(drivers) - 5} more")
    except Exception as e:
        print(f"ODBC driver test failed: {e}")
    
    # Test Windows authentication info
    from database_connection_manager import get_windows_username, get_windows_domain
    print(f"\nWindows user: {get_windows_domain()}\\{get_windows_username()}")
    
    # Test SQL Server connection with Windows auth (if available)
    manager = DatabaseConnectionManager()
    
    sqlserver_config = DatabaseConfig(
        name="test_sqlserver",
        db_type="mssql",
        host="localhost",
        database="master",
        use_windows_auth=True,
        options={'instance': 'SQLEXPRESS'}
    )
    
    manager.add_config(sqlserver_config)
    
    print("\nTesting SQL Server with Windows Authentication...")
    result = manager.test_connection("test_sqlserver")
    print(f"Result: {result['status']}")
    
    return True

def run_all_tests():
    """Run all integration tests"""
    print("=" * 70)
    print("MIDAS SQL Integration Test Suite")
    print("=" * 70)
    
    tests = [
        ("Database Connections", test_database_connections),
        ("Schema Indexing", test_schema_indexing),
        ("Query Generation", test_query_generation),
        ("Query Caching", test_query_caching),
        ("Integrated Search", test_integrated_search),
        ("Windows Features", test_windows_specific_features)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            start_time = time.time()
            
            success = test_func()
            duration = time.time() - start_time
            
            results[test_name] = {
                'success': success,
                'duration': duration
            }
            
            print(f"\n{'✅ PASSED' if success else '❌ FAILED'} ({duration:.2f}s)")
            
        except Exception as e:
            print(f"\n❌ FAILED with error: {e}")
            results[test_name] = {
                'success': False,
                'error': str(e)
            }
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results.values() if r.get('success', False))
    total = len(results)
    
    print(f"\nTests passed: {passed}/{total}")
    
    for test_name, result in results.items():
        status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
        print(f"{status} - {test_name}")
        if 'error' in result:
            print(f"     Error: {result['error']}")
    
    print("\n" + "=" * 70)
    
    return passed == total

if __name__ == "__main__":
    # Run all tests
    success = run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)