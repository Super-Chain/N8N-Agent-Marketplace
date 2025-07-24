import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv  # type: ignore

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

try:
    from supabase import create_client, Client  # type: ignore
    SUPABASE_AVAILABLE = True
except ImportError:
    print("WARNING: Supabase module not available. Running in development mode.")
    SUPABASE_AVAILABLE = False

class SupabaseManager:
    """
    Manages Supabase database operations for N8N workflows and user credentials
    
    UNIFIED DATABASE SCHEMA:
    
    Both n8n_workflows and user_workflows tables should have the same structure:
    
    COMMON FIELDS:
    - id: Primary key (auto-generated)
    - user_id: UUID of the user who imported/uploaded the workflow
    - template_id: Unique identifier
      * For n8n workflows: the n8n.io template ID (numeric)
      * For user uploads: generated as "user-{user_id}-{uuid}"
    - template_url: Source URL
      * For n8n workflows: the n8n.io URL (e.g., "https://n8n.io/workflows/123")
      * For user uploads: synthetic URL (e.g., "user-upload://user-123-abc8")
    - workflow_name: Display name for the workflow
    - workflow_description: Description text
    - workflow_json: The actual N8N workflow data (JSON)
    - n8n_workflow_id: ID when deployed to an N8N instance (nullable)
    - created_at, updated_at: Timestamps
    - status: Workflow status (active, pending, etc.)
    - source: Source type ('n8n_marketplace' or 'user_upload')
    
    DIFFERENCES IN USAGE:
    - user_workflows: For workflows uploaded directly by users via file upload
    """
    
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')
        self.supabase_service_key = os.getenv('SUPABASE_SERVICE_KEY')  # Service role key for admin operations
        self.n8n_api_key = os.getenv('X_N8N_API_KEY')
        self.n8n_base_url = os.getenv('N8N_BASE_URL', 'https://n8n.yourdomain.com')
        
        self.supabase: Optional[Client] = None  # Add Optional type hint
        self.supabase_admin: Optional[Client] = None  # Admin client with service role
        self.development_mode = not SUPABASE_AVAILABLE or self.supabase is None
        
        if SUPABASE_AVAILABLE and self.supabase_url and self.supabase_key:
            self.supabase = create_client(self.supabase_url, self.supabase_key)
            print(f"✅ Connected to Supabase database at {self.supabase_url}")
            
            # Create admin client with service role key if available
            if self.supabase_service_key:
                self.supabase_admin = create_client(self.supabase_url, self.supabase_service_key)
                print(f"✅ Connected to Supabase with service role (admin access)")
            else:
                print("⚠️ SUPABASE_SERVICE_KEY not set, using regular key (may hit RLS policies)")
                self.supabase_admin = self.supabase
        else:
            print("❌ ERROR: Supabase connection failed. Please check environment variables:")
            print(f"   SUPABASE_URL: {'✅ Set' if self.supabase_url else '❌ Missing'}")
            print(f"   SUPABASE_KEY: {'✅ Set' if self.supabase_key else '❌ Missing'}")
            print(f"   SUPABASE_SERVICE_KEY: {'✅ Set' if self.supabase_service_key else '❌ Missing'}")
            print(f"   Supabase module: {'✅ Available' if SUPABASE_AVAILABLE else '❌ Not installed'}")
    
    def init_database(self):
        """Initialize database tables if they don't exist"""
        try:
            # Always initialize Supabase database
            if not SUPABASE_AVAILABLE:
                print("ERROR: Supabase not available, cannot initialize database")
                return False
                
            print("Initializing Supabase database")
            # This would typically be done via Supabase SQL editor or migrations
            # For now, we'll assume tables exist
            print("Database initialized")
            return True
        except Exception as e:
            print(f"Error initializing database: {e}")
            return False
    
    
    # N8N Workflow Management
    def check_workflow_exists(self, template_url: str, template_id: Optional[str] = None) -> Optional[Dict]:
        """Check if N8N template has been processed before"""
        try:
            if not self.supabase:
                print("ERROR: Supabase not available, cannot check workflow existence")
                return None
                
            print(f"Checking workflow existence for {template_url} in Supabase database")
                
            # First try exact URL match
            result = self.supabase.table('user_workflows').select('*').eq('template_url', template_url).execute()  # type: ignore
            if result.data:
                return result.data[0]
            
            # If template_id provided, try matching by template_id
            if template_id:
                result = self.supabase.table('user_workflows').select('*').eq('template_id', template_id).execute()  # type: ignore
                if result.data:
                    return result.data[0]
            
            # Try to extract template_id from URL and search by that
            import re
            url_match = re.search(r'workflows/(\d+)', template_url)
            if url_match:
                extracted_id = url_match.group(1)
                result = self.supabase.table('user_workflows').select('*').eq('template_id', extracted_id).execute()  # type: ignore
                if result.data:
                    return result.data[0]
            
            return None
        except Exception as e:
            print(f"Error checking workflow existence: {e}")
            return None
    
    def check_deployed_workflow_exists(self, user_id: str, workflow_name: str, n8n_workflow_id: Optional[str] = None) -> bool:
        """Check if a deployed workflow already exists in user_workflows to avoid duplicates"""
        try:
            if not self.supabase:
                return False
            
            # Check by workflow name and user
            result = self.supabase.table('user_workflows').select('id').eq('user_id', user_id).eq('workflow_name', workflow_name).execute()  # type: ignore
            
            if result.data:
                print(f"🔍 Found existing deployed workflow '{workflow_name}' for user {user_id}")
                return True
            
            # If n8n_workflow_id provided, also check by that
            if n8n_workflow_id:
                result = self.supabase.table('user_workflows').select('id').eq('user_id', user_id).eq('n8n_workflow_id', n8n_workflow_id).execute()  # type: ignore
                
                if result.data:
                    print(f"🔍 Found existing deployed workflow with n8n_id '{n8n_workflow_id}' for user {user_id}")
                    return True
            
            return False
        except Exception as e:
            print(f"Error checking deployed workflow existence: {e}")
            return False
    
    def save_n8n_workflow(self, template_id: str, template_url: str, workflow_name: str, 
                         workflow_json: Dict, n8n_workflow_id: Optional[str] = None, 
                         credentials_required: Optional[List[str]] = None, user_id: Optional[str] = None,
                         workflow_description: Optional[str] = None) -> bool:
        """Save N8N workflow information to database with unified schema"""
        try:
            if not self.supabase:
                print("ERROR: Supabase not available, cannot save workflow")
                return False
            
            print(f"Saving N8N workflow '{workflow_name}' to Supabase database")
                
            workflow_data = {
                'user_id': user_id,  # Add user_id for consistency
                'template_id': template_id,
                'template_url': template_url,
                'workflow_name': workflow_name,
                'workflow_description': workflow_description or f"N8N workflow template (Template ID: {template_id})",
                'workflow_json': workflow_json,
                'n8n_workflow_id': n8n_workflow_id,
                'credentials_required': json.dumps(credentials_required or []),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'status': 'active' if n8n_workflow_id else 'pending',
                'source': 'n8n_marketplace'
            }
            
            # Check if workflow exists and update, otherwise insert
            existing = self.check_workflow_exists(template_url, template_id)
            
            if existing:
                workflow_data['updated_at'] = datetime.now().isoformat()
                result = self.supabase.table('user_workflows').update(workflow_data).eq('template_url', template_url).execute()  # type: ignore
            else:
                result = self.supabase.table('user_workflows').insert(workflow_data).execute()  # type: ignore
            
            return True
        except Exception as e:
            print(f"Error saving N8N workflow: {e}")
            return False
    
    def update_marketplace_workflow_n8n_id(self, template_url: str, n8n_workflow_id: str) -> bool:
        """Update the N8N workflow ID after successful creation in marketplace workflows table"""
        try:
            if self.supabase is None:
                print("Supabase not available")
                return False
                
            result = self.supabase.table('user_workflows').update({
                'n8n_workflow_id': n8n_workflow_id,
                'status': 'active',
                'updated_at': datetime.now().isoformat()
            }).eq('template_url', template_url).execute()  # type: ignore
            
            return True
        except Exception as e:
            print(f"Error updating workflow N8N ID: {e}")
            return False
    
    def get_user_workflows(self, user_id: str) -> List[Dict]:
        """Get workflows created by a user"""
        try:
            if self.supabase is None:
                print("Supabase not available")
                return []
                
            result = self.supabase.table('user_workflows').select('*').eq('user_id', user_id).execute()  # type: ignore
            
            workflows = []
            for workflow in result.data:
                workflows.append(workflow)
            
            return workflows
        except Exception as e:
            print(f"Error getting user workflows: {e}")
            return []
    
    def save_user_workflow(self, user_id: str, template_url: str, credentials_used: Optional[Dict] = None) -> bool:
        """Save a workflow to user's collection"""
        try:
            if not self.supabase:
                print("ERROR: Supabase not available, cannot save user workflow")
                return False
                
            print(f"Saving user workflow for {user_id} to Supabase database")
                
            workflow_data = {
                'user_id': user_id,
                'template_url': template_url,
                'credentials_used': json.dumps(credentials_used or {}),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.supabase.table('user_workflows').insert(workflow_data).execute()  # type: ignore
            return True
        except Exception as e:
            print(f"Error saving user workflow: {e}")
            return False

    # N8N API Integration
    def create_n8n_workflow(self, workflow_json: Dict, workflow_name: str) -> Optional[str]:
        """Create workflow in N8N instance via API"""
        try:
            import requests
            
            if not self.n8n_api_key:
                print("N8N API key not configured")
                return None
            
            headers = {
                'X-N8N-API-KEY': self.n8n_api_key,
                'Content-Type': 'application/json'
            }
            
            # Prepare workflow data for N8N API
            n8n_payload = {
                'name': workflow_name,
                'nodes': workflow_json.get('nodes', []),
                'connections': workflow_json.get('connections', {}),
                'settings': workflow_json.get('settings', {})
            }
            
            response = requests.post(
                f"{self.n8n_base_url}/api/v1/workflows",
                headers=headers,
                json=n8n_payload,
                timeout=30
            )
            
            if response.status_code == 201:
                workflow_data = response.json()
                return workflow_data.get('id')
            else:
                print(f"Error creating N8N workflow: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error creating N8N workflow: {e}")
            return None
    
    def update_n8n_workflow_credentials(self, n8n_workflow_id: str, credentials: Dict) -> bool:
        """Update N8N workflow with user credentials"""
        try:
            import requests
            
            if not self.n8n_api_key:
                print("N8N API key not configured")
                return False
            
            headers = {
                'X-N8N-API-KEY': self.n8n_api_key,
                'Content-Type': 'application/json'
            }
            
            # This would involve updating the workflow nodes with credential IDs
            # Implementation depends on N8N API structure for credentials
            
            response = requests.patch(
                f"{self.n8n_base_url}/api/v1/workflows/{n8n_workflow_id}",
                headers=headers,
                json={'active': True},  # Activate after credentials are set
                timeout=30
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Error updating N8N workflow credentials: {e}")
            return False

    def save_user_uploaded_workflow(self, user_id: str, workflow_name: str, workflow_json: Dict, 
                                   workflow_description: Optional[str] = None, credentials_required: Optional[List[str]] = None, user_jwt: Optional[str] = None,
                                   n8n_workflow_id: Optional[str] = None, mcp_link: Optional[str] = None, template_id: Optional[str] = None, source_override: Optional[str] = None) -> bool:
        """Save user-uploaded workflow directly to user_workflows table (not n8n_workflows)"""
        try:
            
            # Always save to Supabase database
            if not self.supabase:
                print("ERROR: Supabase not available, cannot save user workflow")
                return False
            
            print(f"Saving user-uploaded workflow '{workflow_name}' for user {user_id} to Supabase database")
                
            # Generate a unique template_id for the user-uploaded workflow if not provided
            if not template_id:
                template_id = f"user-{user_id}-{str(uuid.uuid4())[:8]}"
            
            # Determine the correct source
            if source_override:
                source = source_override
                print(f"💾 Using provided source override: {source}")
            else:
                source = 'user_upload'
                print(f"💾 Using default source: {source}")
            
            # Check for duplicates if template_id is provided (for n8n templates)
            if template_id and source == 'n8n_template':
                print(f"🔍 Checking for duplicate n8n template: {template_id} for user {user_id}")
                # Use user JWT for RLS authentication if provided
                if user_jwt:
                    auth_client: Client = create_client(self.supabase_url, self.supabase_key)  # type: ignore
                    auth_client.auth.session = type('Session', (), {  # type: ignore
                        'access_token': user_jwt,
                        'refresh_token': '',
                        'user': {'id': user_id}
                    })()
                    existing_check = auth_client.table('user_workflows').select('*').eq('user_id', user_id).eq('template_id', template_id).execute()  # type: ignore
                else:
                    existing_check = self.supabase.table('user_workflows').select('*').eq('user_id', user_id).eq('template_id', template_id).execute()  # type: ignore
                
                if existing_check.data:
                    print(f"✅ Template {template_id} already exists for user {user_id}, skipping duplicate save")
                    return True  # Return True as the workflow is already saved
            
            # Determine template URL based on source
            if source == 'n8n_template':
                template_url = f"https://n8n.io/workflows/{template_id}"
            else:
                template_url = f"user-upload://{template_id}"
            
            workflow_data = {
                'user_id': user_id,
                'template_id': template_id,
                'template_url': template_url,
                'workflow_name': workflow_name,
                'workflow_description': workflow_description or f"User-uploaded workflow: {workflow_name}",
                'workflow_json': workflow_json,
                'credentials_required': credentials_required or [],  # Store as array directly
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'source': source,
                'n8n_workflow_id': n8n_workflow_id,
                'mcp_link': mcp_link
            }
            
            # Use admin client with service role to bypass RLS policies
            print(f"DEBUG: user_jwt provided: {user_jwt is not None}")
            print(f"DEBUG: SUPABASE_SERVICE_KEY configured: {self.supabase_service_key is not None}")
            
            if SUPABASE_AVAILABLE and self.supabase_admin:
                print("DEBUG: Using admin client with service role (bypasses RLS)")
                result = self.supabase_admin.table('user_workflows').insert(workflow_data).execute()  # type: ignore
            else:
                print("DEBUG: Supabase admin not available, skipping database insert")
                return True
            
            return True
        except Exception as e:
            print(f"Error saving user-uploaded workflow: {e}")
            return False

    def get_user_uploaded_workflows(self, user_id: str, user_jwt: Optional[str] = None) -> List[Dict]:
        """Get workflows uploaded directly by a user"""
        try:
        
            # Always read from Supabase database using admin client
            if not self.supabase_admin:
                print("ERROR: Supabase admin not available, cannot load user workflows")
                return []
            
            print(f"Loading user-uploaded workflows for user {user_id} from Supabase database")
            
            # Production mode - query Supabase using admin client
            if not SUPABASE_AVAILABLE:
                print("Supabase not available, falling back to development mode behavior")
                return []
                
            result = self.supabase_admin.table('user_workflows').select('*').eq('user_id', user_id).execute()  # type: ignore
            
            workflows = []
            for workflow in result.data:
                # Include ALL workflows for this user regardless of source
                # This function is used to get user's complete workflow list
                source = workflow.get('source', '')
                template_id = str(workflow.get('template_id', ''))
                
                # Include all workflows (user_upload, n8n_template, etc.)
                if True:  # Process all workflows
                    workflow_data = workflow.copy()
                    # workflow_json is already a dict from JSONB, no need to parse
                    
        
            
                    # Handle credentials_required safely (may not exist in all schemas)
                    credentials_raw = workflow_data.get('credentials_required')                    
                    if credentials_raw is None:
                        print("   ⚠️ credentials_required is None/missing in database")
                        workflow_data['credentials_required'] = []
                    elif isinstance(credentials_raw, str):
                        try:
                            parsed_creds = json.loads(credentials_raw)
                            workflow_data['credentials_required'] = parsed_creds
                        except json.JSONDecodeError as e:
                            print(f"   ❌ Failed to parse credentials string: {e}")
                            workflow_data['credentials_required'] = []
                    elif isinstance(credentials_raw, list):
                        workflow_data['credentials_required'] = credentials_raw
                    else:
                        print(f"   ⚠️ Unexpected credentials format: {type(credentials_raw)}")
                        workflow_data['credentials_required'] = []
                    
                    print(f"   Final credentials_required: {workflow_data['credentials_required']}")
                    
                    # Ensure created_at is included in the response
                    if 'created_at' not in workflow_data:
                        print(f"   ⚠️ WARNING: created_at field missing for workflow {template_id}")
                    else:
                        print(f"   ✅ created_at present: {workflow_data['created_at']}")
                    
                    workflows.append(workflow_data)
            
            return workflows
        except Exception as e:
            print(f"Error getting user-uploaded workflows: {e}")
            return []

    def delete_user_uploaded_workflow(self, user_id: str, template_id: str) -> bool:
        """Delete a user's uploaded workflow"""
        try:
            # Always delete from Supabase database using admin client
            if not self.supabase_admin:
                print("ERROR: Supabase admin not available, cannot delete user workflow")
                return False
            
            print(f"Deleting user-uploaded workflow {template_id} for user {user_id} from Supabase database")
            
            # Production mode - delete from Supabase using admin client
            result = self.supabase_admin.table('user_workflows').delete().eq('user_id', user_id).eq('template_id', template_id).execute()  # type: ignore
            
            return len(result.data) > 0 if result.data else False
            
        except Exception as e:
            print(f"Error deleting user-uploaded workflow: {e}")
            return False

    def update_workflow_n8n_id(self, template_id: str, n8n_workflow_id: str, user_id: str) -> bool:
        """Update workflow with N8N workflow ID after deployment"""
        try:
            # Always update in Supabase database
            if not self.supabase:
                print("ERROR: Supabase not available, cannot update workflow N8N ID")
                return False
                
            print(f"Updating workflow N8N ID: {template_id} -> {n8n_workflow_id} in Supabase database")
                
            # Update n8n_workflows table
            result = self.supabase.table('user_workflows').update({
                'n8n_workflow_id': n8n_workflow_id,
                'updated_at': datetime.now().isoformat()
            }).eq('template_id', template_id).execute()  # type: ignore
            
            return True
        except Exception as e:
            print(f"Error updating workflow N8N ID: {e}")
            return False

    def update_user_workflow_n8n_id(self, user_id: str, workflow_name: str, n8n_workflow_id: str) -> bool:
        """Update user workflow with N8N workflow ID after successful creation"""
        try:
            # Always update in Supabase database
            if not self.supabase:
                print("ERROR: Supabase not available, cannot update user workflow N8N ID")
                return False
                
            print(f"Updating user workflow N8N ID: user={user_id}, workflow='{workflow_name}' -> {n8n_workflow_id}")
                
            # Update user_workflows table
            result = self.supabase.table('user_workflows').update({
                'n8n_workflow_id': n8n_workflow_id,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).eq('workflow_name', workflow_name).execute()  # type: ignore
            
            if result.data:
                print(f"✅ Successfully updated user workflow with n8n ID: {n8n_workflow_id}")
                return True
            else:
                print(f"⚠️  No user workflow found to update for user {user_id}, workflow '{workflow_name}'")
                return False
            
        except Exception as e:
            print(f"Error updating user workflow N8N ID: {e}")
            return False

    def update_user_workflow_mcp_link(self, user_id: str, n8n_workflow_id: str, mcp_link: str) -> bool:
        """Update user workflow with MCP link"""
        try:
            # Always update Supabase database using admin client
            if not self.supabase_admin:
                print("ERROR: Supabase admin not available, cannot update user workflow MCP link")
                return False
                
            print(f"Updating user workflow with n8n_workflow_id {n8n_workflow_id} with MCP link: {mcp_link} in Supabase database")
            
            # First, let's check if the workflow exists
            check_result = self.supabase_admin.table('user_workflows').select('*').eq('user_id', user_id).eq('n8n_workflow_id', n8n_workflow_id).execute()  # type: ignore
            print(f"DEBUG: Found {len(check_result.data) if check_result.data else 0} workflows with n8n_workflow_id {n8n_workflow_id}")
            
            if check_result.data:
                for workflow in check_result.data:
                    print(f"DEBUG: Found workflow: {workflow.get('workflow_name')} with template_id: {workflow.get('template_id')}")
                
            result = self.supabase_admin.table('user_workflows').update({
                'mcp_link': mcp_link,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).eq('n8n_workflow_id', n8n_workflow_id).execute()  # type: ignore
            
            if result.data:
                print(f"✅ Successfully updated user workflow with MCP link: {mcp_link}")
                return True
            else:
                print(f"⚠️ No user workflow found to update for user {user_id}, n8n_workflow_id {n8n_workflow_id}")
                return False
            
        except Exception as e:
            print(f"Error updating user workflow MCP link: {e}")
            return False

    def update_user_workflow_template_id(self, user_id: str, workflow_name: str, template_id: str) -> bool:
        """Update user workflow with template_id"""
        try:
            if not self.supabase:
                print("ERROR: Supabase not available, cannot update user workflow template_id")
                return False
                
            print(f"Updating user workflow template_id: user={user_id}, workflow='{workflow_name}' -> {template_id}")
                
            result = self.supabase.table('user_workflows').update({
                'template_id': template_id,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).eq('workflow_name', workflow_name).execute()  # type: ignore
            
            if result.data:
                print(f"✅ Successfully updated user workflow with template_id: {template_id}")
                return True
            else:
                print(f"⚠️  No user workflow found to update for user {user_id}, workflow '{workflow_name}'")
                return False
            
        except Exception as e:
            print(f"Error updating user workflow template_id: {e}")
            return False

    def update_user_workflow_source(self, user_id: str, workflow_name: str, source: str) -> bool:
        """Update user workflow source"""
        try:
            if not self.supabase:
                print("ERROR: Supabase not available, cannot update user workflow source")
                return False
                
            print(f"Updating user workflow source: user={user_id}, workflow='{workflow_name}' -> {source}")
                
            result = self.supabase.table('user_workflows').update({
                'source': source,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).eq('workflow_name', workflow_name).execute()  # type: ignore
            
            if result.data:
                print(f"✅ Successfully updated user workflow source: {source}")
                return True
            else:
                print(f"⚠️  No user workflow found to update for user {user_id}, workflow '{workflow_name}'")
                return False
            
        except Exception as e:
            print(f"Error updating user workflow source: {e}")
            return False

    def get_user_mcp_servers(self, user_id: str) -> List[Dict]:
        """Get all MCP servers created by a user"""
        try:
            # Always get from Supabase database
            if not self.supabase:
                print("ERROR: Supabase not available, cannot get user MCP servers")
                return []
                
            print(f"Getting MCP servers for user {user_id} from Supabase database")
                
            result = self.supabase.table('user_workflows').select('*').eq('user_id', user_id).not_.is_('mcp_link', 'null').order('created_at', desc=True).execute()  # type: ignore
            return result.data
        except Exception as e:
            print(f"Error getting user MCP servers: {e}")
            return []

# Global instance
db_manager = SupabaseManager()