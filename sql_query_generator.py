"""
MIDAS SQL Query Generator
Generates SQL queries from natural language using schema context
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

# LLM for query generation
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("Ollama not available. Using rule-based query generation.")

# Local imports
from database_schema_indexer import DatabaseSchemaIndexer
from database_connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)

@dataclass
class SQLQuery:
    """Generated SQL query with metadata"""
    query: str
    database_name: str
    tables: List[str]
    confidence: float
    explanation: str
    parameters: Dict[str, Any] = None

class SQLQueryGenerator:
    """Generates SQL queries from natural language"""
    
    def __init__(self, 
                 schema_indexer: Optional[DatabaseSchemaIndexer] = None,
                 llm_model: str = "codellama:7b"):
        
        self.schema_indexer = schema_indexer or DatabaseSchemaIndexer()
        self.db_manager = DatabaseConnectionManager()
        self.llm_model = llm_model
        
        # Common SQL patterns
        self.patterns = {
            'select_all': r'(show|get|find|select|list)\s+(all|every)?\s*(\w+)',
            'count': r'(count|how many|number of)\s+(\w+)',
            'filter': r'(where|with|having)\s+(\w+)\s*(=|is|equals|contains)\s*["\']?([^"\']+)["\']?',
            'order': r'(order|sort)\s+by\s+(\w+)\s*(desc|descending|asc|ascending)?',
            'limit': r'(top|first|limit)\s+(\d+)',
            'aggregate': r'(sum|average|avg|max|maximum|min|minimum)\s+(?:of\s+)?(\w+)',
            'join': r'(join|combine|merge)\s+(\w+)\s+(?:and|with)\s+(\w+)',
            'group': r'group\s+by\s+(\w+)'
        }
    
    def generate_query(self, 
                      natural_language: str,
                      database_name: Optional[str] = None,
                      use_llm: bool = True) -> SQLQuery:
        """Generate SQL query from natural language"""
        
        # Find relevant schemas
        schema_results = self.schema_indexer.search_schemas(
            natural_language, 
            limit=3,
            database_filter=database_name
        )
        
        if not schema_results:
            return SQLQuery(
                query="",
                database_name=database_name or "",
                tables=[],
                confidence=0.0,
                explanation="No relevant tables found"
            )
        
        # Use the most relevant schema
        best_schema = schema_results[0]
        context_schemas = schema_results[:3]
        
        # Try LLM-based generation first
        if use_llm and OLLAMA_AVAILABLE:
            try:
                return self._generate_with_llm(
                    natural_language, 
                    context_schemas,
                    database_name or best_schema['database_name']
                )
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}. Falling back to rule-based.")
        
        # Fallback to rule-based generation
        return self._generate_with_rules(
            natural_language,
            best_schema,
            database_name or best_schema['database_name']
        )
    
    def _generate_with_llm(self, 
                          natural_language: str,
                          context_schemas: List[Dict[str, Any]],
                          database_name: str) -> SQLQuery:
        """Generate query using LLM"""
        
        # Build context prompt
        schema_context = "\n\n".join([
            f"Table: {schema['table_name']}\n{schema['schema_text']}"
            for schema in context_schemas
        ])
        
        prompt = f"""Given the following database schemas:

{schema_context}

Generate a SQL query for the following request:
"{natural_language}"

Requirements:
1. Use only the tables and columns from the provided schemas
2. Return valid SQL that can be executed
3. Include appropriate JOINs if multiple tables are needed
4. Add reasonable LIMIT if not specified
5. Use proper SQL syntax for the database type

