"""
NEW BACKEND ENDPOINT FOR MARKET DATA
Add this to your app2.py file
"""

# ============================================
# Add this import at the top if not already present
# ============================================
from flask import Flask, jsonify, request
from typing import Dict, List, Optional


# ============================================
# MAIN ENDPOINT - Add this to your Flask app
# ============================================

@app.route('/api/market-data', methods=['POST'])
@login_required
def get_market_data(user):
    """
    Get market data for selected cards including token_ids and lowest listing prices.
    
    Request body:
    {
        "token_ids": ["123456", "789012", ...],
        "wallet_address": "0x..."
    }
    
    Returns:
    {
        "success": true,
        "cards": [
            {
                "token_id": "123456",
                "proto_id": "1234",
                "card_name": "Example Card",
                "quality": "Meteorite",
                "owner": "0x...",
                "lowest_listing": {
                    "price_usd": 1.23,
                    "currency_address": "0x...",
                    "currency_quantity": "1230000000000000000",
                    "currency_symbol": "ETH",
                    "order_id": "12345",
                    "seller": "0x..."
                },
                "currently_listed": true,
                "user_listing": {
                    "price_usd": 2.50,
                    "order_id": "67890"
                }
            }
        ]
    }
    """
    data = request.json
    token_ids = data.get('token_ids', [])
    wallet_address = data.get('wallet_address', '').lower()
    
    if not token_ids:
        return jsonify({'success': False, 'error': 'No token IDs provided'}), 400
    
    if not wallet_address:
        return jsonify({'success': False, 'error': 'Wallet address required'}), 400
    
    try:
        # Fetch current USD prices
        prices_usd = fetch_prices_usd()
        
        cards_data = []
        
        # Process each token_id
        for token_id in token_ids:
            card_info = fetch_card_info(token_id, wallet_address, prices_usd)
            if card_info:
                cards_data.append(card_info)
        
        return jsonify({
            'success': True,
            'cards': cards_data,
            'total_selected': len(token_ids),
            'data_retrieved': len(cards_data)
        })
        
    except Exception as e:
        print(f"Error in get_market_data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# HELPER FUNCTION 1: Fetch card info
# ============================================

def fetch_card_info(token_id: str, wallet_address: str, prices_usd: Dict[str, float]) -> Optional[dict]:
    """Fetch comprehensive market data for a single card."""
    try:
        # Get asset details
        asset_url = f"https://api.tokentrove.com/v1/assets/{TOKEN_ADDRESS}/{token_id}"
        rate_limit(asset_url, REQUEST_DELAY)
        proxy = get_proxy()
        headers = get_headers()
        
        response = requests.get(asset_url, headers=headers, timeout=30, proxies=proxy)
        response.raise_for_status()
        asset_data = response.json()
        
        # Extract basic card info
        card_info = {
            'token_id': token_id,
            'proto_id': asset_data.get('proto', 'N/A'),
            'card_name': asset_data.get('name', 'Unknown'),
            'quality': asset_data.get('quality', 'N/A'),
            'owner': asset_data.get('user', '').lower(),
            'currently_listed': False,
            'user_listing': None,
            'lowest_listing': None,
            'all_listings': []
        }
        
        # Get listings for this specific token
        listings_url = f"https://api.tokentrove.com/v2/nft/activity/{TOKEN_ADDRESS}/{token_id}"
        rate_limit(listings_url, REQUEST_DELAY)
        
        listings_response = requests.get(listings_url, headers=headers, timeout=30, proxies=proxy)
        listings_response.raise_for_status()
        listings_data = listings_response.json()
        
        # Process active listings
        active_listings = []
        user_listing = None
        
        for listing in listings_data.get('result', []):
            if listing.get('status') == 'active' and listing.get('type') == 'sell':
                price_usd = convert_to_usd(listing, prices_usd)
                seller = listing.get('user', '').lower()
                
                listing_info = {
                    'order_id': listing.get('order_id'),
                    'price_usd': price_usd,
                    'currency_address': listing.get('currency_address'),
                    'currency_quantity': listing.get('currency_quantity'),
                    'currency_symbol': get_currency_symbol(listing.get('currency_address')),
                    'seller': seller,
                    'created_at': listing.get('timestamp'),
                    'expiration': listing.get('expiration_timestamp')
                }
                
                active_listings.append(listing_info)
                
                # Check if this is the user's listing
                if seller == wallet_address:
                    user_listing = listing_info
                    card_info['currently_listed'] = True
        
        # Sort listings by price (USD)
        active_listings.sort(key=lambda x: x['price_usd'] if x['price_usd'] else float('inf'))
        
        card_info['all_listings'] = active_listings
        card_info['user_listing'] = user_listing
        
        # Get lowest listing (that's not the user's own)
        for listing in active_listings:
            if listing['seller'] != wallet_address:
                card_info['lowest_listing'] = listing
                break
        
        # If no other listings, use user's own as reference
        if not card_info['lowest_listing'] and active_listings:
            card_info['lowest_listing'] = active_listings[0]
        
        return card_info
        
    except Exception as e:
        print(f"Error fetching card info for token {token_id}: {e}")
        return None


# ============================================
# HELPER FUNCTION 2: Get currency symbol
# ============================================

def get_currency_symbol(currency_address: str) -> str:
    """Get human-readable currency symbol."""
    if not currency_address:
        return 'N/A'
    
    currency_map = {
        '0x52a6c53869ce09a731cd772f245b97a4401d3348': 'ETH',
        '0xe0e0981d19ef2e0a57cc48ca60d9454ed2d53feb': 'GODS',
        '0xf57e7e7c23978c3caec3c3548e3d615c346e79ff': 'IMX',
        '0x6de8acc0d406837030ce4dd28e7c08c5a96a30d2': 'USDC',
        'NATIVE': 'IMX'
    }
    
    return currency_map.get(currency_address.lower(), 'UNKNOWN')


# ============================================
# NOTES ON EXISTING FUNCTIONS NEEDED
# ============================================

"""
This endpoint relies on the following functions that should already exist in your app2.py:

1. fetch_prices_usd() - Fetches current USD prices from CoinGecko
2. convert_to_usd() - Converts currency amounts to USD
3. rate_limit() - Rate limiting for API calls
4. get_proxy() - Gets proxy for API calls
5. get_headers() - Gets headers for API calls
6. @login_required - Authentication decorator

And these global variables:
- TOKEN_ADDRESS = "0x06d92b637dfcdf95a2faba04ef22b2a096029b69"
- REQUEST_DELAY = 0.3
- TOKEN_MAP - Currency address to (coin_id, decimals) mapping

If any of these are missing, copy them from your existing app2.py file.
"""


# ============================================
# TESTING THE ENDPOINT
# ============================================

"""
Test with curl:

curl -X POST http://localhost:5000/api/market-data \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "token_ids": ["123456", "789012"],
    "wallet_address": "0xYourWalletAddress"
  }'

Expected response:
{
  "success": true,
  "cards": [
    {
      "token_id": "123456",
      "card_name": "Playful Faun",
      "quality": "Meteorite",
      "currently_listed": true,
      "lowest_listing": {
        "price_usd": 1.23,
        "currency_symbol": "ETH"
      }
    }
  ],
  "total_selected": 2,
  "data_retrieved": 2
}
"""