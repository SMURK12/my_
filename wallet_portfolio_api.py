"""
Wallet Portfolio API Module
Handles wallet management, token balance fetching, and portfolio tracking
"""

import psycopg2
import requests
import json
from decimal import Decimal
from datetime import datetime
from flask import jsonify
from auth import get_db, login_required

# Immutable Explorer API base URL
IMMUTABLE_API_BASE = "https://explorer.immutable.com/api/v2"


def get_wallet_tokens(wallet_address):
    """Fetch ERC-20 tokens from Immutable Explorer API."""
    try:
        url = f"{IMMUTABLE_API_BASE}/addresses/{wallet_address}/tokens"
        params = {"type": "ERC-20"}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        return data.get("items", [])
    except requests.RequestException as e:
        print(f"Error fetching tokens from Immutable API: {e}")
        return []


def format_token_balance(balance_str, decimals):
    """Convert raw token balance to formatted decimal."""
    try:
        balance = Decimal(balance_str)
        divisor = Decimal(10 ** int(decimals))
        return balance / divisor
    except (ValueError, TypeError):
        return Decimal(0)


def calculate_usd_value(balance_formatted, exchange_rate):
    """Calculate USD value of token balance."""
    try:
        return Decimal(str(balance_formatted)) * Decimal(str(exchange_rate))
    except (ValueError, TypeError):
        return Decimal(0)


# ==================== API ENDPOINTS ====================

