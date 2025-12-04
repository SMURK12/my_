"""
Add these routes to your app2.py file

Backend API endpoints for secure card listing operations
"""

from flask import request, jsonify
from orderbook_signing import get_signer
from auth import login_required

# ============================================================================
# SECURE LISTING ENDPOINTS - ADD TO app2.py
# ============================================================================

@app.route('/api/orderbook/list-card', methods=['POST'])
@login_required
def list_card(user):
    """
    List a single card for sale
    Requires authentication
    """
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['token_id', 'token_address', 'buy_token', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Get signer instance
        signer = get_signer()
        
        # Verify the wallet address matches the authenticated user
        if signer.address.lower() != user['wallet_address'].lower():
            return jsonify({
                'success': False,
                'error': 'Wallet mismatch - automation wallet does not match user account'
            }), 403
        
        # Perform the listing
        result = signer.sign_and_list(
            token_address=data['token_address'],
            token_id=data['token_id'],
            buy_token=data['buy_token'],
            amount=data['amount']
        )
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"Error in list_card endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orderbook/bulk-list', methods=['POST'])
@login_required
def bulk_list_cards_endpoint(user):
    """
    List multiple cards for sale in bulk
    Requires authentication
    
    Request body:
    {
        "listings": [
            {
                "token_id": "123",
                "token_address": "0x...",
                "buy_token": "0x...",
                "amount": "1000000000000000000"  // Price in wei
            },
            ...
        ]
    }
    """
    try:
        data = request.json
        
        if 'listings' not in data or not isinstance(data['listings'], list):
            return jsonify({
                'success': False,
                'error': 'listings array is required'
            }), 400
        
        if len(data['listings']) == 0:
            return jsonify({
                'success': False,
                'error': 'listings array cannot be empty'
            }), 400
        
        # Get signer instance
        signer = get_signer()
        
        # Verify the wallet address matches the authenticated user
        if signer.address.lower() != user['wallet_address'].lower():
            return jsonify({
                'success': False,
                'error': 'Wallet mismatch - automation wallet does not match user account'
            }), 403
        
        # Perform bulk listing
        results = signer.bulk_list_cards(data['listings'])
        
        return jsonify({
            'success': True,
            'results': results
        }), 200
        
    except Exception as e:
        print(f"Error in bulk_list_cards endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/orderbook/wallet-info', methods=['GET'])
@login_required
def get_wallet_info(user):
    """
    Get information about the automation wallet
    Requires authentication
    """
    try:
        signer = get_signer()
        
        return jsonify({
            'success': True,
            'address': signer.address,
            'matches_user': signer.address.lower() == user['wallet_address'].lower()
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500