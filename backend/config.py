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
