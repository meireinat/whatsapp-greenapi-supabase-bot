"""
Test script to check webhook endpoint accessibility and configuration.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.models.greenapi import GreenWebhookPayload

async def test_webhook_endpoint():
    """Test if webhook endpoint is accessible."""
    settings = get_settings()
    
    # Get Railway URL from environment or ask user
    railway_url = input("Enter your Railway deployment URL (e.g., https://your-app.up.railway.app): ").strip()
    if not railway_url:
        print("❌ No URL provided")
        return
    
    # Remove trailing slash
    railway_url = railway_url.rstrip("/")
    webhook_url = f"{railway_url}/api/green/webhook"
    
    print(f"\n{'='*60}")
    print("Webhook Configuration Test")
    print(f"{'='*60}\n")
    
    print(f"1. Webhook URL: {webhook_url}")
    print(f"2. Expected Authorization header: Bearer {settings.green_api_webhook_token or '(not set)'}")
    print(f"3. Green API Instance ID: {settings.green_api_instance_id}\n")
    
    # Test 1: Check if endpoint is accessible (without auth)
    print("Test 1: Checking if endpoint is accessible...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(webhook_url)
            print(f"   GET response: {response.status_code}")
            if response.status_code == 405:  # Method Not Allowed is OK for GET
                print("   ✓ Endpoint exists (GET not allowed, but POST should work)")
            else:
                print(f"   ⚠ Unexpected status: {response.status_code}")
        except httpx.ConnectError:
            print("   ✗ Cannot connect to server - check if Railway deployment is running")
            return
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return
    
    # Test 2: Test with sample webhook payload (without auth)
    print("\nTest 2: Testing webhook with sample payload (no auth)...")
    sample_payload = {
        "typeWebhook": "incomingMessageReceived",
        "instanceData": {
            "idInstance": settings.green_api_instance_id,
            "wid": "7107376686@c.us",
            "typeInstance": "whatsapp"
        },
        "timestamp": 1234567890,
        "idMessage": "test123",
        "senderData": {
            "sender": "972504057453@c.us",
            "senderName": "Test User",
            "chatId": "972504057453@c.us"
        },
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {
                "textMessage": "בדיקת בוט"
            }
        }
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(webhook_url, json=sample_payload)
            print(f"   POST response (no auth): {response.status_code}")
            if response.status_code == 401:
                print("   ✓ Endpoint requires authentication (expected)")
            elif response.status_code == 200:
                print("   ⚠ Endpoint accepted request without auth (security issue!)")
            else:
                print(f"   ⚠ Unexpected status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
    
    # Test 3: Test with auth
    if settings.green_api_webhook_token:
        print("\nTest 3: Testing webhook with Authorization header...")
        headers = {
            "Authorization": f"Bearer {settings.green_api_webhook_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(webhook_url, json=sample_payload, headers=headers)
                print(f"   POST response (with auth): {response.status_code}")
                if response.status_code == 200:
                    print("   ✓ Webhook endpoint is working correctly!")
                elif response.status_code == 202:
                    print("   ✓ Webhook endpoint accepted request (202 Accepted)")
                else:
                    print(f"   ⚠ Unexpected status: {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
            except Exception as e:
                print(f"   ✗ Error: {e}")
    else:
        print("\nTest 3: Skipped (no webhook token configured)")
    
    print(f"\n{'='*60}")
    print("Configuration Summary for Green API:")
    print(f"{'='*60}")
    print(f"Webhook URL: {webhook_url}")
    if settings.green_api_webhook_token:
        print(f"Authorization Header: Bearer {settings.green_api_webhook_token}")
    else:
        print("⚠ No webhook token configured - webhook will accept all requests!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(test_webhook_endpoint())