def add_wallet(user):
    """Add a new wallet for the user."""
    from flask import request
    
    data = request.get_json()
    wallet_address = data.get('wallet_address', '').strip()
    nickname = data.get('nickname', '').strip()
    is_primary = data.get('is_primary', False)
    
    if not wallet_address:
        return jsonify({'success': False, 'error': 'Wallet address is required'}), 400
    
    # Validate Ethereum address format (basic check)
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        return jsonify({'success': False, 'error': 'Invalid wallet address format'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # If setting as primary, unset other primary wallets
        if is_primary:
            cur.execute("""
                UPDATE gu_user_wallets 
                SET is_primary = FALSE 
                WHERE user_id = %s
            """, (user['user_id'],))
        
        # Insert wallet
        cur.execute("""
            INSERT INTO gu_user_wallets (user_id, wallet_address, nickname, is_primary)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, wallet_address) 
            DO UPDATE SET 
                nickname = EXCLUDED.nickname,
                is_primary = EXCLUDED.is_primary,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, wallet_address, nickname, is_primary, created_at;
        """, (user['user_id'], wallet_address, nickname or None, is_primary))
        
        result = cur.fetchone()
        wallet_data = {
            'id': result[0],
            'wallet_address': result[1],
            'nickname': result[2],
            'is_primary': result[3],
            'created_at': result[4].isoformat()
        }
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'wallet': wallet_data,
            'message': 'Wallet added successfully'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error adding wallet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def get_user_wallets(user):
    """Get all wallets for the user with their balances."""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT * FROM gu_wallet_details 
            WHERE user_id = %s
            ORDER BY is_primary DESC, created_at DESC;
        """, (user['user_id'],))
        
        wallets = []
        for row in cur.fetchall():
            wallets.append({
                'id': row[0],
                'wallet_address': row[2],
                'nickname': row[3],
                'is_primary': row[4],
                'token_count': row[5],
                'total_value_usd': float(row[6]) if row[6] else 0.0,
                'last_updated': row[7].isoformat() if row[7] else None
            })
        
        return jsonify({
            'success': True,
            'wallets': wallets
        })
        
    except Exception as e:
        print(f"Error getting wallets: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def update_wallet(user, wallet_id):
    """Update wallet nickname or primary status."""
    from flask import request
    
    data = request.get_json()
    nickname = data.get('nickname', '').strip()
    is_primary = data.get('is_primary')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Verify wallet belongs to user
        cur.execute("""
            SELECT id FROM gu_user_wallets 
            WHERE id = %s AND user_id = %s
        """, (wallet_id, user['user_id']))
        
        if not cur.fetchone():
            return jsonify({'success': False, 'error': 'Wallet not found'}), 404
        
        # If setting as primary, unset other primary wallets
        if is_primary:
            cur.execute("""
                UPDATE gu_user_wallets 
                SET is_primary = FALSE 
                WHERE user_id = %s AND id != %s
            """, (user['user_id'], wallet_id))
        
        # Update wallet
        update_fields = []
        update_values = []
        
        if nickname is not None:
            update_fields.append("nickname = %s")
            update_values.append(nickname or None)
        
        if is_primary is not None:
            update_fields.append("is_primary = %s")
            update_values.append(is_primary)
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.extend([wallet_id])
            
            cur.execute(f"""
                UPDATE gu_user_wallets 
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, wallet_address, nickname, is_primary;
            """, update_values)
            
            result = cur.fetchone()
            wallet_data = {
                'id': result[0],
                'wallet_address': result[1],
                'nickname': result[2],
                'is_primary': result[3]
            }
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'wallet': wallet_data,
                'message': 'Wallet updated successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400
        
    except Exception as e:
        conn.rollback()
        print(f"Error updating wallet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def delete_wallet(user, wallet_id):
    """Delete a wallet."""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            DELETE FROM gu_user_wallets 
            WHERE id = %s AND user_id = %s
            RETURNING wallet_address;
        """, (wallet_id, user['user_id']))
        
        result = cur.fetchone()
        
        if not result:
            return jsonify({'success': False, 'error': 'Wallet not found'}), 404
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Wallet {result[0]} deleted successfully'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error deleting wallet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def refresh_wallet_balances(user, wallet_id):
    """Fetch and update token balances for a wallet from Immutable API."""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Verify wallet belongs to user and get wallet address
        cur.execute("""
            SELECT wallet_address FROM gu_user_wallets 
            WHERE id = %s AND user_id = %s
        """, (wallet_id, user['user_id']))
        
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Wallet not found'}), 404
        
        wallet_address = result[0]
        
        # Fetch tokens from Immutable API
        tokens = get_wallet_tokens(wallet_address)
        
        if not tokens:
            return jsonify({
                'success': True,
                'message': 'No tokens found or API error',
                'tokens': []
            })
        
        # Update balances in database
        updated_count = 0
        token_list = []
        
        for item in tokens:
            token = item.get('token', {})
            value = item.get('value', '0')
            
            token_address = token.get('address_hash')
            token_name = token.get('name')
            token_symbol = token.get('symbol')
            token_decimals = int(token.get('decimals', 18))
            token_icon = token.get('icon_url')
            exchange_rate = float(token.get('exchange_rate', 0))
            
            # Calculate formatted balance and USD value
            balance_formatted = format_token_balance(value, token_decimals)
            usd_value = calculate_usd_value(balance_formatted, exchange_rate)
            
            # Insert or update balance
            cur.execute("""
                INSERT INTO gu_wallet_balances (
                    wallet_id, token_address, token_name, token_symbol,
                    token_decimals, token_icon_url, balance, balance_formatted,
                    exchange_rate, usd_value, last_updated
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (wallet_id, token_address)
                DO UPDATE SET
                    token_name = EXCLUDED.token_name,
                    token_symbol = EXCLUDED.token_symbol,
                    token_decimals = EXCLUDED.token_decimals,
                    token_icon_url = EXCLUDED.token_icon_url,
                    balance = EXCLUDED.balance,
                    balance_formatted = EXCLUDED.balance_formatted,
                    exchange_rate = EXCLUDED.exchange_rate,
                    usd_value = EXCLUDED.usd_value,
                    last_updated = CURRENT_TIMESTAMP;
            """, (
                wallet_id, token_address, token_name, token_symbol,
                token_decimals, token_icon, value, balance_formatted,
                exchange_rate, usd_value
            ))
            
            updated_count += 1
            
            token_list.append({
                'token_address': token_address,
                'name': token_name,
                'symbol': token_symbol,
                'balance': str(balance_formatted),
                'exchange_rate': exchange_rate,
                'usd_value': float(usd_value)
            })
        
        # Create snapshot
        cur.execute("""
            SELECT SUM(usd_value), COUNT(*) 
            FROM gu_wallet_balances 
            WHERE wallet_id = %s
        """, (wallet_id,))
        
        snapshot_result = cur.fetchone()
        total_value = snapshot_result[0] or Decimal(0)
        token_count = snapshot_result[1] or 0
        
        cur.execute("""
            INSERT INTO gu_wallet_snapshots (
                wallet_id, total_usd_value, token_count, snapshot_data
            )
            VALUES (%s, %s, %s, %s::jsonb)
        """, (wallet_id, total_value, token_count, json.dumps(token_list)))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Updated {updated_count} token balances',
            'tokens': token_list,
            'total_value_usd': float(total_value),
            'token_count': token_count
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error refreshing wallet balances: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def get_wallet_details(user, wallet_id):
    """Get detailed balance information for a wallet."""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Verify wallet belongs to user
        cur.execute("""
            SELECT wallet_address, nickname FROM gu_user_wallets 
            WHERE id = %s AND user_id = %s
        """, (wallet_id, user['user_id']))
        
        wallet_info = cur.fetchone()
        if not wallet_info:
            return jsonify({'success': False, 'error': 'Wallet not found'}), 404
        
        # Get token balances
        cur.execute("""
            SELECT 
                token_address, token_name, token_symbol, token_icon_url,
                balance_formatted, exchange_rate, usd_value, last_updated
            FROM gu_wallet_balances
            WHERE wallet_id = %s
            ORDER BY usd_value DESC;
        """, (wallet_id,))
        
        tokens = []
        total_value = Decimal(0)
        
        for row in cur.fetchall():
            token_data = {
                'token_address': row[0],
                'name': row[1],
                'symbol': row[2],
                'icon_url': row[3],
                'balance': float(row[4]) if row[4] else 0.0,
                'exchange_rate': float(row[5]) if row[5] else 0.0,
                'usd_value': float(row[6]) if row[6] else 0.0,
                'last_updated': row[7].isoformat() if row[7] else None
            }
            tokens.append(token_data)
            total_value += (row[6] or Decimal(0))
        
        return jsonify({
            'success': True,
            'wallet': {
                'id': wallet_id,
                'address': wallet_info[0],
                'nickname': wallet_info[1],
                'tokens': tokens,
                'total_value_usd': float(total_value),
                'token_count': len(tokens)
            }
        })
        
    except Exception as e:
        print(f"Error getting wallet details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


def get_portfolio_summary(user):
    """Get total portfolio summary across all wallets."""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Get overall summary
        cur.execute("""
            SELECT * FROM gu_user_portfolio_summary 
            WHERE user_id = %s;
        """, (user['user_id'],))
        
        summary_row = cur.fetchone()
        
        if not summary_row:
            return jsonify({
                'success': True,
                'portfolio': {
                    'wallet_count': 0,
                    'total_tokens': 0,
                    'total_value_usd': 0.0,
                    'wallets': []
                }
            })
        
        # Get individual wallet summaries
        cur.execute("""
            SELECT * FROM gu_wallet_details 
            WHERE user_id = %s
            ORDER BY is_primary DESC, total_value_usd DESC;
        """, (user['user_id'],))
        
        wallets = []
        for row in cur.fetchall():
            wallets.append({
                'id': row[0],
                'wallet_address': row[2],
                'nickname': row[3],
                'is_primary': row[4],
                'token_count': row[5],
                'total_value_usd': float(row[6]) if row[6] else 0.0,
                'last_updated': row[7].isoformat() if row[7] else None
            })
        
        return jsonify({
            'success': True,
            'portfolio': {
                'wallet_count': summary_row[2] or 0,
                'total_tokens': summary_row[3] or 0,
                'total_value_usd': float(summary_row[4]) if summary_row[4] else 0.0,
                'last_updated': summary_row[5].isoformat() if summary_row[5] else None,
                'wallets': wallets
            }
        })
        
    except Exception as e:
        print(f"Error getting portfolio summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ==================== FLASK ROUTE REGISTRATION ====================

def register_wallet_routes(app):
    """Register all wallet-related routes with the Flask app."""
    
    @app.route('/api/wallets', methods=['POST'])
    @login_required
    def api_add_wallet(user):
        return add_wallet(user)
    
    @app.route('/api/wallets', methods=['GET'])
    @login_required
    def api_get_wallets(user):
        return get_user_wallets(user)
    
    @app.route('/api/wallets/<int:wallet_id>', methods=['PUT'])
    @login_required
    def api_update_wallet(user, wallet_id):
        return update_wallet(user, wallet_id)
    
    @app.route('/api/wallets/<int:wallet_id>', methods=['DELETE'])
    @login_required
    def api_delete_wallet(user, wallet_id):
        return delete_wallet(user, wallet_id)
    
    @app.route('/api/wallets/<int:wallet_id>/refresh', methods=['POST'])
    @login_required
    def api_refresh_wallet(user, wallet_id):
        return refresh_wallet_balances(user, wallet_id)
    
    @app.route('/api/wallets/<int:wallet_id>/details', methods=['GET'])
    @login_required
    def api_wallet_details(user, wallet_id):
        return get_wallet_details(user, wallet_id)
    
    @app.route('/api/portfolio', methods=['GET'])
    @login_required
    def api_portfolio_summary(user):
        return get_portfolio_summary(user)