Return the SQL query only, no explanation."""

        try:
            # Call Ollama
            response = ollama.generate(
                model=self.llm_model,
                prompt=prompt
            )
            
            generated_sql = response['response'].strip()
            
            # Clean up the SQL
            generated_sql = self._clean_sql(generated_sql)
            
            # Extract table names
            tables = self._extract_table_names(generated_sql, context_schemas)
            
            return SQLQuery(
                query=generated_sql,
                database_name=database_name,
                tables=tables,
                confidence=0.8,
                explanation="Generated using LLM"
            )
            
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise
    
    def _generate_with_rules(self,
                           natural_language: str,
                           schema: Dict[str, Any],
                           database_name: str) -> SQLQuery:
        """Generate query using rule-based approach"""
        
        nl_lower = natural_language.lower()
        table_name = schema['table_name']
        columns = self._extract_columns_from_schema(schema['schema_text'])
        
        # Start building query
        query_parts = {
            'select': [],
            'from': table_name,
            'where': [],
            'group_by': [],
            'order_by': [],
            'limit': None
        }
        
        # Detect query type and build accordingly
        confidence = 0.5
        
        # COUNT queries
        count_match = re.search(self.patterns['count'], nl_lower)
        if count_match:
            query_parts['select'] = ['COUNT(*)']
            confidence = 0.7
        
        # AGGREGATE queries
        agg_match = re.search(self.patterns['aggregate'], nl_lower)
        if agg_match:
            agg_func = agg_match.group(1).upper()
            if agg_func == 'AVG':
                agg_func = 'AVG'
            
            # Find numeric column
            col_name = self._find_column(agg_match.group(2), columns)
            if col_name:
                query_parts['select'] = [f'{agg_func}({col_name})']
                confidence = 0.7
        
        # SELECT queries
        if not query_parts['select']:
            select_match = re.search(self.patterns['select_all'], nl_lower)
            if select_match or any(word in nl_lower for word in ['show', 'get', 'find', 'list']):
                # Check if specific columns are mentioned
                mentioned_cols = []
                for col in columns:
                    if col.lower() in nl_lower:
                        mentioned_cols.append(col)
                
                if mentioned_cols:
                    query_parts['select'] = mentioned_cols
                    confidence = 0.6
                else:
                    query_parts['select'] = ['*']
                    confidence = 0.5
        
        # WHERE conditions
        filter_match = re.search(self.patterns['filter'], nl_lower)
        if filter_match:
            col_name = self._find_column(filter_match.group(2), columns)
            operator = '=' if filter_match.group(3) in ['=', 'is', 'equals'] else 'LIKE'
            value = filter_match.group(4)
            
            if col_name:
                if operator == 'LIKE':
                    query_parts['where'].append(f"{col_name} LIKE '%{value}%'")
                else:
                    # Check if value is numeric
                    try:
                        float(value)
                        query_parts['where'].append(f"{col_name} = {value}")
                    except:
                        query_parts['where'].append(f"{col_name} = '{value}'")
                confidence += 0.1
        
        # ORDER BY
        order_match = re.search(self.patterns['order'], nl_lower)
        if order_match:
            col_name = self._find_column(order_match.group(2), columns)
            direction = 'DESC' if order_match.group(3) and 'desc' in order_match.group(3).lower() else 'ASC'
            
            if col_name:
                query_parts['order_by'] = [f"{col_name} {direction}"]
                confidence += 0.1
        
        # LIMIT
        limit_match = re.search(self.patterns['limit'], nl_lower)
        if limit_match:
            query_parts['limit'] = int(limit_match.group(2))
        elif not any(word in nl_lower for word in ['all', 'every']):
            query_parts['limit'] = 100  # Default limit
        
        # Build final query
        sql = self._build_sql_from_parts(query_parts)
        
        return SQLQuery(
            query=sql,
            database_name=database_name,
            tables=[table_name],
            confidence=min(confidence, 0.9),
            explanation="Generated using pattern matching"
        )
    
    def _extract_columns_from_schema(self, schema_text: str) -> List[str]:
        """Extract column names from schema text"""
        columns = []
        lines = schema_text.split('\n')
        in_columns_section = False
        
        for line in lines:
            if line.strip() == 'Columns:':
                in_columns_section = True
                continue
            elif line.strip() and not line.startswith(' ') and not line.startswith('-'):
                in_columns_section = False
            
            if in_columns_section and line.strip().startswith('-'):
                # Extract column name
                match = re.match(r'-\s+(\w+)\s+\(', line.strip())
                if match:
                    columns.append(match.group(1))
        
        return columns
    
    def _find_column(self, text: str, columns: List[str]) -> Optional[str]:
        """Find best matching column name"""
        text_lower = text.lower()
        
        # Exact match
        for col in columns:
            if col.lower() == text_lower:
                return col
        
        # Partial match
        for col in columns:
            if text_lower in col.lower() or col.lower() in text_lower:
                return col
        
        # Fuzzy match (simple)
        for col in columns:
            if any(part in col.lower() for part in text_lower.split('_')):
                return col
        
        return None
    
    def _extract_table_names(self, sql: str, schemas: List[Dict[str, Any]]) -> List[str]:
        """Extract table names from SQL query"""
        tables = []
        sql_upper = sql.upper()
        
        for schema in schemas:
            table_name = schema['table_name']
            if table_name.upper() in sql_upper:
                tables.append(table_name)
        
        return tables
    
    def _clean_sql(self, sql: str) -> str:
        """Clean and format SQL query"""
        # Remove markdown code blocks if present
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)
        
        # Remove extra whitespace
        sql = ' '.join(sql.split())
        
        # Ensure semicolon at end
        if not sql.rstrip().endswith(';'):
            sql = sql.rstrip() + ';'
        
        return sql
    
    def _build_sql_from_parts(self, parts: Dict[str, Any]) -> str:
        """Build SQL query from parts"""
        sql_parts = []
        
        # SELECT
        if parts['select']:
            sql_parts.append(f"SELECT {', '.join(parts['select'])}")
        else:
            sql_parts.append("SELECT *")
        
        # FROM
        sql_parts.append(f"FROM {parts['from']}")
        
        # WHERE
        if parts['where']:
            sql_parts.append(f"WHERE {' AND '.join(parts['where'])}")
        
        # GROUP BY
        if parts['group_by']:
            sql_parts.append(f"GROUP BY {', '.join(parts['group_by'])}")
        
        # ORDER BY
        if parts['order_by']:
            sql_parts.append(f"ORDER BY {', '.join(parts['order_by'])}")
        
        # LIMIT
        if parts['limit']:
            sql_parts.append(f"LIMIT {parts['limit']}")
        
        return ' '.join(sql_parts) + ';'
    
    def validate_query(self, query: SQLQuery) -> Tuple[bool, Optional[str]]:
        """Validate generated SQL query"""
        try:
            # Basic SQL injection prevention
            dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE']
            query_upper = query.query.upper()
            
            for keyword in dangerous_keywords:
                if keyword in query_upper:
                    return False, f"Query contains dangerous keyword: {keyword}"
            
            # Check if tables exist
            if query.database_name and query.tables:
                all_tables = self.db_manager.get_table_list(query.database_name)
                for table in query.tables:
                    if table not in all_tables:
                        return False, f"Table '{table}' not found in database"
            
            # Try to parse with pandas (basic validation)
            # This is a simple check, not execution
            if 'SELECT' in query.query.upper():
                return True, None
            
            return False, "Invalid query structure"
            
        except Exception as e:
            return False, str(e)
    
    def execute_query(self, query: SQLQuery, limit: int = 1000) -> pd.DataFrame:
        """Execute generated SQL query safely"""
        # Validate first
        is_valid, error = self.validate_query(query)
        if not is_valid:
            raise ValueError(f"Query validation failed: {error}")
        
        # Execute query
        return self.db_manager.execute_query(
            query.database_name,
            query.query,
            limit=limit
        )

class QueryOptimizer:
    """Optimizes generated SQL queries"""
    
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
    
    def optimize_query(self, query: SQLQuery) -> SQLQuery:
        """Optimize SQL query for better performance"""
        optimized_sql = query.query
        
        # Add index hints if available
        # Add JOIN order optimization
        # Add query hints based on database type
        
        # For now, just ensure LIMIT is present for SELECT queries
        if 'SELECT' in optimized_sql.upper() and 'LIMIT' not in optimized_sql.upper():
            optimized_sql = optimized_sql.rstrip(';') + ' LIMIT 1000;'
        
        return SQLQuery(
            query=optimized_sql,
            database_name=query.database_name,
            tables=query.tables,
            confidence=query.confidence,
            explanation=query.explanation + " (optimized)",
            parameters=query.parameters
        )

# Example usage
if __name__ == "__main__":
    # Initialize generator
    generator = SQLQueryGenerator()
    
    # Test queries
    test_queries = [
        "Show all customers",
        "Count the number of orders",
        "Find products with price greater than 100",
        "Get top 5 most expensive products",
        "Show orders for customer John Doe",
        "What is the average order amount?",
        "List all tables with customer data"
    ]
    
    for nl_query in test_queries:
        print(f"\nNatural Language: {nl_query}")
        
        try:
            sql_query = generator.generate_query(nl_query, database_name="local_sqlite")
            print(f"Generated SQL: {sql_query.query}")
            print(f"Confidence: {sql_query.confidence:.2f}")
            print(f"Tables: {sql_query.tables}")
            
            # Validate
            is_valid, error = generator.validate_query(sql_query)
            print(f"Valid: {is_valid}" + (f" (Error: {error})" if error else ""))
            
        except Exception as e:
            print(f"Error: {e}")