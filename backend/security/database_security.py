import os
import re
import logging
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql, errors as pg_errors
import sqlparse
from sqlparse import tokens
import win32api
import win32security
import win32file
import win32con

logger = logging.getLogger(__name__)

@dataclass
class DatabaseSecurityConfig:
    connection_encryption: bool = True
    enable_ssl: bool = True
    ssl_verify_ca: bool = True
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    ssl_ca_path: Optional[str] = None
    query_timeout: int = 30
    max_query_length: int = 10000
    enable_query_logging: bool = True
    log_sensitive_data: bool = False
    connection_pool_size: int = 20
    enable_row_level_security: bool = True
    enable_audit_triggers: bool = True

class SQLInjectionDetector:
    """Advanced SQL injection detection and prevention"""
    
    def __init__(self):
        self.dangerous_keywords = [
            'DROP', 'DELETE', 'UPDATE', 'INSERT', 'CREATE', 'ALTER', 'EXEC',
            'EXECUTE', 'TRUNCATE', 'GRANT', 'REVOKE', 'UNION', 'INTO',
            'OUTFILE', 'DUMPFILE', 'LOAD_FILE', 'BENCHMARK', 'SLEEP',
            'WAITFOR', 'DELAY', 'xp_', 'sp_', 'fn_'
        ]
        
        self.injection_patterns = [
            r"(\b(OR|AND)\s+[\d\w]+\s*[=<>]\s*[\d\w]+)",
            r"([\'\"][\s]*;[\s]*--)",
            r"([\'\"][\s]*;[\s]*#)",
            r"([\'\"][\s]*;[\s]*/\*)",
            r"(\bUNION\s+(?:ALL\s+)?SELECT)",
            r"(\bSELECT\s+.*\bFROM\s+.*\bWHERE\s+.*[=<>].*[\'\"].*[\'\"])",
            r"([\'\"][\s]*\+[\s]*[\'\"])",
            r"(CONCAT\s*\()",
            r"(CHAR\s*\(\d+\))",
            r"(0x[0-9A-Fa-f]+)",
            r"(\b(CONVERT|CAST)\s*\()",
            r"([\'\"][\s]*OR[\s]+[\'\"].*[\'\"][\s]*=[\s]*[\'\"])",
            r"([\'\"][\s]*AND[\s]+[\'\"].*[\'\"][\s]*=[\s]*[\'\"])",
            r"(\b(WAITFOR|DELAY)\s+TIME)",
            r"(\b(BENCHMARK|SLEEP)\s*\()",
            r"(@@\w+)",
            r"(\bIF\s*\(\s*\d+\s*=\s*\d+)",
            r"(\bCASE\s+WHEN\s+.*\s+THEN)",
            r"(\bEXISTS\s*\(\s*SELECT)",
            r"(\b(SUBSTRING|MID|LEFT|RIGHT)\s*\()"
        ]
        
        self.comment_patterns = [
            r"(--[\s\S]*?$)",
            r"(/\*[\s\S]*?\*/)",
            r"(#[\s\S]*?$)"
        ]
    
    def detect_sql_injection(self, query: str) -> Tuple[bool, List[str], str]:
        """
        Detect SQL injection attempts
        Returns: (is_malicious, detected_patterns, risk_level)
        """
        if not isinstance(query, str):
            return False, [], "low"
        
        detected_patterns = []
        risk_score = 0
        
        # Normalize query
        normalized_query = query.upper().strip()
        
        # Check for dangerous keywords in suspicious contexts
        for keyword in self.dangerous_keywords:
            if keyword in normalized_query:
                # Check if it's in a legitimate context (basic heuristic)
                if not self._is_legitimate_keyword_usage(query, keyword):
                    detected_patterns.append(f"Dangerous keyword: {keyword}")
                    risk_score += 3
        
        # Check injection patterns
        for pattern in self.injection_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                detected_patterns.append(f"Injection pattern: {match.group()}")
                risk_score += 2
        
        # Check for comment-based attacks
        for pattern in self.comment_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                detected_patterns.append(f"Comment injection: {match.group()}")
                risk_score += 1
        
        # Check for multiple statement execution
        statements = sqlparse.split(query)
        if len(statements) > 1:
            detected_patterns.append("Multiple statements detected")
            risk_score += 2
        
        # Determine risk level
        is_malicious = risk_score >= 3
        if risk_score >= 6:
            risk_level = "critical"
        elif risk_score >= 4:
            risk_level = "high"
        elif risk_score >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return is_malicious, detected_patterns, risk_level
    
    def _is_legitimate_keyword_usage(self, query: str, keyword: str) -> bool:
        """Basic heuristic to check if keyword usage is legitimate"""
        # This is a simplified check - in production, you'd want more sophisticated analysis
        try:
            parsed = sqlparse.parse(query)
            if not parsed:
                return False
            
            # Check if it's a simple SELECT statement
            first_token = str(parsed[0].tokens[0]).strip().upper()
            if first_token == 'SELECT' and keyword in ['SELECT', 'FROM', 'WHERE', 'ORDER', 'GROUP']:
                return True
            
            return False
        except:
            return False

