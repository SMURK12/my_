"""
Gods Unchained Collection Valuation Backend
Optimized for DATA COMPLETENESS - slower but ensures all data is retrieved
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import requests
import time
import json
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os
from auth import get_db, hash_password, create_session, verify_token, login_required
from auth import login_required, get_db
from wallet_portfolio_api import register_wallet_routes
from dotenv import load_dotenv
from orderbook_signing import get_signer
load_dotenv()


import os
print(f"Current directory: {os.getcwd()}")
print(f"proxies.txt exists: {os.path.exists('proxies.txt')}")

if os.path.exists('proxies.txt'):
    with open('proxies.txt', 'r') as f:
        lines = f.readlines()
        print(f"Number of lines in proxies.txt: {len(lines)}")
        print(f"First line: ")

app = Flask(__name__)
CORS(app)
register_wallet_routes(app)

# Add CORS headers for all routes
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Serve the frontend
@app.route('/')
@app.route('/index1.html')
def serve_index():
    return send_file('index1.html')

# ============================================================================
# PROXY CONFIGURATION
# ============================================================================

PROXIES = []
_proxy_lock = threading.Lock()
_proxy_index = 0
_last_request_time = {}
_request_lock = threading.Lock()

def load_proxies(filepath='proxies.txt'):
    """Load proxies from file. Format: host:port:username:password"""
    global PROXIES
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 4:
                            host, port, user, passwd = parts[0], parts[1], parts[2], parts[3]
                            proxy_url = f"http://{user}:{passwd}@{host}:{port}"
                            PROXIES.append({
                                'http': proxy_url,
                                'https': proxy_url
                            })
            print(f"✓ Loaded {len(PROXIES)} residential proxies")
        else:
            print(f"⚠ No proxies.txt found, running without proxies")
    except Exception as e:
        print(f"Error loading proxies: {e}")

def get_proxy():
    """Get next proxy using round-robin for even distribution."""
    global _proxy_index
    if not PROXIES:
        return None
    with _proxy_lock:
        proxy = PROXIES[_proxy_index % len(PROXIES)]
        _proxy_index += 1
        return proxy

import random

def rate_limit(url: str, delay: float = 0.5):
    """Ensure minimum delay between requests with randomization to avoid detection."""
    with _request_lock:
        endpoint = url.split('?')[0]
        now = time.time()
        last_time = _last_request_time.get(endpoint, 0)
        time_since_last = now - last_time
        
        # Add random jitter: 50-150% of base delay
        random_delay = delay * random.uniform(0.5, 1.5)
        
        if time_since_last < random_delay:
            time.sleep(random_delay - time_since_last)
        
        _last_request_time[endpoint] = time.time()

# Load proxies on startup
load_proxies()

# ============================================================================
# CONFIGURATION
# ============================================================================

# Optimized for DATA COMPLETENESS with anti-detection measures
MAX_WORKERS = 50  # Moderate concurrency with randomization
REQUEST_DELAY = 0.0005  # Base delay - actual delay is randomized (0.15-0.45s)
MAX_RETRIES = 15  # Aggressive retries to ensure complete data

API_KEY = "Np8BV2d5QR9TSFEr9EvF66FWcJf0wIxy2qBpOH6s"
TOKEN_ADDRESS = "0x06d92b637dfcdf95a2faba04ef22b2a096029b69"
IMMUTABLE_CONVERSION_API = "https://checkout-api.immutable.com/v1/fiat/conversion"

# Cache for conversion prices
_price_cache = {}
_price_cache_time = 0
_price_cache_lock = threading.Lock()
CACHE_DURATION = 60

TOKEN_MAP = {
    "0x52a6c53869ce09a731cd772f245b97a4401d3348": ("ethereum", 18),
    "0xe0e0981d19ef2e0a57cc48ca60d9454ed2d53feb": ("gods-unchained", 18),
    "0xf57e7e7c23978c3caec3c3548e3d615c346e79ff": ("immutable-x", 18),
    "0x6de8acc0d406837030ce4dd28e7c08c5a96a30d2": ("usd-coin", 6),
    "NATIVE": ("immutable-x", 18),
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
]

def get_headers():
    """Get headers with random user agent."""
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://tokentrove.com",
        "Referer": "https://tokentrove.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": random.choice(USER_AGENTS),
        "X-Api-Key": API_KEY
    }

HEADERS = get_headers()  # Keep for backwards compatibility

# ============================================================================
# PRICE CONVERSION FUNCTIONS
# ============================================================================

def fetch_prices_usd(coin_ids: Optional[List[str]] = None) -> Dict[str, float]:
    """Fetch USD prices from Immutable conversion API with caching."""
    global _price_cache, _price_cache_time
    
    if coin_ids is None:
        coin_ids = list(set(token_info[0] for token_info in TOKEN_MAP.values()))
    
    if not coin_ids:
        return {}
    
    current_time = time.time()
    
    with _price_cache_lock:
        if _price_cache and (current_time - _price_cache_time) < CACHE_DURATION:
            return _price_cache.copy()
    
    unique_ids = sorted(set(coin_ids))
    params = {"ids": ",".join(unique_ids), "currencies": "usd,eth"}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.get(IMMUTABLE_CONVERSION_API, params=params, timeout=10)
            r.raise_for_status()
            payload = r.json()
            
            # Parse the new response format: {"ethereum": {"usd": 2808.47, "eth": 1}, ...}
            with _price_cache_lock:
                _price_cache = {cid: float(payload.get(cid, {}).get("usd", 0.0)) for cid in unique_ids}
                _price_cache_time = current_time
                return _price_cache.copy()
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 5)
                else:
                    with _price_cache_lock:
                        return _price_cache.copy() if _price_cache else {}
            else:
                raise
    
    return {}


def convert_to_usd(item: dict, prices_usd: Dict[str, float]) -> Optional[float]:
    """Convert listing/offer to USD."""
    cur_addr = item.get("currency_address", "")
    if not cur_addr:
        return None
    
    if cur_addr == "NATIVE":
        usd_price = item.get("usd_price")
        if usd_price is not None:
            return float(usd_price)
    
    cur = cur_addr.lower()
    mapping = TOKEN_MAP.get(cur)
    if not mapping:
        return None
    
    coingecko_id, decimals = mapping
    raw_qty = int(item.get("currency_quantity", 0))
    token_amount = raw_qty / (10 ** decimals)
    
    if coingecko_id == "usd-coin":
        return token_amount
    
    price = prices_usd.get(coingecko_id)
    if price is None or price == 0:
        return None
    
    return token_amount * price


# ============================================================================
# API FUNCTIONS WITH AGGRESSIVE RETRY LOGIC
# ============================================================================

def get_collection(owner_address: str) -> List[Dict]:
    """Fetch user's card collection from TokenTrove."""
    url = "https://api.tokentrove.com/tokens"
    params = {"owner": owner_address, "tokenAddress": TOKEN_ADDRESS}
    
    for attempt in range(MAX_RETRIES):
        try:
            rate_limit(url, REQUEST_DELAY)
            proxy = get_proxy()
            headers = get_headers()  # Random UA each request
            response = requests.get(url, headers=headers, params=params, timeout=15, proxies=proxy)
            response.raise_for_status()
            return response.json() or []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1.0)  # Cooldown before next proxy
                    continue
                print(f"⚠ Collection fetch failed after {MAX_RETRIES} attempts: All proxies blocked")
                return []
            elif e.response.status_code == 429:
                if attempt < MAX_RETRIES - 1:
                    wait_time = min(10, (attempt + 1) * 2)
                    print(f"⏱ 429 rate limit, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                print(f"Error fetching collection: {e}")
                return []
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)
                continue
            print(f"Error fetching collection: {e}")
            return []
    return []


