"""
Test script to debug configuration loading.
"""
import os
from dotenv import load_dotenv
from app.config import get_settings, _load_credentials_file

print("=" * 60)
print("Configuration Debug Test")
print("=" * 60)

# Check .env file
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
print(f"\n1. Checking for .env file: {env_path}")
print(f"   Exists: {os.path.exists(env_path)}")

# Check environment variables directly
print("\n2. Environment variables (direct):")
for key in ["GREEN_API_INSTANCE_ID", "GREEN_API_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]:
    value = os.getenv(key)
    if value:
        # Mask sensitive values
        if "TOKEN" in key or "KEY" in key:
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"   {key} = {masked}")
        else:
            print(f"   {key} = {value}")
    else:
        print(f"   {key} = (not set)")

# Load .env explicitly
print("\n3. Loading .env file...")
load_dotenv()
print("   load_dotenv() called")

# Check after load_dotenv
print("\n4. Environment variables (after load_dotenv):")
for key in ["GREEN_API_INSTANCE_ID", "GREEN_API_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]:
    value = os.getenv(key)
    if value:
        if "TOKEN" in key or "KEY" in key:
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"   {key} = {masked}")
        else:
            print(f"   {key} = {value}")
    else:
        print(f"   {key} = (not set)")

# Check credentials file
print("\n5. Credentials file content:")
try:
    creds = _load_credentials_file()
    if creds:
        print("   File loaded successfully")
        for key in ["green_api_instance_id", "green_api_token", "supabase_url", "supabase_service_role_key"]:
            value = creds.get(key, "(not found)")
            if value and value not in ["instance_id", "api_token", "supabase_service_role_key", "your-project.supabase.co"]:
                if "token" in key or "key" in key:
                    masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                    print(f"   {key} = {masked}")
                else:
                    print(f"   {key} = {value}")
            else:
                print(f"   {key} = {value} (placeholder)")
    else:
        print("   File is empty or doesn't exist")
except Exception as e:
    print(f"   Error loading credentials file: {e}")

# Try to get settings
print("\n6. Attempting to load settings via get_settings():")
try:
    settings = get_settings()
    print("   ✓ Settings loaded successfully")
    print(f"   green_api_instance_id = {settings.green_api_instance_id}")
    if settings.green_api_instance_id == "instance_id":
        print("   ⚠ WARNING: Still using placeholder value!")
    else:
        print(f"   ✓ Using real instance ID: {settings.green_api_instance_id}")
    
    token_preview = settings.green_api_token[:8] + "..." + settings.green_api_token[-4:] if len(settings.green_api_token) > 12 else "***"
    print(f"   green_api_token = {token_preview}")
    if settings.green_api_token == "api_token":
        print("   ⚠ WARNING: Still using placeholder value!")
except Exception as e:
    print(f"   ✗ Error loading settings: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)