class ParameterizedQueryBuilder:
    """Builder for safe parameterized queries"""
    
    def __init__(self):
        self.query_templates = {}
        self._setup_common_templates()
    
    def _setup_common_templates(self):
        """Setup common query templates"""
        self.query_templates = {
            'select_by_id': "SELECT * FROM {} WHERE id = %s",
            'select_by_field': "SELECT * FROM {} WHERE {} = %s",
            'select_with_limit': "SELECT * FROM {} LIMIT %s OFFSET %s",
            'insert_record': "INSERT INTO {} ({}) VALUES ({})",
            'update_by_id': "UPDATE {} SET {} WHERE id = %s",
            'delete_by_id': "DELETE FROM {} WHERE id = %s",
            'count_records': "SELECT COUNT(*) FROM {} WHERE {} = %s",
            'search_text': "SELECT * FROM {} WHERE {} ILIKE %s",
            'select_range': "SELECT * FROM {} WHERE {} BETWEEN %s AND %s",
            'select_in_list': "SELECT * FROM {} WHERE {} = ANY(%s)"
        }
    
    def build_select_query(
        self, 
        table: str, 
        fields: List[str] = None, 
        where_conditions: Dict[str, Any] = None,
        limit: int = None,
        offset: int = None,
        order_by: List[str] = None
    ) -> Tuple[str, List[Any]]:
        """Build a safe SELECT query"""
        
        # Validate table name
        safe_table = self._validate_identifier(table)
        
        # Build SELECT clause
        if fields:
            safe_fields = [self._validate_identifier(f) for f in fields]
            select_clause = ", ".join(safe_fields)
        else:
            select_clause = "*"
        
        query_parts = [f"SELECT {select_clause} FROM {safe_table}"]
        params = []
        
        # Build WHERE clause
        if where_conditions:
            where_clauses = []
            for field, value in where_conditions.items():
                safe_field = self._validate_identifier(field)
                if isinstance(value, (list, tuple)):
                    where_clauses.append(f"{safe_field} = ANY(%s)")
                    params.append(list(value))
                elif value is None:
                    where_clauses.append(f"{safe_field} IS NULL")
                else:
                    where_clauses.append(f"{safe_field} = %s")
                    params.append(value)
            
            if where_clauses:
                query_parts.append("WHERE " + " AND ".join(where_clauses))
        
        # Build ORDER BY clause
        if order_by:
            safe_order_fields = []
            for field in order_by:
                if field.upper().endswith(' DESC'):
                    field_name = field[:-5].strip()
                    safe_field = self._validate_identifier(field_name)
                    safe_order_fields.append(f"{safe_field} DESC")
                elif field.upper().endswith(' ASC'):
                    field_name = field[:-4].strip()
                    safe_field = self._validate_identifier(field_name)
                    safe_order_fields.append(f"{safe_field} ASC")
                else:
                    safe_field = self._validate_identifier(field)
                    safe_order_fields.append(safe_field)
            
            query_parts.append("ORDER BY " + ", ".join(safe_order_fields))
        
        # Build LIMIT and OFFSET
        if limit is not None:
            query_parts.append("LIMIT %s")
            params.append(limit)
            
            if offset is not None:
                query_parts.append("OFFSET %s")
                params.append(offset)
        
        return " ".join(query_parts), params
    
    def build_insert_query(
        self, 
        table: str, 
        data: Dict[str, Any],
        returning: List[str] = None
    ) -> Tuple[str, List[Any]]:
        """Build a safe INSERT query"""
        
        safe_table = self._validate_identifier(table)
        
        fields = list(data.keys())
        safe_fields = [self._validate_identifier(f) for f in fields]
        placeholders = ["%s"] * len(fields)
        params = list(data.values())
        
        query = f"INSERT INTO {safe_table} ({', '.join(safe_fields)}) VALUES ({', '.join(placeholders)})"
        
        if returning:
            safe_returning = [self._validate_identifier(f) for f in returning]
            query += f" RETURNING {', '.join(safe_returning)}"
        
        return query, params
    
    def build_update_query(
        self, 
        table: str, 
        data: Dict[str, Any],
        where_conditions: Dict[str, Any],
        returning: List[str] = None
    ) -> Tuple[str, List[Any]]:
        """Build a safe UPDATE query"""
        
        safe_table = self._validate_identifier(table)
        
        # Build SET clause
        set_clauses = []
        params = []
        
        for field, value in data.items():
            safe_field = self._validate_identifier(field)
            set_clauses.append(f"{safe_field} = %s")
            params.append(value)
        
        query = f"UPDATE {safe_table} SET {', '.join(set_clauses)}"
        
        # Build WHERE clause
        if where_conditions:
            where_clauses = []
            for field, value in where_conditions.items():
                safe_field = self._validate_identifier(field)
                where_clauses.append(f"{safe_field} = %s")
                params.append(value)
            
            query += " WHERE " + " AND ".join(where_clauses)
        
        if returning:
            safe_returning = [self._validate_identifier(f) for f in returning]
            query += f" RETURNING {', '.join(safe_returning)}"
        
        return query, params
    
    def _validate_identifier(self, identifier: str) -> str:
        """Validate and quote SQL identifier"""
        if not isinstance(identifier, str):
            raise ValueError("Identifier must be a string")
        
        # Remove any existing quotes
        clean_identifier = identifier.strip().strip('"').strip("'")
        
        # Check for valid identifier pattern
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', clean_identifier):
            raise ValueError(f"Invalid identifier: {identifier}")
        
        # Quote the identifier to prevent injection
        return f'"{clean_identifier}"'

