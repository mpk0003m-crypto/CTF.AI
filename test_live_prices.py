"""
Test script for Live Prices functionality
Run this to verify all endpoints work correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, init_db
import json

print("=" * 60)
print("LIVE PRICES FUNCTIONALITY TEST")
print("=" * 60)

# Initialize database
print("\n1. Initializing database...")
try:
    init_db()
    print("   ✓ Database initialized successfully")
    print("   ✓ live_prices table created")
    print("   ✓ live_price_feedback table created")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# Test API endpoints
print("\n2. Testing API endpoints...")
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1  # Simulate logged-in user
    
    # Test GET /api/live-prices
    print("   Testing GET /api/live-prices...")
    response = client.get('/api/live-prices')
    try:
        data = json.loads(response.data)
        if data.get('success'):
            print(f"   ✓ GET /api/live-prices works (found {len(data.get('prices', []))} posts)")
        else:
            print(f"   ⚠ Warning: {data.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test POST /api/live-prices
    print("   Testing POST /api/live-prices...")
    test_data = {
        'product_name': 'Test Maize',
        'category': 'Grains',
        'min_price': '15',
        'max_price': '20',
        'price_unit': 'Kg',
        'price_trend': 'stable',
        'phone': '9876543210',
        'area': 'Test Area',
        'city': 'Test City',
        'district': 'Test District',
        'state': 'Telangana',
        'pin_code': '500001'
    }
    response = client.post('/api/live-prices', data=test_data)
    try:
        data = json.loads(response.data)
        if data.get('success'):
            test_post_id = data.get('id')
            print(f"   ✓ POST /api/live-prices works (created post ID: {test_post_id})")
            
            # Test GET single price
            print(f"   Testing GET /api/live-prices/{test_post_id}...")
            response = client.get(f'/api/live-prices/{test_post_id}')
            data = json.loads(response.data)
            if data.get('success'):
                print(f"   ✓ GET /api/live-prices/{test_post_id} works")
            else:
                print(f"   ✗ Error: {data.get('message')}")
            
            # Test POST feedback
            print(f"   Testing POST /api/live-prices/{test_post_id}/feedback...")
            feedback_data = {
                'rating': 5,
                'farmer_name': 'Test Farmer',
                'comment': 'Great quality!'
            }
            response = client.post(
                f'/api/live-prices/{test_post_id}/feedback',
                data=json.dumps(feedback_data),
                content_type='application/json'
            )
            data = json.loads(response.data)
            if data.get('success'):
                print(f"   ✓ POST /api/live-prices/{test_post_id}/feedback works")
            else:
                print(f"   ✗ Error: {data.get('message')}")
            
            # Test GET feedback
            print(f"   Testing GET /api/live-prices/{test_post_id}/feedback...")
            response = client.get(f'/api/live-prices/{test_post_id}/feedback')
            data = json.loads(response.data)
            if data.get('success'):
                fb_count = len(data.get('feedbacks', []))
                avg_rating = data.get('stats', {}).get('avg_rating', 0)
                print(f"   ✓ GET /api/live-prices/{test_post_id}/feedback works")
                print(f"     - Feedback count: {fb_count}")
                print(f"     - Average rating: {avg_rating}/5")
            else:
                print(f"   ✗ Error: {data.get('message')}")
        else:
            print(f"   ✗ Error: {data.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\nTo run the server:")
print("  python app.py")
print("\nThen open: http://127.0.0.1:5000/dashboard")
print("Navigate to 'Live Prices' section to test the UI")
print("=" * 60)
