"""
Secure Orderbook Signing Module
Handles all blockchain signing operations on the backend
"""

import os
from eth_account import Account
from eth_account.messages import encode_typed_data
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

# Load private key from environment variable
AUTOMATION_PRIVATE_KEY = os.getenv('AUTOMATION_WALLET_PRIVATE_KEY')

if not AUTOMATION_PRIVATE_KEY:
    print("⚠️ WARNING: AUTOMATION_WALLET_PRIVATE_KEY not set in environment")
    AUTOMATION_PRIVATE_KEY = None

# Constants
ZKEVM_MAINNET_RPC = "https://rpc.immutable.com"
ORDERBOOK_API = "https://api.immutable.com/v1/orderbook"

class OrderbookSigner:
    """Handles secure signing of orderbook operations"""
    
    def __init__(self, private_key: Optional[str] = None):
        """Initialize with private key from environment or parameter"""
        self.private_key = private_key or AUTOMATION_PRIVATE_KEY
        
        if not self.private_key:
            raise ValueError("No private key provided. Set AUTOMATION_WALLET_PRIVATE_KEY environment variable")
        
        # Remove 0x prefix if present
        if self.private_key.startswith('0x'):
            self.private_key = self.private_key[2:]
        
        # Create account from private key
        self.account = Account.from_key(self.private_key)
        self.address = self.account.address
        
        print(f"✅ OrderbookSigner initialized for address: {self.address}")
    
    def sign_typed_data(self, domain: dict, types: dict, value: dict) -> str:
        """
        Sign EIP-712 typed data
        
        Args:
            domain: EIP-712 domain separator
            types: Type definitions
            value: The message to sign
            
        Returns:
            Signature as hex string
        """
        try:
            # Construct the EIP-712 message
            typed_data = {
                "domain": domain,
                "types": types,
                "primaryType": list(types.keys())[0] if types else "EIP712Domain",
                "message": value
            }
            
            # Encode and sign
            encoded_data = encode_typed_data(full_message=typed_data)
            signed_message = self.account.sign_message(encoded_data)
            
            return signed_message.signature.hex()
            
        except Exception as e:
            print(f"❌ Error signing typed data: {e}")
            raise
    
    def prepare_listing(self, token_address: str, token_id: str, 
                    buy_token: str, amount: str) -> dict:
        """Prepare a listing"""
        url = "https://api.immutable.com/v1/orderbook/orders"  # Changed from /listings
        
        payload = {
            "maker_address": self.address,
            "sell": [{
                "type": "ERC721",
                "contract_address": token_address,
                "token_id": token_id
            }],
            "buy": [{
                "type": "ERC20",
                "contract_address": buy_token,
                "amount": amount
            }]
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        return response.json()
    def create_listing(self, order_components: dict, order_hash: str, 
                  signature: str) -> dict:
        """Create a listing after signing"""
        url = "https://api.immutable.com/v1/orderbook/orders"  # Changed from /listings
        
        payload = {
            "maker_fees": [],
            "order_components": order_components,
            "order_hash": order_hash,
            "order_signature": signature
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        return response.json()
    def sign_and_list(self, token_address: str, token_id: str,
                     buy_token: str, amount: str) -> dict:
        """
        Complete listing flow: prepare -> sign -> create
        
        Args:
            token_address: NFT contract address
            token_id: Token ID to list
            buy_token: Currency contract address  
            amount: Price amount in wei
            
        Returns:
            Listing result with success status and listing ID
        """
        try:
            # Step 1: Prepare listing
            prepare_response = self.prepare_listing(token_address, token_id, buy_token, amount)
            
            # Step 2: Extract signable action
            signable_action = None
            for action in prepare_response.get('actions', []):
                if action.get('type') == 'SIGNABLE':
                    signable_action = action
                    break
            
            if not signable_action:
                raise ValueError("No signable action found in prepare response")
            
            # Step 3: Sign the message
            message = signable_action['message']
            signature = self.sign_typed_data(
                domain=message['domain'],
                types=message['types'],
                value=message['value']
            )
            
            # Step 4: Create listing
            create_response = self.create_listing(
                order_components=prepare_response['order_components'],
                order_hash=prepare_response['order_hash'],
                signature=signature
            )
            
            return {
                'success': True,
                'listing_id': create_response.get('result', {}).get('id'),
                'token_id': token_id
            }
            
        except Exception as e:
            print(f"❌ Error listing token {token_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'token_id': token_id
            }
    
    def bulk_list_cards(self, listings: List[dict]) -> dict:
        """List multiple cards in bulk"""
        results = {
            'successful': 0,
            'failed': 0,
            'listings': [],
            'errors': []
        }
        
        for listing_data in listings:
            # Add default buy_token if missing (IMX wrapped token)
            if 'buy_token' not in listing_data:
                listing_data['buy_token'] = '0xf57e7e7c23978c3caec3c3548e3d615c346e79ff'  # IMX
            
            # Add default token_address if missing
            if 'token_address' not in listing_data:
                listing_data['token_address'] = '0x06d92b637dfcdf95a2faba04ef22b2a096029b69'  # GU cards
            
            result = self.sign_and_list(
                token_address=listing_data['token_address'],
                token_id=listing_data['token_id'],
                buy_token=listing_data['buy_token'],
                amount=listing_data['amount']
            )
            
            if result['success']:
                results['successful'] += 1
                results['listings'].append(result)
            else:
                results['failed'] += 1
                results['errors'].append(result)
        
        return results
def get_signer() -> OrderbookSigner:
    """Get configured OrderbookSigner instance"""
    return OrderbookSigner()