def get_listings_and_offers(proto: str, user_address: str, prices_usd: Dict[str, float]) -> Dict:
    """Fetch listings and offers for a specific proto."""
    url = "https://api.tokentrove.com/cached/cheapest"
    params = {
        "tokenAddress": TOKEN_ADDRESS,
        "protos": proto,
        "userAddress": user_address,
        "currencyAddress": "all"
    }
    
    user_addr_lower = user_address.lower()
    
    for attempt in range(MAX_RETRIES):
        try:
            rate_limit(url, REQUEST_DELAY)
            proxy = get_proxy()
            headers = get_headers()  # Random UA each request
            response = requests.get(url, headers=headers, params=params, timeout=15, proxies=proxy)
            response.raise_for_status()
            raw_data = response.json() or []
            
            listings = []
            offers = []
            user_listed_token_ids = []
            listed_token_order_hash = []
            
            for item in raw_data:
                usd_price = convert_to_usd(item, prices_usd)
                currency_addr = item.get("currency_address") or "0x52a6c53869ce09a731cd772f245b97a4401d3348"
                currency_symbol = get_currency_symbol(currency_addr)
                
                result = {
                    "makerAddress": item.get("makerAddress"),
                    "usd_price": round(usd_price, 6) if usd_price else None,
                    "currency_address": currency_addr,
                    "currency_quantity": item.get("currency_quantity"),
                    "currency_symbol": currency_symbol,  # ADD THIS
                    "token_id": item.get("token_id")
                }
                
                if item.get('isBuy') == 0:
                    # Check if this is the user's listing
                    if item.get('makerAddress', '').lower() == user_addr_lower:
                        order_hash = item.get('order_hash')
                        token_id = item.get('token_id')
                        if token_id:
                            user_listed_token_ids.append(token_id)
                            if proto == '0197e72d-4c8b-afc7-59c5-cb42f5928796':
                                print(token_id)
                        if order_hash:
                            listed_token_order_hash.append(order_hash)
                    
                    listings.append(result)
                else:
                    offers.append(result)
            order_identifier = dict(zip(user_listed_token_ids,listed_token_order_hash))
            listings = sorted([l for l in listings if l['usd_price']], key=lambda x: x['usd_price'])
            offers = sorted([o for o in offers if o['usd_price']], key=lambda x: x['usd_price'], reverse=True)
            # Calculate lowest_price excluding user's own listings
            market_listings = [l for l in listings if l['makerAddress'].lower() != user_addr_lower]
            lowest_price = market_listings[0]['usd_price'] if market_listings else None
            highest_bid = offers[0]['usd_price'] if offers else None

            lowest_listing_currency = None
            lowest_listing_currency_symbol = None
            if market_listings:
                lowest_listing_currency = market_listings[0].get('currency_address')
                lowest_listing_currency_symbol = get_currency_symbol(lowest_listing_currency)

            # Calculate ETH amount from USD price using consistent ETH price
            lowest_price_eth = None
            if lowest_price and prices_usd.get('ethereum'):
                eth_price_usd = prices_usd.get('ethereum')
                lowest_price_eth = lowest_price / eth_price_usd
            
            return {
                'listings': listings,
                'offers': offers,
                'lowest_price': lowest_price,
                'lowest_price_eth': lowest_price_eth,
                'lowest_listing_currency': lowest_listing_currency,              # ADD
                'lowest_listing_currency_symbol': lowest_listing_currency_symbol, # ADD
                'highest_bid': highest_bid,
                'user_listed_token_ids': user_listed_token_ids,
                'order_identifier':order_identifier
            }
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1.0)
                    continue
            elif e.response.status_code == 429:
                if attempt < MAX_RETRIES - 1:
                    wait_time = min(10, (attempt + 1) * 2)
                    time.sleep(wait_time)
                    continue
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)
                continue
    
    # Only print error if we've exhausted all retries
    print(f"⚠ Failed to get listings for {proto} after {MAX_RETRIES} attempts")
    return {'listings': [], 'offers': [], 'lowest_price': None, 'highest_bid': None, 'user_listed_token_ids': []}

