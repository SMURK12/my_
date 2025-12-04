"""
Authentication module for GU Collection Valuator
"""

import psycopg2
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

DATABASE_URL = "postgresql://thesis_rsc9_user:ydWX0M6oSpQvvaRNBFA8ztpoI2JDdMor@dpg-d3ia2pumcj7s7392m7d0-a.oregon-postgres.render.com/gu_collection_valuator"

def get_db():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)

def hash_password(password):
    """Simple password hashing (use bcrypt in production)."""
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(user_id):
    """Create a new session token for user."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)  # 7 day sessions
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO gu_sessions (user_id, token, expires_at)
            VALUES (%s, %s, %s)
            RETURNING token
        """, (user_id, token, expires_at))
        conn.commit()
        return token
    finally:
        cur.close()
        conn.close()

def verify_token(token):
    """Verify session token and return user_id if valid."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT user_id, username, wallet_address 
            FROM gu_sessions 
            JOIN gu_users ON gu_sessions.user_id = gu_users.id
            WHERE token = %s AND expires_at > NOW()
        """, (token,))
        result = cur.fetchone()
        if result:
            return {'user_id': result[0], 'username': result[1], 'wallet_address': result[2]}
        return None
    finally:
        cur.close()
        conn.close()

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        return f(user, *args, **kwargs)
    return decorated_function