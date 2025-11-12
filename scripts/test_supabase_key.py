"""
Test script to verify Supabase key and connection.
This will help diagnose 401 Unauthorized errors.
"""

import json
import sys
from pathlib import Path

import httpx
from app.config import get_settings


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload to see the role."""
    import base64
    
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return {}
        
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        print(f"Error decoding JWT: {e}")
        return {}


def test_supabase_connection():
    """Test Supabase connection with the current key."""
    print("=" * 60)
    print("TESTING SUPABASE CONNECTION")
    print("=" * 60)
    
    try:
        settings = get_settings()
        print(f"\nSupabase URL: {settings.supabase_url}")
        print(f"Key length: {len(settings.supabase_service_role_key)}")
        
        # Decode JWT to check role
        payload = decode_jwt_payload(settings.supabase_service_role_key)
        role = payload.get('role', 'unknown')
        ref = payload.get('ref', 'unknown')
        
        print(f"\nJWT Payload:")
        print(f"  Role: {role}")
        print(f"  Ref: {ref}")
        print(f"  Iss: {payload.get('iss', 'unknown')}")
        
        if role == 'anon':
            print("\n⚠️  WARNING: This is an ANON key, not a SERVICE_ROLE key!")
            print("   Anon keys have limited permissions.")
            print("   You need the SERVICE_ROLE key from Supabase Dashboard:")
            print("   Settings → API → service_role key (click 'Reveal')")
        elif role == 'service_role':
            print("\n✓ This is a SERVICE_ROLE key (correct)")
        else:
            print(f"\n⚠️  Unknown role: {role}")
        
        # Test connection
        print("\n" + "=" * 60)
        print("TESTING API CONNECTION")
        print("=" * 60)
        
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        
        # Test 1: Check if we can access the containers table
        url = f"{settings.supabase_url}/rest/v1/containers?select=SHANA&limit=1"
        print(f"\nTest 1: GET {url}")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✓ Successfully connected to Supabase!")
                data = response.json()
                print(f"  Response: {data}")
            elif response.status_code == 401:
                print("✗ 401 Unauthorized - Invalid API key")
                print(f"  Response: {response.text[:200]}")
                print("\nPossible solutions:")
                print("  1. Check if you're using the SERVICE_ROLE key (not anon key)")
                print("  2. Verify the key in Railway matches the key in Supabase Dashboard")
                print("  3. Make sure there are no extra spaces or newlines in the key")
            elif response.status_code == 404:
                print("✗ 404 Not Found - Table might not exist")
                print("  Make sure you've created the 'containers' table in Supabase")
            else:
                print(f"✗ Unexpected status: {response.status_code}")
                print(f"  Response: {response.text[:200]}")
        
        # Test 2: Try to count containers for January 2024
        print("\n" + "=" * 60)
        print("TESTING QUERY FOR JANUARY 2024")
        print("=" * 60)
        
        query_url = (
            f"{settings.supabase_url}/rest/v1/containers"
            f"?select=SHANA"
            f"&TARICH_PRIKA=gte.20240101"
            f"&TARICH_PRIKA=lte.20240131"
        )
        
        query_headers = {
            **headers,
            "Range-Unit": "items",
            "Prefer": "count=exact",
        }
        
        print(f"\nTest 2: GET {query_url}")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(query_url, headers=query_headers)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                content_range = response.headers.get("Content-Range", "")
                print(f"Content-Range: {content_range}")
                
                if content_range:
                    parts = content_range.split("/")
                    if len(parts) == 2 and parts[1].isdigit():
                        count = int(parts[1])
                        print(f"\n✓ Found {count} containers in January 2024")
                    else:
                        print(f"  Could not parse Content-Range: {content_range}")
                else:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"  Got {len(data)} items (might be limited)")
                    else:
                        print(f"  Response: {data}")
            else:
                print(f"✗ Query failed: {response.status_code}")
                print(f"  Response: {response.text[:200]}")
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print("\nIf you're getting 401 errors:")
        print("1. Go to Supabase Dashboard → Settings → API")
        print("2. Find 'service_role' key (not 'anon' key)")
        print("3. Click 'Reveal' to see the full key")
        print("4. Copy the ENTIRE key (it's very long)")
        print("5. Paste it into Railway → Settings → Variables → SUPABASE_SERVICE_ROLE_KEY")
        print("6. Make sure there are no spaces or newlines")
        print("7. Redeploy on Railway")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_supabase_connection()