def convert_historical_to_usd(item: dict, prices_usd: Dict[str, float]) -> Optional[float]:
    """Get USD price from historical sale."""
    cur_addr = item.get("currency", "")
    if not cur_addr:
        return None
    
    if cur_addr == "NATIVE":
        usd_price = item.get("usd_price")
        if usd_price is not None:
            return float(usd_price)
    
    cur = cur_addr.lower()
    mapping = TOKEN_MAP.get(cur)
    if not mapping:
        return None
    
    coingecko_id, decimals = mapping
    raw_qty = int(item.get("takerAssetFilledAmount", 0))
    token_amount = raw_qty / (10 ** decimals)
    
    if coingecko_id == "usd-coin":
        return token_amount
    
    price = prices_usd.get(coingecko_id)
    if price is None or price == 0:
        return None
    
    return token_amount * price


def get_historical_prices(proto: str, prices_usd: Dict[str, float]) -> Dict:
    """Fetch historical price data for a proto."""
    url = "https://api.tokentrove.com/cached/historical-prices"
    params = {
        "tokenAddress": TOKEN_ADDRESS,
        "tokenProto": proto
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            rate_limit(url, REQUEST_DELAY)
            proxy = get_proxy()
            headers = get_headers()  # Random UA each request
            response = requests.get(url, headers=headers, params=params, timeout=15, proxies=proxy)
            response.raise_for_status()
            data = response.json() or []
            
            if not data:
                return {'historical': [], 'last_sold': None, 'last_sold_date': None}
            
            converted_sales = []
            for sale in data:
                usd_price = convert_historical_to_usd(sale, prices_usd)
                if usd_price:
                    converted_sales.append({
                        'usd_price': round(usd_price, 6),
                        'updated_at': sale.get('updated_at'),
                        'isBuy': sale.get('isBuy')
                    })
            
            last_sold = None
            last_sold_date = None
            if converted_sales:
                sorted_sales = sorted(converted_sales, key=lambda x: x.get('updated_at', ''), reverse=True)
                last_sold = sorted_sales[0]['usd_price']
                last_sold_date = sorted_sales[0]['updated_at']
            
            return {
                'historical': converted_sales[-10:],
                'last_sold': last_sold,
                'last_sold_date': last_sold_date
            }
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1.0)
                    continue
            elif e.response.status_code == 429:
                if attempt < MAX_RETRIES - 1:
                    wait_time = min(10, (attempt + 1) * 2)
                    time.sleep(wait_time)
                    continue
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(0.5)
                continue
    
    print(f"⚠ Failed to get historical for {proto} after {MAX_RETRIES} attempts")
    return {'historical': [], 'last_sold': None, 'last_sold_date': None}


