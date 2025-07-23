"""
MIDAS Authenticated Chat Application
Streamlit app with Windows-native authentication and user management
"""

import streamlit as st
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.exceptions import (
    CredentialsError,
    ForgotError,
    LoginError,
    RegisterError,
    ResetError,
    UpdateError
)
import yaml
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import our modules
from windows_auth_system import WindowsAuthenticationSystem, WindowsUserDatabase
from enhanced_chat_app import (
    initialize_enhanced_session_state,
    enhanced_sidebar_configuration,
    create_enhanced_search_results_display,
    construct_enhanced_context_prompt,
    ConversationMemory,
    EnhancedRAGSystem,
    WindowsFileHandler
)
from visualization_chat_app import (
    initialize_visualization_session_state,
    display_visualization_result,
    process_chat_with_visualization,
    VisualizationRequestDetector
)

class AuthenticatedStreamlitApp:
    """Main authenticated Streamlit application"""
    
    def __init__(self):
        self.auth_system = WindowsAuthenticationSystem()
        self.authenticator = None
        self._init_authenticator()
    
    def _init_authenticator(self):
        """Initialize streamlit-authenticator"""
        try:
            config = self.auth_system.get_streamlit_config()
            
            self.authenticator = stauth.Authenticate(
                config['credentials'],
                config['cookie']['name'],
                config['cookie']['key'],
                config['cookie']['expiry_days'],
                config['preauthorized']
            )
        except Exception as e:
            st.error(f"Authentication system initialization failed: {e}")
            st.stop()
    
    def render_authentication_sidebar(self):
        """Render authentication controls in sidebar"""
        with st.sidebar:
            st.markdown("---")
            st.subheader("👤 User Account")
            
            if st.session_state.get("authentication_status"):
                # User is logged in
                user_info = st.session_state.get("user_info", {})
                st.success(f"Welcome, {user_info.get('username', 'User')}!")
                st.write(f"**Role**: {user_info.get('role', 'user').title()}")
                st.write(f"**Email**: {user_info.get('email', 'Not provided')}")
                
                # User preferences
                with st.expander("⚙️ User Preferences", expanded=False):
                    self._render_user_preferences()
                
                # Admin functions
                if user_info.get('role') == 'admin':
                    with st.expander("👑 Admin Functions", expanded=False):
                        self._render_admin_functions()
                
                # Logout button
                if st.button("🚪 Logout"):
                    self.logout_user()
            else:
                st.info("Please log in to access the application")
    
    def _render_user_preferences(self):
        """Render user preferences interface"""
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            return
        
        # Get current preferences
        preferences = self.auth_system.user_db.get_user_preferences(user_id)
        
        # Theme preference
        current_theme = preferences.get("theme", "default")
        theme = st.selectbox(
            "App Theme",
            ["default", "dark", "light"],
            index=["default", "dark", "light"].index(current_theme)
        )
        
        if theme != current_theme:
            self.auth_system.user_db.set_user_preference(user_id, "theme", theme)
            st.success("Theme preference saved!")
        
        # Default chart style
        current_chart_style = preferences.get("chart_style", "professional")
        chart_style = st.selectbox(
            "Default Chart Style",
            ["professional", "vibrant", "pastel", "default"],
            index=["professional", "vibrant", "pastel", "default"].index(current_chart_style)
        )
        
        if chart_style != current_chart_style:
            self.auth_system.user_db.set_user_preference(user_id, "chart_style", chart_style)
            st.success("Chart style preference saved!")
        
        # Auto-save conversations
        auto_save = st.checkbox(
            "Auto-save conversations",
            value=preferences.get("auto_save_conversations", True)
        )
        
        if auto_save != preferences.get("auto_save_conversations", True):
            self.auth_system.user_db.set_user_preference(user_id, "auto_save_conversations", auto_save)
            st.success("Auto-save preference updated!")
        
        # Change password section
        st.markdown("**Change Password**")
        with st.form("change_password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            if st.form_submit_button("Change Password"):
                if not current_password or not new_password:
                    st.error("Please fill in all fields")
                elif new_password != confirm_password:
                    st.error("New passwords do not match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters long")
                else:
                    # Verify current password
                    user_data = self.auth_system.user_db.authenticate_user(
                        user_info["username"], current_password
                    )
                    if user_data:
                        if self.auth_system.user_db.change_password(user_id, new_password):
                            st.success("Password changed successfully!")
                        else:
                            st.error("Failed to change password")
                    else:
                        st.error("Current password is incorrect")
    
    def _render_admin_functions(self):
        """Render admin-only functions"""
        st.markdown("**User Management**")
        
        # Create new user
        with st.form("create_user_form"):
            st.write("Create New User")
            new_username = st.text_input("Username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            
            if st.form_submit_button("Create User"):
                if new_username and new_password:
                    success, message = self.auth_system.register_user(
                        new_username, new_password, new_email
                    )
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.error("Username and password are required")
        
        # System statistics
        with self.auth_system.user_db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = TRUE")
            active_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE last_login > datetime('now', '-7 days')")
            weekly_active = cursor.fetchone()['count']
        
        st.write(f"**Active Users**: {active_users}")
        st.write(f"**Weekly Active**: {weekly_active}")
        
        # Database maintenance
        if st.button("Clean up expired sessions"):
            self.auth_system.session_manager._cleanup_expired_sessions()
            st.success("Session cleanup completed")
    
    def render_login_page(self):
        """Render login/registration page"""
        st.title("🔐 MIDAS Authentication")
        st.markdown("**Secure Windows-based RAG Chat System**")
        
        tab1, tab2, tab3 = st.tabs(["🔑 Login", "📝 Register", "🔄 Reset Password"])
        
        with tab1:
            # Login form
            try:
                name, authentication_status, username = self.authenticator.login('Login', 'main')
                
                if authentication_status == False:
                    st.error('Username/password is incorrect')
                elif authentication_status == None:
                    st.warning('Please enter your username and password')
                elif authentication_status:
                    # Get full user data from our database
                    user_data = self.auth_system.user_db.authenticate_user(username, "dummy")
                    if not user_data:
                        # Try to get user data by username lookup
                        with self.auth_system.user_db._get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
                            user_row = cursor.fetchone()
                            if user_row:
                                user_data = {
                                    'id': user_row['id'],
                                    'username': user_row['username'],
                                    'email': user_row['email'],
                                    'role': user_row['role'],
                                    'created_at': user_row['created_at'],
                                    'last_login': user_row['last_login']
                                }
                    
                    st.session_state["user_info"] = user_data or {"username": username}
                    st.rerun()
                    
            except LoginError as e:
                st.error(e)
        
        with tab2:
            # Registration form
            st.subheader("Create New Account")
            
            with st.form("registration_form"):
                reg_username = st.text_input("Choose Username")
                reg_email = st.text_input("Email Address")
                reg_password = st.text_input("Password", type="password")
                reg_confirm = st.text_input("Confirm Password", type="password")
                
                if st.form_submit_button("Register"):
                    if not reg_username or not reg_password:
                        st.error("Username and password are required")
                    elif reg_password != reg_confirm:
                        st.error("Passwords do not match")
                    elif len(reg_password) < 6:
                        st.error("Password must be at least 6 characters")
                    else:
                        success, message = self.auth_system.register_user(
                            reg_username, reg_password, reg_email
                        )
                        if success:
                            st.success(message + " Please log in.")
                        else:
                            st.error(message)
        
        with tab3:
            # Password reset form
            st.subheader("Reset Password")
            
            with st.form("reset_password_form"):
                reset_username = st.text_input("Username")
                reset_token = st.text_input("Reset Token (if you have one)")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.form_submit_button("Request Reset Token"):
                        if reset_username:
                            token = self.auth_system.user_db.create_password_reset_token(reset_username)
                            if token:
                                st.success(f"Reset token generated: {token}")
                                st.info("Copy this token and use it below to reset your password.")
                            else:
                                st.error("Username not found")
                        else:
                            st.error("Please enter username")
                
                with col2:
                    new_password = st.text_input("New Password", type="password")
                    if st.form_submit_button("Reset Password"):
                        if reset_token and new_password:
                            if len(new_password) < 6:
                                st.error("Password must be at least 6 characters")
                            else:
                                if self.auth_system.user_db.reset_password_with_token(reset_token, new_password):
                                    st.success("Password reset successfully! Please log in.")
                                else:
                                    st.error("Invalid or expired token")
                        else:
                            st.error("Please enter token and new password")
    
    def logout_user(self):
        """Logout current user"""
        # Clear streamlit-authenticator session
        st.session_state["authentication_status"] = None
        st.session_state["name"] = None
        st.session_state["username"] = None
        st.session_state["user_info"] = None
        
        # Clear our custom session data
        if "messages" in st.session_state:
            st.session_state.messages = []
        if "conversation_memory" in st.session_state:
            st.session_state.conversation_memory.clear_memory()
        if "visualization_history" in st.session_state:
            st.session_state.visualization_history = []
        
        st.success("Logged out successfully!")
        st.rerun()
    
    def run(self):
        """Main application runner"""
        # Configure page
        st.set_page_config(
            page_title="MIDAS Authenticated Chat",
            page_icon="🔐",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Initialize authentication state
        if "authentication_status" not in st.session_state:
            st.session_state["authentication_status"] = None
        
        # Check authentication status
        if not st.session_state.get("authentication_status"):
            self.render_login_page()
            return
        
        # User is authenticated - show main app
        self.render_main_application()
    
    def render_main_application(self):
        """Render the main authenticated application"""
        # Initialize session state for authenticated features
        initialize_visualization_session_state()
        
        # Custom sidebar with authentication
        self.render_custom_authenticated_sidebar()
        
        # Main content
        st.title("🤖 MIDAS Authenticated RAG Chat")
        st.markdown("*Secure chat with your data and instant visualizations*")
        
        # Show user info
        user_info = st.session_state.get("user_info", {})
        st.info(f"Welcome back, **{user_info.get('username', 'User')}**! You have **{user_info.get('role', 'user')}** access.")
        
        # Display chat messages with visualization support
        self.display_authenticated_chat_messages()
        
        # Chat input
        if prompt := st.chat_input("Ask about your data or request visualizations..."):
            if not st.session_state.ollama_chat.is_available():
                st.error("❌ Ollama service not available")
                st.stop()
            
            if not st.session_state.available_models:
                st.error("❌ No models available")
                st.stop()
            
            # Process the chat message with user context
            self.process_authenticated_chat_message(prompt)
    
    def render_custom_authenticated_sidebar(self):
        """Custom sidebar with authentication integration"""
        with st.sidebar:
            # Authentication section
            self.render_authentication_sidebar()
            
            # Standard app configuration
            st.markdown("---")
            st.title("🤖 MIDAS Chat")
            
            # System Information
            st.subheader("💻 System Status")
            rag_system = st.session_state.enhanced_rag_system
            
            with st.expander("System Specs", expanded=False):
                specs = rag_system.specs
                st.write(f"**Device**: {rag_system.device}")
                st.write(f"**CPU**: {specs.get('cpu_cores', 'Unknown')} cores")
                st.write(f"**RAM**: {specs.get('memory_gb', 'Unknown')} GB")
            
            # User-specific settings
            user_info = st.session_state.get("user_info", {})
            user_id = user_info.get("id")
            preferences = {}
            
            if user_id:
                preferences = self.auth_system.user_db.get_user_preferences(user_id)
            
            # Apply user preferences to config
            if preferences:
                st.session_state.config["chart_style"] = preferences.get("chart_style", "professional")
            
            # Visualization settings
            st.subheader("📊 Visualization Settings")
            
            auto_detect_viz = st.checkbox(
                "Auto-detect visualization requests",
                value=True,
                help="Automatically generate charts when visualization intent is detected"
            )
            st.session_state.config["auto_detect_visualization"] = auto_detect_viz
            
            # Chart style from preferences
            chart_style = st.selectbox(
                "Chart Style",
                ["professional", "vibrant", "pastel", "default"],
                index=["professional", "vibrant", "pastel", "default"].index(
                    preferences.get("chart_style", "professional")
                )
            )
            st.session_state.config["chart_style"] = chart_style
            
            # Services status
            st.subheader("🔧 Services")
            
            # Ollama status
            if st.session_state.ollama_chat.is_available():
                st.success("✅ Ollama Connected")
                
                if not st.session_state.available_models:
                    st.session_state.available_models = st.session_state.ollama_chat.get_available_models()
                
                if st.session_state.available_models:
                    selected_model = st.selectbox(
                        "Model",
                        st.session_state.available_models,
                        index=0 if st.session_state.config["default_model"] not in st.session_state.available_models 
                        else st.session_state.available_models.index(st.session_state.config["default_model"])
                    )
                    st.session_state.config["default_model"] = selected_model
            else:
                st.error("❌ Ollama Disconnected")
            
            # Enhanced RAG status
            if rag_system.doc_indexer:
                try:
                    status = rag_system.doc_indexer.get_system_status()
                    if status.get('status') == 'connected':
                        st.success("✅ RAG System Ready")
                        
                        # Show visualization history
                        if st.session_state.visualization_history:
                            with st.expander("📈 Recent Visualizations", expanded=False):
                                for i, viz in enumerate(reversed(st.session_state.visualization_history[-5:])):
                                    st.write(f"• {viz['request'][:50]}...")
                except Exception:
                    st.warning("⚠️ RAG System Issues")
            
            # Configuration
            st.subheader("⚙️ Settings")
            
            enable_rag = st.checkbox(
                "Enable RAG Search",
                value=st.session_state.config.get("enable_rag", True)
            )
            st.session_state.config["enable_rag"] = enable_rag
            
            if enable_rag:
                rag_max_results = st.slider(
                    "Max Search Results",
                    min_value=1,
                    max_value=15,
                    value=st.session_state.config.get("rag_max_results", 5)
                )
                st.session_state.config["rag_max_results"] = rag_max_results
            
            temperature = st.slider(
                "Response Creativity",
                min_value=0.0,
                max_value=2.0,
                value=st.session_state.config.get("temperature", 0.7),
                step=0.1
            )
            st.session_state.config["temperature"] = temperature
            
            # Conversation Management
            st.subheader("💬 Management")
            
            if st.button("🗑️ Clear Chat"):
                st.session_state.messages = []
                st.session_state.conversation_memory.clear_memory()
                st.session_state.visualization_history = []
                st.rerun()
    
    def display_authenticated_chat_messages(self):
        """Display chat messages with user context"""
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
                
                # Display visualization if present
                if message["role"] == "assistant" and message.get("chart_generated"):
                    viz_result = message.get("visualization_result")
                    if viz_result:
                        display_visualization_result(viz_result, "Previous request")
                
                # Display regular search results
                elif message["role"] == "assistant" and "search_results" in message:
                    create_enhanced_search_results_display(
                        message["search_results"], 
                        message.get("debug_info")
                    )
    
    def process_authenticated_chat_message(self, prompt: str):
        """Process chat message with user authentication context"""
        user_info = st.session_state.get("user_info", {})
        
        # Add user context to the conversation
        enhanced_prompt = f"[User: {user_info.get('username', 'Anonymous')} | Role: {user_info.get('role', 'user')}] {prompt}"
        
        # Use the existing visualization chat processing
        process_chat_with_visualization(enhanced_prompt)
        
        # Auto-save conversation if enabled
        user_id = user_info.get("id")
        if user_id:
            preferences = self.auth_system.user_db.get_user_preferences(user_id)
            if preferences.get("auto_save_conversations", True):
                self._save_conversation_to_user_history(user_id, prompt)
    
    def _save_conversation_to_user_history(self, user_id: int, message: str):
        """Save conversation to user history"""
        # This could be extended to save full conversation history
        conversation_data = {
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "model": st.session_state.config.get("default_model", "unknown")
        }
        
        self.auth_system.user_db.set_user_preference(
            user_id, 
            f"last_conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}", 
            conversation_data
        )

def main():
    """Main function to run the authenticated application"""
    app = AuthenticatedStreamlitApp()
    app.run()

if __name__ == "__main__":
    main()