class WindowsDatabaseSecurity:
    """Comprehensive database security for Windows deployment"""
    
    def __init__(self, config: DatabaseSecurityConfig = None):
        self.config = config or DatabaseSecurityConfig()
        self.injection_detector = SQLInjectionDetector()
        self.query_builder = ParameterizedQueryBuilder()
        self.connection_pool = None
        
        # Query audit log
        self.query_log = []
        self.max_log_entries = 1000
        
        # Connection security
        self._setup_connection_security()
    
    def _setup_connection_security(self):
        """Setup connection security parameters"""
        self.connection_params = {
            'connect_timeout': 10,
            'application_name': 'MIDAS_Security',
            'options': '-c default_transaction_isolation=serializable'
        }
        
        if self.config.connection_encryption:
            self.connection_params['sslmode'] = 'require'
            
        if self.config.enable_ssl:
            if self.config.ssl_verify_ca:
                self.connection_params['sslmode'] = 'verify-ca'
            
            if self.config.ssl_cert_path:
                self.connection_params['sslcert'] = self.config.ssl_cert_path
            
            if self.config.ssl_key_path:
                self.connection_params['sslkey'] = self.config.ssl_key_path
            
            if self.config.ssl_ca_path:
                self.connection_params['sslrootcert'] = self.config.ssl_ca_path
    
    def create_connection_pool(
        self, 
        host: str,
        database: str,
        user: str,
        password: str,
        port: int = 5432
    ) -> psycopg2.pool.ThreadedConnectionPool:
        """Create secure connection pool"""
        
        connection_kwargs = {
            'host': host,
            'database': database,
            'user': user,
            'password': password,
            'port': port,
            **self.connection_params
        }
        
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config.connection_pool_size,
                **connection_kwargs
            )
            
            logger.info("Secure database connection pool created")
            return self.connection_pool
            
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    @contextmanager
    def get_secure_connection(self):
        """Get secure database connection from pool"""
        if not self.connection_pool:
            raise RuntimeError("Connection pool not initialized")
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            conn.autocommit = False
            
            # Set session security parameters
            with conn.cursor() as cursor:
                cursor.execute("SET statement_timeout = %s", (self.config.query_timeout * 1000,))
                cursor.execute("SET lock_timeout = %s", (self.config.query_timeout * 1000,))
                cursor.execute("SET idle_in_transaction_session_timeout = %s", (300000,))  # 5 minutes
            
            yield conn
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
    def execute_safe_query(
        self,
        query: str,
        params: Tuple = None,
        fetch: str = 'none',
        connection=None
    ) -> Any:
        """Execute query with security validation"""
        
        # Validate query length
        if len(query) > self.config.max_query_length:
            raise ValueError(f"Query too long (max {self.config.max_query_length} characters)")
        
        # Detect SQL injection
        is_malicious, patterns, risk_level = self.injection_detector.detect_sql_injection(query)
        
        if is_malicious:
            logger.error(f"SQL injection detected: {patterns}")
            raise SecurityError(f"Malicious SQL detected: {patterns}")
        
        if risk_level in ['medium', 'high']:
            logger.warning(f"Suspicious SQL query (risk: {risk_level}): {patterns}")
        
        # Log query if enabled
        if self.config.enable_query_logging:
            self._log_query(query, params, risk_level)
        
        # Execute query
        if connection:
            return self._execute_query(connection, query, params, fetch)
        else:
            with self.get_secure_connection() as conn:
                return self._execute_query(conn, query, params, fetch)
    
    def _execute_query(self, connection, query: str, params: Tuple, fetch: str):
        """Execute the actual query"""
        try:
            with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch == 'all':
                    return cursor.fetchall()
                elif fetch == 'one':
                    return cursor.fetchone()
                elif fetch == 'many':
                    return cursor.fetchmany()
                else:
                    return cursor.rowcount
        
        except pg_errors.Error as e:
            logger.error(f"Database error: {e}")
            raise DatabaseSecurityError(f"Database operation failed: {e}")
    
    def safe_select(
        self,
        table: str,
        fields: List[str] = None,
        where_conditions: Dict[str, Any] = None,
        limit: int = None,
        offset: int = None,
        order_by: List[str] = None,
        connection=None
    ) -> List[Dict]:
        """Perform safe SELECT operation"""
        
        query, params = self.query_builder.build_select_query(
            table, fields, where_conditions, limit, offset, order_by
        )
        
        return self.execute_safe_query(query, params, 'all', connection)
    
    def safe_insert(
        self,
        table: str,
        data: Dict[str, Any],
        returning: List[str] = None,
        connection=None
    ) -> Optional[Dict]:
        """Perform safe INSERT operation"""
        
        query, params = self.query_builder.build_insert_query(table, data, returning)
        
        if returning:
            return self.execute_safe_query(query, params, 'one', connection)
        else:
            return self.execute_safe_query(query, params, 'none', connection)
    
    def safe_update(
        self,
        table: str,
        data: Dict[str, Any],
        where_conditions: Dict[str, Any],
        returning: List[str] = None,
        connection=None
    ) -> Union[int, Dict]:
        """Perform safe UPDATE operation"""
        
        query, params = self.query_builder.build_update_query(table, data, where_conditions, returning)
        
        if returning:
            return self.execute_safe_query(query, params, 'one', connection)
        else:
            return self.execute_safe_query(query, params, 'none', connection)
    
    def safe_delete(
        self,
        table: str,
        where_conditions: Dict[str, Any],
        connection=None
    ) -> int:
        """Perform safe DELETE operation"""
        
        safe_table = self.query_builder._validate_identifier(table)
        
        where_clauses = []
        params = []
        
        for field, value in where_conditions.items():
            safe_field = self.query_builder._validate_identifier(field)
            where_clauses.append(f"{safe_field} = %s")
            params.append(value)
        
        if not where_clauses:
            raise ValueError("DELETE requires WHERE conditions")
        
        query = f"DELETE FROM {safe_table} WHERE {' AND '.join(where_clauses)}"
        
        return self.execute_safe_query(query, params, 'none', connection)
    
    def _log_query(self, query: str, params: Tuple, risk_level: str):
        """Log query for audit purposes"""
        log_entry = {
            'timestamp': datetime.now(),
            'query': query if not self.config.log_sensitive_data else query[:100] + '...',
            'params_count': len(params) if params else 0,
            'risk_level': risk_level,
            'user': self._get_current_user()
        }
        
        self.query_log.append(log_entry)
        
        # Rotate log if too large
        if len(self.query_log) > self.max_log_entries:
            self.query_log = self.query_log[-self.max_log_entries//2:]
    
    def _get_current_user(self) -> str:
        """Get current Windows user"""
        try:
            return win32api.GetUserName()
        except:
            return "unknown"
    
    def setup_database_security(self, connection):
        """Setup database-level security features"""
        
        security_queries = []
        
        if self.config.enable_row_level_security:
            security_queries.extend([
                "ALTER SYSTEM SET row_security = on;",
                "SELECT pg_reload_conf();"
            ])
        
        if self.config.enable_audit_triggers:
            # Create audit log table
            security_queries.append("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    table_name VARCHAR(64) NOT NULL,
                    operation VARCHAR(10) NOT NULL,
                    old_values JSONB,
                    new_values JSONB,
                    user_name VARCHAR(64) NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    client_ip INET
                );
            """)
            
            # Create audit trigger function
            security_queries.append("""
                CREATE OR REPLACE FUNCTION audit_trigger_function()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        INSERT INTO audit_log (table_name, operation, old_values, user_name, client_ip)
                        VALUES (TG_TABLE_NAME, TG_OP, row_to_json(OLD), session_user, inet_client_addr());
                        RETURN OLD;
                    ELSIF TG_OP = 'UPDATE' THEN
                        INSERT INTO audit_log (table_name, operation, old_values, new_values, user_name, client_ip)
                        VALUES (TG_TABLE_NAME, TG_OP, row_to_json(OLD), row_to_json(NEW), session_user, inet_client_addr());
                        RETURN NEW;
                    ELSIF TG_OP = 'INSERT' THEN
                        INSERT INTO audit_log (table_name, operation, new_values, user_name, client_ip)
                        VALUES (TG_TABLE_NAME, TG_OP, row_to_json(NEW), session_user, inet_client_addr());
                        RETURN NEW;
                    END IF;
                    RETURN NULL;
                END;
                $$ LANGUAGE plpgsql;
            """)
        
        # Execute security setup queries
        for query in security_queries:
            try:
                self.execute_safe_query(query, connection=connection)
                logger.info(f"Executed security setup query: {query[:50]}...")
            except Exception as e:
                logger.error(f"Failed to execute security query: {e}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get database security statistics"""
        return {
            'config': {
                'connection_encryption': self.config.connection_encryption,
                'ssl_enabled': self.config.enable_ssl,
                'query_timeout': self.config.query_timeout,
                'connection_pool_size': self.config.connection_pool_size,
                'row_level_security': self.config.enable_row_level_security
            },
            'audit_log_entries': len(self.query_log),
            'recent_queries': len([log for log in self.query_log if log['timestamp'] > datetime.now() - timedelta(hours=1)]),
            'high_risk_queries': len([log for log in self.query_log if log['risk_level'] in ['high', 'critical']]),
            'pool_available': self.connection_pool.closed == 0 if self.connection_pool else False
        }

class SecurityError(Exception):
    """Security-related error"""
    pass

class DatabaseSecurityError(Exception):
    """Database security error"""
    pass

# Global database security instance
db_security_instance: Optional[WindowsDatabaseSecurity] = None

def initialize_database_security(config: DatabaseSecurityConfig = None) -> WindowsDatabaseSecurity:
    """Initialize global database security"""
    global db_security_instance
    db_security_instance = WindowsDatabaseSecurity(config)
    return db_security_instance

def get_database_security() -> WindowsDatabaseSecurity:
    """Get global database security instance"""
    if db_security_instance is None:
        initialize_database_security()
    return db_security_instance