def enrich_card(card: Dict, user_address: str, prices_usd: Dict[str, float]) -> Dict:
    """Enrich a card with pricing data."""
    proto = card.get('proto')
    user_addr_lower = user_address.lower()
    
    try:
        metadata = json.loads(card.get('metadata', '{}'))
    except:
        metadata = {}
    
    # Fetch listings and historical data in PARALLEL
    with ThreadPoolExecutor(max_workers=8) as executor:
        listings_future = executor.submit(get_listings_and_offers, proto, user_address, prices_usd)
        historical_future = executor.submit(get_historical_prices, proto, prices_usd)
        
        market_data = listings_future.result()
        historical_data = historical_future.result()
    
    lowest_price = market_data.get('lowest_price')
    last_sold = historical_data.get('last_sold')
    listings = market_data.get('listings', [])
    
    
    # Get user's listed token_ids from market_data
    user_listed_token_ids = market_data.get('user_listed_token_ids', [])
    order_identifier = market_data.get('order_identifier', [])

    # Real value is only valid when BOTH lowest_price AND last_sold exist
    if lowest_price and last_sold:
        real_value = min(lowest_price, last_sold)
    else:
        real_value = 0
    
    highest_bid = market_data.get('highest_bid')
    bid_spread_pct = None
    if lowest_price and highest_bid and highest_bid > 0:
        bid_spread_pct = round(((lowest_price - highest_bid) / highest_bid) * 100, 2)
    
    listing_status = None
    user_listing_price = None
    
    # Find all user listings to get user_listing_price and listing_status
    user_listings = [l for l in listings if l.get('makerAddress', '').lower() == user_addr_lower]
    
    if user_listings:
        user_listing_price = user_listings[0]['usd_price']
        
        if listings and listings[0].get('makerAddress', '').lower() == user_addr_lower:
            listing_status = "lowest"
        else:
            listing_status = "undercut"
    
    # Get all token_ids owned for this proto
    all_token_ids = card.get('ids', [])
    
    # Calculate unlisted token_ids (owned but not listed)
    unlisted_token_ids = [tid for tid in all_token_ids if tid not in user_listed_token_ids]
    
    # Calculate counts
    count = card.get('count', 1)
    listed_count = len(user_listed_token_ids)
    unlisted_count = len(unlisted_token_ids)
    
    return {
        'ids': all_token_ids,
        'count': count,
        'listed_count': listed_count,
        'unlisted_count': unlisted_count,
        'proto': proto,
        'metadata': metadata,
        'pCount': card.get('pCount'),
        'listings': listings[:5],
        'offers': market_data.get('offers', [])[:5],
        'lowest_price': lowest_price,
        'lowest_price_eth': market_data.get('lowest_price_eth'),
        'highest_bid': highest_bid,
        'bid_spread_pct': bid_spread_pct,
        'listing_status': listing_status,
        'user_listing_price': user_listing_price,
        'user_listed_token_ids': user_listed_token_ids,
        'order_identifier':order_identifier,
        'unlisted_token_ids': unlisted_token_ids,
        'historical': historical_data.get('historical', []),
        'last_sold': last_sold,
        'last_sold_date': historical_data.get('last_sold_date'),
        'real_value': real_value,
        'total_listing_value': round(lowest_price * count, 6) if lowest_price else None,
        'total_bid_value': round(highest_bid * count, 6) if highest_bid else None,
        'total_last_sold_value': round(last_sold * count, 6) if last_sold else None,
        'total_real_value': round(real_value * count, 6) if real_value else None,
    }
def get_all_user_notifications(user_address: str) -> List[Dict]:
    """Fetch ALL user notifications using 'before' timestamp pagination."""
    url = "https://api.tokentrove.com/user-notifications"
    all_notifications = []
    
    print(f"📥 Fetching all notifications for {user_address}")
    
    batch_count = 0
    max_batches = 500
    before_time = None
    
    while batch_count < max_batches:
        params = {
            "user": user_address,
            "limit": 100  # Try to get 100 per batch
        }
        
        # Add 'before' parameter if we have it
        if before_time:
            params['before'] = before_time
        
        for attempt in range(MAX_RETRIES):
            try:
                rate_limit(url, REQUEST_DELAY)
                proxy = get_proxy()
                headers = get_headers()
                
                response = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxy)
                response.raise_for_status()
                data = response.json() or []
                
                if not data:
                    print(f"✅ Fetched total {len(all_notifications)} notifications across {batch_count} batches")
                    return all_notifications
                
                # Get existing token IDs to avoid duplicates
                existing_ids = {n.get('token_id') for n in all_notifications}
                
                # Add new unique notifications
                new_notifications = [n for n in data if n.get('token_id') not in existing_ids]
                all_notifications.extend(new_notifications)
                
                batch_count += 1
                print(f"  📄 Batch {batch_count}: {len(data)} returned, {len(new_notifications)} new (total={len(all_notifications)})")
                
                # If no new notifications were added, we're done
                if len(new_notifications) == 0:
                    print(f"✅ No more new notifications found, total: {len(all_notifications)}")
                    return all_notifications
                
                # Get the oldest notification's timestamp for next batch
                if data:
                    # Sort by timestamp to get the oldest
                    sorted_data = sorted(data, key=lambda x: x.get('updated_at', ''))
                    oldest = sorted_data[0]
                    before_time = oldest.get('updated_at')
                    
                    if not before_time:
                        print(f"⚠ No timestamp found, stopping pagination")
                        return all_notifications
                    
                    print(f"  ⏪ Next batch will use before={before_time}")
                else:
                    break
                
                break
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403 and attempt < MAX_RETRIES - 1:
                    time.sleep(1.0)
                    continue
                elif e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    wait_time = min(10, (attempt + 1) * 2)
                    print(f"⏱ Rate limit hit, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ Error in batch {batch_count}: {e}")
                    return all_notifications
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.5)
                    continue
                print(f"❌ Error in batch {batch_count}: {e}")
                return all_notifications
        else:
            # All retries failed
            return all_notifications
    
    print(f"✅ Reached max batches ({max_batches}), returning {len(all_notifications)} notifications")
    return all_notifications
