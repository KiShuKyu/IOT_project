import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')
    SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
    SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    ITEMS_TABLE = os.getenv('SUPABASE_ITEMS_TABLE', 'items')
    DEVICE_TOKEN = os.getenv('DEVICE_TOKEN', '')
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', '5000'))
    DEBUG = os.getenv('DEBUG', '0').lower() in ('1','true','yes')
    MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '20'))
    OPENHANDS_URL = os.getenv('OPENHANDS_URL', 'http://127.0.0.1:8000')
    OPENHANDS_API_KEY = os.getenv('OPENHANDS_API_KEY', '')
    OPENHANDS_AGENT_PROFILE_ID = os.getenv(
        'OPENHANDS_AGENT_PROFILE_ID',
        '1b7d86a9-63cf-402e-b370-cc5cb4420b31'
    )
    PROJECTS_ROOT = os.getenv('PROJECTS_ROOT', r'D:\Coding\PalaProjects')
