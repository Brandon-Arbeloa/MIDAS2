"""
MIDAS SQL-RAG Interface
Streamlit UI for managing data sources and integrated search
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import json
from pathlib import Path
import pyodbc
from typing import Dict, List, Any, Optional

# Local imports
from database_connection_manager import (
    DatabaseConnectionManager, DatabaseConfig,
    get_windows_username, get_windows_domain
)
from database_schema_indexer import DatabaseSchemaIndexer
from integrated_sql_rag_search import IntegratedSQLRAGSearch
from query_cache_manager import QueryCacheManager

# Page configuration
st.set_page_config(
    page_title="MIDAS SQL-RAG System",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .database-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 4px solid #1f77b4;
    }
    .sql-result-container {
        max-height: 500px;
        overflow-y: auto;
    }
    .connection-success {
        color: #28a745;
        font-weight: bold;
    }
    .connection-error {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseConnectionManager()
if 'schema_indexer' not in st.session_state:
    st.session_state.schema_indexer = DatabaseSchemaIndexer()
if 'search_system' not in st.session_state:
    st.session_state.search_system = IntegratedSQLRAGSearch()
if 'query_history' not in st.session_state:
    st.session_state.query_history = []

def render_database_connection_form():
    """Render form for adding new database connection"""
    st.subheader("➕ Add New Database Connection")
    
    with st.form("new_database_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Connection Name", placeholder="my_database")
            db_type = st.selectbox(
                "Database Type",
                ["postgresql", "mysql", "sqlite", "mssql"]
            )
            
            if db_type != "sqlite":
                host = st.text_input("Host", value="localhost")
                port = st.number_input(
                    "Port",
                    value=5432 if db_type == "postgresql" else 3306 if db_type == "mysql" else 1433
                )
            else:
                host = None
                port = None
        
        with col2:
            if db_type == "sqlite":
                database = st.text_input(
                    "Database File Path",
                    placeholder="C:\\Users\\Username\\Documents\\database.db"
                )
                use_windows_auth = False
                username = None
                password = None
            else:
                database = st.text_input("Database Name", placeholder="mydb")
                
                if db_type == "mssql":
                    use_windows_auth = st.checkbox(
                        "Use Windows Authentication",
                        value=True
                    )
                else:
                    use_windows_auth = False
                
                if not use_windows_auth:
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                else:
                    st.info(f"Will connect as: {get_windows_domain()}\\{get_windows_username()}")
                    username = None
                    password = None
        
        # Advanced options
        with st.expander("Advanced Options"):
            pool_size = st.number_input("Connection Pool Size", value=5, min_value=1)
            
            if db_type == "mssql":
                instance = st.text_input("Instance Name", value="SQLEXPRESS")
                driver = st.selectbox(
                    "ODBC Driver",
                    pyodbc.drivers() if pyodbc.drivers() else ["ODBC Driver 17 for SQL Server"]
                )
                options = {"instance": instance, "driver": driver}
            else:
                options = {}
        
        submitted = st.form_submit_button("Add Connection", type="primary")
        
        if submitted and name:
            # Create database config
            config = DatabaseConfig(
                name=name,
                db_type=db_type,
                host=host,
                port=port,
                database=database,
                username=username,
                password=password,
                use_windows_auth=use_windows_auth,
                pool_size=pool_size,
                options=options
            )
            
            # Add to manager
            st.session_state.db_manager.add_config(config)
            st.success(f"Added database connection: {name}")
            st.rerun()

def render_database_list():
    """Render list of configured databases"""
    st.subheader("📊 Configured Databases")
    
    if not st.session_state.db_manager.configs:
        st.info("No databases configured yet. Add one above!")
        return
    
    for name, config in st.session_state.db_manager.configs.items():
        with st.expander(f"🗄️ {name} ({config.db_type})", expanded=False):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f"**Type:** {config.db_type}")
                if config.host:
                    st.markdown(f"**Host:** {config.host}:{config.port}")
                st.markdown(f"**Database:** {config.database}")
                if config.use_windows_auth:
                    st.markdown("**Auth:** Windows Authentication")
            
            with col2:
                if st.button("Test Connection", key=f"test_{name}"):
                    with st.spinner("Testing connection..."):
                        result = st.session_state.db_manager.test_connection(name)
                        
                        if result['status'] == 'connected':
                            st.success("Connected!")
                            st.write(f"Version: {result['version'][:50]}...")
                            if result.get('size_bytes'):
                                size_mb = result['size_bytes'] / (1024 * 1024)
                                st.write(f"Size: {size_mb:.2f} MB")
                        else:
                            st.error(f"Connection failed: {result.get('error', 'Unknown error')}")
            
            with col3:
                if st.button("Index Schema", key=f"index_{name}"):
                    with st.spinner(f"Indexing {name}..."):
                        try:
                            embeddings = st.session_state.schema_indexer.index_database(name)
                            st.success(f"Indexed {len(embeddings)} tables")
                        except Exception as e:
                            st.error(f"Indexing failed: {e}")
                
                if st.button("Remove", key=f"remove_{name}"):
                    del st.session_state.db_manager.configs[name]
                    st.session_state.db_manager.save_configs()
                    st.rerun()

def render_sql_query_interface():
    """Render SQL query interface"""
    st.subheader("🔍 SQL Query Interface")
    
    # Natural language query
    nl_query = st.text_area(
        "Natural Language Query",
        placeholder="Find all customers who placed orders in the last month",
        height=80
    )
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        selected_db = st.selectbox(
            "Select Database",
            options=list(st.session_state.db_manager.configs.keys()),
            key="query_database"
        )
    
    with col2:
        use_llm = st.checkbox("Use LLM", value=True)
    
    with col3:
        limit = st.number_input("Limit Results", value=100, min_value=1, max_value=10000)
    
    if st.button("Generate & Execute Query", type="primary"):
        if nl_query and selected_db:
            with st.spinner("Generating SQL..."):
                try:
                    # Generate SQL
                    sql_query = st.session_state.search_system.get_sql_for_query(
                        nl_query,
                        selected_db
                    )
                    
                    # Display generated SQL
                    st.code(sql_query.query, language="sql")
                    st.write(f"Confidence: {sql_query.confidence:.2%}")
                    
                    # Execute query
                    with st.spinner("Executing query..."):
                        df = st.session_state.search_system.execute_sql(
                            sql_query.query,
                            selected_db,
                            limit=limit
                        )
                        
                        # Display results
                        st.success(f"Query returned {len(df)} rows")
                        
                        # Show data
                        st.dataframe(df, height=400)
                        
                        # Add to history
                        st.session_state.query_history.append({
                            'timestamp': datetime.now().isoformat(),
                            'natural_language': nl_query,
                            'sql': sql_query.query,
                            'database': selected_db,
                            'row_count': len(df)
                        })
                        
                        # Download options
                        col1, col2 = st.columns(2)
                        with col1:
                            csv = df.to_csv(index=False)
                            st.download_button(
                                "📥 Download CSV",
                                csv,
                                f"query_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv"
                            )
                        
                        with col2:
                            # Create Excel download
                            from io import BytesIO
                            output = BytesIO()
                            df.to_excel(output, index=False)
                            excel_data = output.getvalue()
                            
                            st.download_button(
                                "📥 Download Excel",
                                excel_data,
                                f"query_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        
                except Exception as e:
                    st.error(f"Query failed: {e}")
    
    # Manual SQL input
    with st.expander("Manual SQL Query"):
        manual_sql = st.text_area(
            "Enter SQL Query",
            height=150,
            placeholder="SELECT * FROM customers WHERE created_at > '2024-01-01'"
        )
        
        if st.button("Execute Manual Query"):
            if manual_sql and selected_db:
                try:
                    df = st.session_state.search_system.execute_sql(
                        manual_sql,
                        selected_db,
                        limit=limit
                    )
                    
                    st.success(f"Query returned {len(df)} rows")
                    st.dataframe(df, height=400)
                    
                except Exception as e:
                    st.error(f"Query failed: {e}")

def render_integrated_search():
    """Render integrated SQL-RAG search interface"""
    st.subheader("🔎 Integrated Search (SQL + Documents)")
    
    search_query = st.text_input(
        "Search Query",
        placeholder="Find information about customer orders and related documentation"
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_databases = st.checkbox("Search Databases", value=True)
    
    with col2:
        search_documents = st.checkbox("Search Documents", value=True)
    
    with col3:
        result_limit = st.slider("Results per source", 1, 20, 5)
    
    if st.button("🔍 Search", type="primary"):
        if search_query:
            with st.spinner("Searching..."):
                results = st.session_state.search_system.search(
                    search_query,
                    search_databases=search_databases,
                    search_documents=search_documents,
                    limit=result_limit
                )
                
                # Display results
                st.success(
                    f"Found {results['total_results']} results in "
                    f"{results['search_time_ms']:.0f}ms"
                )
                
                # Show results by type
                tab1, tab2, tab3 = st.tabs(["All Results", "Database Results", "Document Results"])
                
                with tab1:
                    # Combined ranked results
                    for i, result in enumerate(results.get('ranked_results', [])[:10]):
                        with st.container():
                            col1, col2 = st.columns([3, 1])
                            
                            with col1:
                                if result.source_type == 'database':
                                    st.markdown(f"**🗄️ Database:** {result.source_name}")
                                else:
                                    st.markdown(f"**📄 Document:** {result.source_name}")
                            
                            with col2:
                                st.metric("Relevance", f"{result.relevance_score:.2%}")
                            
                            # Show preview
                            st.text(result.preview[:300] + "..." if len(result.preview) > 300 else result.preview)
                            
                            # Show full data for database results
                            if result.source_type == 'database' and isinstance(result.content, pd.DataFrame):
                                with st.expander("View Data"):
                                    st.dataframe(result.content)
                            
                            st.divider()
                
                with tab2:
                    # Database results
                    for result in results.get('database_results', []):
                        st.markdown(f"**Table:** {result.source_name}")
                        st.text(result.preview)
                        if isinstance(result.content, pd.DataFrame):
                            with st.expander("View Full Data"):
                                st.dataframe(result.content)
                        st.divider()
                
                with tab3:
                    # Document results
                    for result in results.get('document_results', []):
                        st.markdown(f"**Document:** {result.source_name}")
                        st.text(result.content[:500] + "..." if len(result.content) > 500 else result.content)
                        st.divider()

def render_cache_management():
    """Render cache management interface"""
    st.subheader("💾 Query Cache Management")
    
    cache_manager = st.session_state.search_system.cache_manager if st.session_state.search_system.enable_caching else None
    
    if not cache_manager:
        st.warning("Caching is disabled")
        return
    
    # Cache statistics
    stats = cache_manager.get_cache_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Cache Hits", stats.get('hits', 0))
    
    with col2:
        st.metric("Cache Misses", stats.get('misses', 0))
    
    with col3:
        hit_rate = stats.get('hit_rate', 0) * 100
        st.metric("Hit Rate", f"{hit_rate:.1f}%")
    
    with col4:
        st.metric("Cached Queries", stats.get('cached_query_count', 0))
    
    # Cache size
    st.info(f"Total cache size: {stats.get('total_cache_size_mb', 0):.2f} MB")
    
    # Cached queries list
    with st.expander("View Cached Queries"):
        cached_queries = cache_manager.get_cached_queries()
        
        if cached_queries:
            for query in cached_queries[:10]:
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.text(query['query'][:80] + "..." if len(query['query']) > 80 else query['query'])
                
                with col2:
                    st.text(f"{query['row_count']} rows")
                
                with col3:
                    ttl = query.get('remaining_ttl', 0)
                    st.text(f"TTL: {ttl}s")
        else:
            st.info("No cached queries")
    
    # Cache controls
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Clear All Cache"):
            cleared = cache_manager.clear_all()
            st.success(f"Cleared {cleared} cached queries")
    
    with col2:
        selected_db = st.selectbox(
            "Clear cache for database:",
            ["All"] + list(st.session_state.db_manager.configs.keys()),
            key="cache_clear_db"
        )
        
        if st.button("Clear Database Cache"):
            if selected_db == "All":
                cleared = cache_manager.invalidate()
            else:
                cleared = cache_manager.invalidate(database=selected_db)
            st.success(f"Cleared {cleared} cached queries")

def render_query_history():
    """Render query history"""
    st.subheader("📜 Query History")
    
    if not st.session_state.query_history:
        st.info("No queries executed yet")
        return
    
    # Convert to DataFrame for display
    history_df = pd.DataFrame(st.session_state.query_history)
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    
    # Sort by timestamp descending
    history_df = history_df.sort_values('timestamp', ascending=False)
    
    # Display
    for _, row in history_df.head(20).iterrows():
        with st.expander(f"{row['timestamp'].strftime('%Y-%m-%d %H:%M')} - {row['database']}"):
            st.markdown(f"**Natural Language:** {row['natural_language']}")
            st.code(row['sql'], language='sql')
            st.markdown(f"**Results:** {row['row_count']} rows")

def main():
    st.title("🗄️ MIDAS SQL-RAG System")
    st.markdown("Integrated SQL database and document search with natural language queries")
    
    # Sidebar
    with st.sidebar:
        st.header("Navigation")
        page = st.radio(
            "Select Page",
            ["Data Sources", "SQL Query", "Integrated Search", "Cache Management", "Query History"]
        )
        
        st.divider()
        
        # System info
        st.subheader("System Info")
        st.write(f"**Windows User:** {get_windows_username()}")
        st.write(f"**Domain:** {get_windows_domain()}")
        
        # Available ODBC drivers
        with st.expander("ODBC Drivers"):
            drivers = pyodbc.drivers()
            for driver in drivers:
                st.write(f"- {driver}")
    
    # Main content
    if page == "Data Sources":
        render_database_connection_form()
        st.divider()
        render_database_list()
    
    elif page == "SQL Query":
        render_sql_query_interface()
    
    elif page == "Integrated Search":
        render_integrated_search()
    
    elif page == "Cache Management":
        render_cache_management()
    
    elif page == "Query History":
        render_query_history()

if __name__ == "__main__":
    main()