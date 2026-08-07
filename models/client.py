import os

from supabase import Client

client = Client(supabase_url=os.environ.get("SUPABASE_URL"), supabase_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY"))