def parse_notification_sales(notifications: List[Dict]) -> Dict[str, List[Dict]]:
    """Parse notifications and group sales by proto."""
    sales_by_proto = {}
    
    for notif in notifications:
        if notif.get('type') != 'SALE':
            continue
        
        proto = notif.get('token_proto')
        if not proto:
            continue
        
        # Parse notification_data
        try:
            notif_data = json.loads(notif.get('notification_data', '{}'))
        except:
            notif_data = {}
        
        # Extract price (it's in ETH as a string)
        price_eth_str = notif_data.get('price', '0')
        try:
            price_eth = float(price_eth_str)
        except:
            price_eth = 0
        
        sale_info = {
            'token_id': notif.get('token_id'),
            'price_eth': price_eth,
            'currency_address': notif_data.get('currency_address'),
            'card_name': notif_data.get('name'),
            'card_img': notif_data.get('img'),
            'sold_at': notif.get('updated_at')
        }
        
        if proto not in sales_by_proto:
            sales_by_proto[proto] = []
        
        sales_by_proto[proto].append(sale_info)
    
    return sales_by_proto

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/sales/<wallet_address>', methods=['GET'])
def get_user_sales(wallet_address: str):
    """Get all sale notifications for a user."""
    try:
        # Fetch all notifications
        notifications = get_all_user_notifications(wallet_address)
        
        # Parse and group by proto
        sales_by_proto = parse_notification_sales(notifications)
        
        # Calculate summary statistics
        total_sales = len(notifications)
        unique_cards_sold = len(sales_by_proto)
        
        # Get ETH price for USD conversion
        prices_usd = fetch_prices_usd(['ethereum'])
        eth_price = prices_usd.get('ethereum', 0)
        
        # Calculate total value
        total_value_eth = sum(
            sale['price_eth'] 
            for sales in sales_by_proto.values() 
            for sale in sales
        )
        total_value_usd = total_value_eth * eth_price if eth_price else 0
        
        # Get top sales
        all_sales = []
        for proto, sales in sales_by_proto.items():
            for sale in sales:
                all_sales.append({
                    **sale,
                    'proto': proto,
                    'price_usd': sale['price_eth'] * eth_price if eth_price else 0
                })
        
        # Sort by USD value
        all_sales.sort(key=lambda x: x.get('price_usd', 0), reverse=True)
        
        return jsonify({
            'success': True,
            'wallet': wallet_address,
            'summary': {
                'total_sales': total_sales,
                'unique_cards_sold': unique_cards_sold,
                'total_value_eth': round(total_value_eth, 6),
                'total_value_usd': round(total_value_usd, 2),
                'eth_price': eth_price
            },
            'sales_by_proto': sales_by_proto,
            'top_sales': all_sales[:20],  # Top 20 sales
            'all_sales': all_sales
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/collection/<wallet_address>', methods=['GET'])
def get_wallet_collection(wallet_address: str):
    """Get full collection valuation for a wallet."""
    import time as timing
    start_time = timing.time()
    
    try:
        collection = get_collection(wallet_address)
        print(f"⏱ Collection fetched: {len(collection)} cards in {timing.time() - start_time:.2f}s")
        
        if not collection:
            return jsonify({
                'success': True,
                'wallet': wallet_address,
                'cards': [],
                'summary': {
                    'total_cards': 0,
                    'unique_cards': 0,
                    'total_listing_value': 0,
                    'total_bid_value': 0,
                    'total_last_sold_value': 0,
                    'total_real_value': 0
                }
            })
        
        prices_usd = fetch_prices_usd()
        
        enrich_start = timing.time()
        enriched_cards = []
        
        total_cards = len(collection)
        processed = 0
        with_listings = 0
        with_historical = 0
        with_bids = 0
        progress_lock = threading.Lock()
        
        def enrich_with_progress(card):
            nonlocal processed, with_listings, with_historical, with_bids
            result = enrich_card(card, wallet_address, prices_usd)
            
            with progress_lock:
                processed += 1
                if result.get('lowest_price'):
                    with_listings += 1
                if result.get('last_sold'):
                    with_historical += 1
                if result.get('highest_bid'):
                    with_bids += 1
                
                if processed % 10 == 0 or processed == total_cards:
                    print(f"⏳ Progress: {processed}/{total_cards} cards | "
                          f"Listings: {with_listings} | Historical: {with_historical} | Bids: {with_bids}")
            
            return result
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(enrich_with_progress, card): card 
                for card in collection
            }
            
            for future in as_completed(futures):
                try:
                    enriched_cards.append(future.result())
                except Exception as e:
                    print(f"Error enriching card: {e}")
        
        print(f"✅ Done! {with_listings}/{total_cards} with listings, "
              f"{with_historical}/{total_cards} with historical, "
              f"{with_bids}/{total_cards} with bids")
        print(f"⏱ Cards enriched in {timing.time() - enrich_start:.2f}s")
        print(f"⏱ Total time: {timing.time() - start_time:.2f}s")
        
        total_cards = sum(c.get('count', 1) for c in enriched_cards)
        unique_cards = len(enriched_cards)
        
        total_listing_value = sum(c.get('total_listing_value') or 0 for c in enriched_cards)
        total_bid_value = sum(c.get('total_bid_value') or 0 for c in enriched_cards)
        total_last_sold_value = sum(c.get('total_last_sold_value') or 0 for c in enriched_cards)
        total_real_value = sum(c.get('total_real_value') or 0 for c in enriched_cards)
        
        lowest_count = len([c for c in enriched_cards if c.get('listing_status') == 'lowest'])
        undercut_count = len([c for c in enriched_cards if c.get('listing_status') == 'undercut'])
        
        enriched_cards.sort(key=lambda x: x.get('total_real_value') or 0, reverse=True)
        
        return jsonify({
            'success': True,
            'wallet': wallet_address,
            'cards': enriched_cards,
            'summary': {
                'total_cards': total_cards,
                'unique_cards': unique_cards,
                'total_listing_value': round(total_listing_value, 2),
                'total_bid_value': round(total_bid_value, 2),
                'total_last_sold_value': round(total_last_sold_value, 2),
                'total_real_value': round(total_real_value, 2),
                'lowest_count': lowest_count,
                'undercut_count': undercut_count,
                'avg_bid_spread_pct': round(
                    sum(c.get('bid_spread_pct') or 0 for c in enriched_cards if c.get('bid_spread_pct')) /
                    max(1, len([c for c in enriched_cards if c.get('bid_spread_pct')])),
                    2
                ) if any(c.get('bid_spread_pct') for c in enriched_cards) else None
            }
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/card/<proto>', methods=['GET'])
def get_card_details(proto: str):
    """Get detailed pricing for a specific card proto."""
    user_address = request.args.get('wallet', '0x0000000000000000000000000000000000000000')
    
    try:
        prices_usd = fetch_prices_usd()
        market_data = get_listings_and_offers(proto, user_address, prices_usd)
        historical_data = get_historical_prices(proto, prices_usd)
        
        return jsonify({
            'success': True,
            'proto': proto,
            **market_data,
            **historical_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/prices', methods=['GET'])
def get_current_prices():
    """Get current token prices."""
    try:
        prices = fetch_prices_usd()
        return jsonify({'success': True, 'prices': prices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    wallet_address = data.get('wallet_address', '')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        password_hash = hash_password(password)
        cur.execute("""
            INSERT INTO gu_users (username, password_hash, wallet_address)
            VALUES (%s, %s, %s)
            RETURNING id, username
        """, (username, password_hash, wallet_address))
        
        user = cur.fetchone()
        conn.commit()
        
        token = create_session(user[0])
        
        return jsonify({
            'success': True,
            'user': {'id': user[0], 'username': user[1]},
            'token': token
        })
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'success': False, 'error': 'Username already exists'}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/login', methods=['POST'])
def login():
    """Login user and return session token."""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        password_hash = hash_password(password)
        cur.execute("""
            SELECT id, username, wallet_address 
            FROM gu_users 
            WHERE username = %s AND password_hash = %s
        """, (username, password_hash))
        
        user = cur.fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        token = create_session(user[0])
        
        return jsonify({
            'success': True,
            'user': {
                'id': user[0],
                'username': user[1],
                'wallet_address': user[2]
            },
            'token': token
        })
    finally:
        cur.close()
        conn.close()


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout user by deleting session token."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        return jsonify({'success': False, 'error': 'No token provided'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM gu_sessions WHERE token = %s", (token,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Logged out successfully'})
    finally:
        cur.close()
        conn.close()


@app.route('/api/me', methods=['GET'])
@login_required
def get_current_user(user):
    """Get current logged-in user info."""
    return jsonify({'success': True, 'user': user})

@app.route('/login.html')
def serve_login():
    return send_file('login.html')

# ============================================================================
# SAVED COLLECTIONS ROUTES
# ============================================================================

@app.route('/api/collections/save', methods=['POST'])
@login_required
def save_collection(user):
    """Save a collection for the logged-in user."""
    data = request.json
    wallet_address = data.get('wallet_address')
    collection_name = data.get('collection_name', f"Collection {wallet_address[:8]}")
    collection_data = data.get('collection_data')
    summary_data = data.get('summary_data')
    
    if not wallet_address or not collection_data:
        return jsonify({'success': False, 'error': 'Missing required data'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # Extract summary values
        total_cards = summary_data.get('total_cards', 0)
        unique_cards = summary_data.get('unique_cards', 0)
        total_listing_value = summary_data.get('total_listing_value', 0)
        total_bid_value = summary_data.get('total_bid_value', 0)
        total_last_sold_value = summary_data.get('total_last_sold_value', 0)
        total_real_value = summary_data.get('total_real_value', 0)
        
        cur.execute("""
            INSERT INTO gu_saved_collections 
            (user_id, wallet_address, collection_name, collection_data, summary_data,
             total_cards, unique_cards, total_listing_value, total_bid_value, 
             total_last_sold_value, total_real_value, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id, saved_at
        """, (
            user['user_id'], wallet_address, collection_name, 
            json.dumps(collection_data), json.dumps(summary_data),
            total_cards, unique_cards, total_listing_value, total_bid_value,
            total_last_sold_value, total_real_value
        ))
        
        result = cur.fetchone()
        conn.commit()
        
        return jsonify({
            'success': True,
            'collection_id': result[0],
            'saved_at': result[1].isoformat(),
            'message': 'Collection saved successfully'
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/collections/list', methods=['GET'])
@login_required
def list_saved_collections(user):
    """Get all saved collections for the logged-in user."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, wallet_address, collection_name, 
                   total_cards, unique_cards, total_listing_value, 
                   total_bid_value, total_last_sold_value, total_real_value,
                   saved_at, updated_at
            FROM gu_saved_collections
            WHERE user_id = %s
            ORDER BY updated_at DESC
        """, (user['user_id'],))
        
        collections = []
        for row in cur.fetchall():
            collections.append({
                'id': row[0],
                'wallet_address': row[1],
                'collection_name': row[2],
                'total_cards': row[3],
                'unique_cards': row[4],
                'total_listing_value': float(row[5]) if row[5] else 0,
                'total_bid_value': float(row[6]) if row[6] else 0,
                'total_last_sold_value': float(row[7]) if row[7] else 0,
                'total_real_value': float(row[8]) if row[8] else 0,
                'saved_at': row[9].isoformat(),
                'updated_at': row[10].isoformat()
            })
        
        return jsonify({'success': True, 'collections': collections})
    finally:
        cur.close()
        conn.close()


@app.route('/api/collections/<int:collection_id>', methods=['GET'])
@login_required
def get_saved_collection(user, collection_id):
    """Load a specific saved collection."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT wallet_address, collection_name, collection_data, summary_data
            FROM gu_saved_collections
            WHERE id = %s AND user_id = %s
        """, (collection_id, user['user_id']))
        
        result = cur.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        return jsonify({
            'success': True,
            'wallet': result[0],
            'collection_name': result[1],
            'cards': result[2],  # Already JSON
            'summary': result[3]  # Already JSON
        })
    finally:
        cur.close()
        conn.close()


@app.route('/api/collections/<int:collection_id>', methods=['DELETE'])
@login_required
def delete_saved_collection(user, collection_id):
    """Delete a saved collection."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM gu_saved_collections
            WHERE id = %s AND user_id = %s
            RETURNING id
        """, (collection_id, user['user_id']))
        
        result = cur.fetchone()
        conn.commit()
        
        if not result:
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        return jsonify({'success': True, 'message': 'Collection deleted'})
    finally:
        cur.close()
        conn.close()


@app.route('/api/collections/<int:collection_id>/update', methods=['PUT'])
@login_required
def update_saved_collection(user, collection_id):
    """Update/refresh a saved collection with new data."""
    data = request.json
    collection_data = data.get('collection_data')
    summary_data = data.get('summary_data')
    collection_name = data.get('collection_name')
    
    if not collection_data or not summary_data:
        return jsonify({'success': False, 'error': 'Missing required data'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # Extract summary values
        total_cards = summary_data.get('total_cards', 0)
        unique_cards = summary_data.get('unique_cards', 0)
        total_listing_value = summary_data.get('total_listing_value', 0)
        total_bid_value = summary_data.get('total_bid_value', 0)
        total_last_sold_value = summary_data.get('total_last_sold_value', 0)
        total_real_value = summary_data.get('total_real_value', 0)
        
        # Build update query dynamically based on what's provided
        update_fields = [
            "collection_data = %s",
            "summary_data = %s",
            "total_cards = %s",
            "unique_cards = %s",
            "total_listing_value = %s",
            "total_bid_value = %s",
            "total_last_sold_value = %s",
            "total_real_value = %s",
            "updated_at = NOW()"
        ]
        
        params = [
            json.dumps(collection_data),
            json.dumps(summary_data),
            total_cards, unique_cards, total_listing_value, total_bid_value,
            total_last_sold_value, total_real_value
        ]
        
        if collection_name:
            update_fields.append("collection_name = %s")
            params.append(collection_name)
        
        params.extend([collection_id, user['user_id']])
        
        cur.execute(f"""
            UPDATE gu_saved_collections
            SET {', '.join(update_fields)}
            WHERE id = %s AND user_id = %s
            RETURNING id, updated_at
        """, params)
        
        result = cur.fetchone()
        conn.commit()
        
        if not result:
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        return jsonify({
            'success': True,
            'collection_id': result[0],
            'updated_at': result[1].isoformat(),
            'message': 'Collection updated successfully'
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
@app.route('/api/test-notifications/<wallet_address>', methods=['GET'])
def test_notifications(wallet_address: str):
    """Test endpoint to see raw notification response."""
    url = "https://api.tokentrove.com/user-notifications"
    
    # Test different parameter combinations
    test_results = {}
    
    # Test 1: No parameters except user
    try:
        params1 = {"user": wallet_address}
        proxy = get_proxy()
        headers = get_headers()
        response1 = requests.get(url, headers=headers, params=params1, timeout=30, proxies=proxy)
        data1 = response1.json() or []
        test_results['no_params'] = {
            'count': len(data1),
            'sample': data1[:2] if data1 else []
        }
    except Exception as e:
        test_results['no_params'] = {'error': str(e)}
    
    # Test 2: With limit=1000
    try:
        params2 = {"user": wallet_address, "limit": 1000}
        proxy = get_proxy()
        headers = get_headers()
        response2 = requests.get(url, headers=headers, params=params2, timeout=30, proxies=proxy)
        data2 = response2.json() or []
        test_results['limit_1000'] = {
            'count': len(data2),
            'sample': data2[:2] if data2 else []
        }
    except Exception as e:
        test_results['limit_1000'] = {'error': str(e)}
    
    # Test 3: With offset
    try:
        params3 = {"user": wallet_address, "offset": 20, "limit": 100}
        proxy = get_proxy()
        headers = get_headers()
        response3 = requests.get(url, headers=headers, params=params3, timeout=30, proxies=proxy)
        data3 = response3.json() or []
        test_results['offset_20'] = {
            'count': len(data3),
            'sample': data3[:2] if data3 else []
        }
    except Exception as e:
        test_results['offset_20'] = {'error': str(e)}
    
    return jsonify({
        'success': True,
        'wallet': wallet_address,
        'tests': test_results
    })

@app.route('/api/raw-notifications/<wallet_address>')
def raw_notifications(wallet_address: str):
    """Return raw API response for debugging."""
    url = "https://api.tokentrove.com/user-notifications"
    
    # Just get the basic response
    try:
        params = {"user": wallet_address}
        proxy = get_proxy()
        headers = get_headers()
        
        response = requests.get(url, headers=headers, params=params, timeout=30, proxies=proxy)
        response.raise_for_status()
        data = response.json() or []
        
        # Also try with limit
        params2 = {"user": wallet_address, "limit": 1000}
        response2 = requests.get(url, headers=headers, params=params2, timeout=30, proxies=proxy)
        data2 = response2.json() or []
        
        return jsonify({
            'success': True,
            'without_limit': {
                'count': len(data),
                'data': data
            },
            'with_limit_1000': {
                'count': len(data2),
                'data': data2
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# http://127.0.0.1:5000/api/test-notifications/0x11493ba58a5a3bb88332b3dcc5cc11e80e6711d2

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

@app.route('/orderbook-integration.js')
def serve_orderbook():
    return send_file('orderbook-integration.js', mimetype='application/javascript')

@app.route('/demo.html')
def serve_demo():
    return send_file('demo.html')

# Add this endpoint to your app2.py file

@app.route('/api/cancel-orders', methods=['POST', 'OPTIONS'])
def cancel_orders_proxy():
    """
    Proxy endpoint to cancel orders on Immutable API
    Avoids CORS issues by making the request from the server
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        order_ids = data.get('order_ids', [])
        signature = data.get('signature')
        signer = data.get('signer')
        
        print(f"Received cancel request for {len(order_ids)} orders")
        print(f"Order IDs: {order_ids}")
        print(f"Signer: {signer}")
        print(f"Signature: {signature[:20]}...")
        
        if not order_ids or not signature or not signer:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: order_ids, signature, signer'
            }), 400
        
        # Try the correct Immutable API endpoint format
        # It might be /v1/orders/cancel or /v1/orders/cancellations
        api_url = 'https://api.immutable.com/v1/orderbook/orders/cancel'
        
        payload = {
            'order_ids': order_ids,
            'signature': signature,
            'account_address': signer  # might be 'account_address' instead of 'signer'
        }
        
        print(f"Sending to Immutable API: {api_url}")
        print(f"Payload: {payload}")
        
        immutable_response = requests.post(
            api_url,
            headers={
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=30
        )
        
        print(f"Immutable response status: {immutable_response.status_code}")
        print(f"Immutable response: {immutable_response.text}")
        
        if immutable_response.status_code == 200 or immutable_response.status_code == 201:
            return jsonify({
                'success': True,
                'result': immutable_response.json() if immutable_response.text else {}
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Immutable API error: {immutable_response.status_code}',
                'details': immutable_response.text
            }), immutable_response.status_code
            
    except Exception as e:
        print(f"Exception in cancel_orders_proxy: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    


@app.route('/api/orderbook/list-card', methods=['POST', 'OPTIONS'])
@login_required
def list_card(user):
    """List a single card for sale using backend signing"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        required_fields = ['token_id', 'token_address', 'buy_token', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing: {field}'}), 400
        
        print(f"📤 Listing card {data['token_id']}...")
        signer = get_signer()
        
        result = signer.sign_and_list(
            token_address=data['token_address'],
            token_id=data['token_id'],
            buy_token=data['buy_token'],
            amount=data['amount']
        )
        
        if result['success']:
            print(f"✅ Card {data['token_id']} listed")
            return jsonify(result), 200
        else:
            print(f"❌ Failed: {result.get('error')}")
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orderbook/bulk-list', methods=['POST', 'OPTIONS'])
def bulk_list_cards_endpoint():
    if request.method == 'OPTIONS':
        return '', 200
    
    # Auth check
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'success': False, 'error': 'No token'}), 401
    
    if token.startswith('Bearer '):
        token = token[7:]
    
    from auth import verify_token
    user = verify_token(token)
    if not user:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        data = request.json
        
        # DEBUG: Print what we received
        print("📋 Received data:", data)
        if 'listings' in data and len(data['listings']) > 0:
            print("📋 First listing:", data['listings'][0])
        
        if 'listings' not in data:
            return jsonify({'success': False, 'error': 'listings required'}), 400
        
        from orderbook_signing import get_signer
        signer = get_signer()
        results = signer.bulk_list_cards(data['listings'])
        
        return jsonify({'success': True, 'results': results}), 200
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/orderbook/wallet-info', methods=['GET', 'OPTIONS'])
@login_required
def get_wallet_info(user):
    """Get automation wallet information"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        signer = get_signer()
        return jsonify({
            'success': True,
            'address': signer.address,
            'user_address': user.get('wallet_address'),
            'matches_user': signer.address.lower() == (user.get('wallet_address') or '').lower()
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orderbook/sign', methods=['POST', 'OPTIONS'])
def sign_orderbook_message():
    if request.method == 'OPTIONS':
        return '', 200
    
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'success': False, 'error': 'No token'}), 401
    
    if token.startswith('Bearer '):
        token = token[7:]
    
    from auth import verify_token
    user = verify_token(token)
    if not user:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        data = request.json
        from orderbook_signing import get_signer
        
        signer = get_signer()
        
        signature = signer.sign_typed_data(
            domain=data['domain'],
            types=data['types'],
            value=data['value']
        )
        
        return jsonify({'success': True, 'signature': signature}), 200
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orderbook/get-key', methods=['GET', 'OPTIONS'])
def get_automation_key():
    if request.method == 'OPTIONS':
        return '', 200
    
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'success': False, 'error': 'No token'}), 401
    
    if token.startswith('Bearer '):
        token = token[7:]
    
    from auth import verify_token
    user = verify_token(token)
    if not user:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    try:
        import os
        key = os.getenv('AUTOMATION_WALLET_PRIVATE_KEY')
        if not key:
            return jsonify({'success': False, 'error': 'No key configured'}), 500
        
        # Add 0x prefix if not present
        if not key.startswith('0x'):
            key = '0x' + key
            
        return jsonify({'success': True, 'private_key': key}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True, port=5000)