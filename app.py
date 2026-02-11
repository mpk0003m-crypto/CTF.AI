from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import json
import re
import requests
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Add CORS headers for API responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov'}
ALLOWED_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mov'}

# Max file sizes
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB for images
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB for videos

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'rentals'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'feedback'), exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_media_file(filename):
    """Check if file is allowed image or video"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_MEDIA_EXTENSIONS

def get_media_type(filename):
    """Get media type from filename"""
    if '.' not in filename:
        return None
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_EXTENSIONS:
        return 'image'
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        return 'video'
    return None

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect('localfarmer.db')
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    # PRAGMA doesn't support parameterized queries, but table_name is hardcoded as 'users'
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def init_db():
    """Initialize database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT UNIQUE NOT NULL,
            village TEXT NOT NULL,
            mandal TEXT NOT NULL,
            district TEXT NOT NULL,
            location TEXT NOT NULL,
            user_type TEXT NOT NULL,
            preferred_language TEXT NOT NULL,
            password TEXT NOT NULL,
            phone_verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add new columns if they don't exist (for existing databases)
    columns_to_add = [
        ('village', 'TEXT'),
        ('mandal', 'TEXT'),
        ('district', 'TEXT'),
        ('user_type', 'TEXT'),
        ('preferred_language', 'TEXT'),
        ('phone_verified', 'INTEGER DEFAULT 0')
    ]
    
    for col_name, col_type in columns_to_add:
        if not column_exists(cursor, 'users', col_name):
            try:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
            except Exception as e:
                print(f"Warning: Could not add column {col_name}: {e}")
    
    conn.commit()
    
    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            price REAL NOT NULL,
            images TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Customer requirements table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity TEXT NOT NULL,
            location TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Contact messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_info TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Government schemes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS government_schemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_name TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            description TEXT,
            benefits TEXT,
            eligibility TEXT,
            required_documents TEXT,
            apply_link TEXT,
            official_website TEXT,
            state TEXT,
            category TEXT,
            last_updated TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Rental items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rental_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            price_per_hour REAL,
            price_per_day REAL NOT NULL,
            location TEXT NOT NULL,
            availability_status TEXT DEFAULT 'available',
            images TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Rental feedback table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rental_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rental_id INTEGER NOT NULL,
            user_id INTEGER,
            reviewer_name TEXT,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rental_id) REFERENCES rental_items (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Rental media table for photos and videos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rental_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rental_id INTEGER NOT NULL,
            media_type TEXT NOT NULL CHECK(media_type IN ('image', 'video')),
            media_path TEXT NOT NULL,
            filename TEXT,
            file_size INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rental_id) REFERENCES rental_items (id)
        )
    ''')
    
    # User activity history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER,
            item_name TEXT NOT NULL,
            owner_name TEXT,
            location TEXT,
            action_status TEXT DEFAULT 'completed',
            extra_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # User feedback table (for product/farmer feedback)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            farmer_id INTEGER NOT NULL,
            product_id INTEGER,
            reviewer_name TEXT NOT NULL,
            reviewer_phone TEXT,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            images TEXT,
            videos TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (farmer_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id),
            UNIQUE(product_id, user_id)
        )
    ''')
    
    # Add images and videos columns if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE user_feedback ADD COLUMN images TEXT')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE user_feedback ADD COLUMN videos TEXT')
    except:
        pass
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_product_user_feedback ON user_feedback(product_id, user_id)')
    except:
        pass
    
    # Rental requirements table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rental_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            farmer_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            rental_category TEXT NOT NULL,
            field_area TEXT,
            village TEXT,
            mandal TEXT,
            district TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Saved items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('product_posted', 'rental_posted', 'product_requirement_posted', 'rental_requirement_posted')),
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            related_item_id INTEGER,
            related_item_type TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Add user_id column to customer_requirements if not exists
    try:
        cursor.execute('ALTER TABLE customer_requirements ADD COLUMN user_id INTEGER')
    except:
        pass
    
    # Add status column to customer_requirements if not exists
    try:
        cursor.execute('ALTER TABLE customer_requirements ADD COLUMN status TEXT DEFAULT "active"')
    except:
        pass
    
    # Add pin_code column to customer_requirements if not exists
    try:
        cursor.execute('ALTER TABLE customer_requirements ADD COLUMN pin_code TEXT DEFAULT ""')
    except:
        pass
    
    # Add special_instructions column to customer_requirements if not exists
    try:
        cursor.execute('ALTER TABLE customer_requirements ADD COLUMN special_instructions TEXT DEFAULT ""')
    except:
        pass
    
    # Add preferred_delivery_date column to customer_requirements if not exists
    try:
        cursor.execute('ALTER TABLE customer_requirements ADD COLUMN preferred_delivery_date TEXT DEFAULT ""')
    except:
        pass
    
    # Add status column to products if not exists
    try:
        cursor.execute('ALTER TABLE products ADD COLUMN status TEXT DEFAULT "active"')
    except:
        pass
    
    # Add user_type, preferred_language, profile_photo columns to users if not exists
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN user_type TEXT DEFAULT "farmer"')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN preferred_language TEXT DEFAULT "en"')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN profile_photo TEXT')
    except:
        pass
    
    # Live prices table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS live_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            min_price REAL NOT NULL,
            max_price REAL NOT NULL,
            price_unit TEXT DEFAULT 'Kg',
            price_trend TEXT NOT NULL CHECK(price_trend IN ('increased', 'decreased', 'stable')),
            market_name TEXT,
            phone TEXT NOT NULL,
            area TEXT,
            city TEXT,
            district TEXT,
            state TEXT,
            pin_code TEXT,
            latitude REAL,
            longitude REAL,
            images TEXT,
            videos TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Live price feedback table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS live_price_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_id INTEGER NOT NULL,
            user_id INTEGER,
            farmer_name TEXT,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (price_id) REFERENCES live_prices (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Migration: Check if old schema exists and migrate if needed
    try:
        cursor.execute("PRAGMA table_info(live_price_feedback)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # If table exists but doesn't have price_id column, recreate it
        if columns and 'price_id' not in columns:
            print("Migrating live_price_feedback table...")
            cursor.execute('DROP TABLE IF EXISTS live_price_feedback')
            cursor.execute('''
                CREATE TABLE live_price_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    price_id INTEGER NOT NULL,
                    user_id INTEGER,
                    farmer_name TEXT,
                    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (price_id) REFERENCES live_prices (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            print("Migration completed.")
    except Exception as e:
        print(f"Migration check: {e}")
        pass

    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Ensure live_prices upload directory exists
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'live_prices'), exist_ok=True)

def login_required(f):
    """Decorator to require login for HTML routes (redirects)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'info')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def api_login_required(f):
    """Decorator to require login for API routes (returns JSON)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page"""
    # Verify session is set
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/api/register', methods=['POST'])
def register():
    """Handle user registration with step-based flow"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        village = data.get('village', '').strip()
        mandal = data.get('mandal', '').strip()
        district = data.get('district', '').strip()
        user_type = data.get('userType', '').strip()
        preferred_language = data.get('language', '').strip()
        password = data.get('password', '').strip()
        
        # Validation
        if not all([name, phone, village, mandal, district, user_type, preferred_language, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        # Validate name (letters only)
        if not re.match(r'^[A-Za-z\s]+$', name):
            return jsonify({'success': False, 'message': 'Name must contain only letters'}), 400
        
        # Validate phone (10 digits)
        if not re.match(r'^[0-9]{10}$', phone):
            return jsonify({'success': False, 'message': 'Phone must be 10 digits'}), 400
        
        # Validate password (exactly 3 alphanumeric characters)
        if not re.match(r'^[A-Za-z0-9]{3}$', password):
            return jsonify({'success': False, 'message': 'Password must be exactly 3 alphanumeric characters'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if phone already exists
        cursor.execute('SELECT id FROM users WHERE phone = ?', (phone,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Mobile number already registered'}), 400
        
        # Create location string
        location = f"{village}, {mandal}, {district}"
        
        # Create user (email defaults to empty string to satisfy NOT NULL constraint in older databases)
        email = data.get('email', '').strip()
        hashed_password = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (name, email, phone, village, mandal, district, location, user_type, preferred_language, password, phone_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, village, mandal, district, location, user_type, preferred_language, hashed_password, 1))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Set session
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_phone'] = phone
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': {
                'id': user_id,
                'name': name,
                'phone': phone,
                'village': village,
                'mandal': mandal,
                'district': district,
                'location': location,
                'userType': user_type,
                'preferredLanguage': preferred_language,
                'created_at': datetime.now().isoformat()
            }
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Handle user login with mobile + password"""
    try:
        data = request.get_json()
        
        phone = data.get('phone', '').strip()
        password = data.get('password', '').strip()
        
        if not phone or not password:
            return jsonify({'success': False, 'message': 'Mobile number and password are required'}), 400
        
        # Validate phone format
        if not re.match(r'^[0-9]{10}$', phone):
            return jsonify({'success': False, 'message': 'Invalid mobile number format'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Find user by phone
        cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        
        if not check_password_hash(user['password'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        
        # Set session
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_phone'] = user['phone']
        
        # Build user response with all fields
        user_dict = dict(user)
        user_data = {
            'id': user_dict.get('id', ''),
            'name': user_dict.get('name', ''),
            'phone': user_dict.get('phone', ''),
            'location': user_dict.get('location', ''),
            'village': user_dict.get('village', ''),
            'mandal': user_dict.get('mandal', ''),
            'district': user_dict.get('district', ''),
            'userType': user_dict.get('user_type', 'Farmer'),
            'preferredLanguage': user_dict.get('preferred_language', 'English'),
            'created_at': user_dict.get('created_at', '')
        }
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': user_data
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle user logout"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

@app.route('/api/user', methods=['GET'])
def get_user():
    """Get current user information"""
    try:
        # Check if user is logged in
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user_dict = dict(user)
        return jsonify({
            'success': True,
            'user': {
                'id': user_dict.get('id', ''),
                'name': user_dict.get('name', ''),
                'phone': user_dict.get('phone', ''),
                'village': user_dict.get('village', ''),
                'mandal': user_dict.get('mandal', ''),
                'district': user_dict.get('district', ''),
                'location': user_dict.get('location', ''),
                'userType': user_dict.get('user_type', 'Farmer'),
                'preferredLanguage': user_dict.get('preferred_language', 'English'),
                'created_at': user_dict.get('created_at', ''),
                'phone_verified': bool(user_dict.get('phone_verified', 0))
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user', methods=['PUT'])
@api_login_required
def update_user():
    """Update current user information"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        phone = data.get('phone', '').strip()
        location = data.get('location', '').strip()
        
        # Validation
        if not all([name, email, phone, location]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email is already taken by another user
        cursor.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, session['user_id']))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
        # Update user
        cursor.execute('''
            UPDATE users 
            SET name = ?, email = ?, phone = ?, location = ?
            WHERE id = ?
        ''', (name, email, phone, location, session['user_id']))
        
        conn.commit()
        conn.close()
        
        # Update session
        session['user_name'] = name
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'user': {
                'id': session['user_id'],
                'name': name,
                'email': email,
                'phone': phone,
                'location': location
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==========================================
# PROFILE API ROUTES
# ==========================================

@app.route('/api/profile/full', methods=['GET'])
@api_login_required
def get_full_profile():
    """Get complete profile data for current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, email, phone, location, user_type, preferred_language, profile_photo, created_at
            FROM users WHERE id = ?
        ''', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'phone': user['phone'],
                'location': user['location'],
                'user_type': user['user_type'] or 'farmer',
                'preferred_language': user['preferred_language'] or 'en',
                'profile_photo': user['profile_photo'],
                'member_since': user['created_at']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/update', methods=['PUT'])
@api_login_required
def update_full_profile():
    """Update profile with all fields"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        phone = data.get('phone', '').strip()
        location = data.get('location', '').strip()
        user_type = data.get('user_type', 'farmer')
        preferred_language = data.get('preferred_language', 'en')
        
        if not all([name, email, phone, location]):
            return jsonify({'success': False, 'message': 'Name, email, phone and location are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check email uniqueness
        cursor.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, session['user_id']))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
        cursor.execute('''
            UPDATE users 
            SET name = ?, email = ?, phone = ?, location = ?, user_type = ?, preferred_language = ?
            WHERE id = ?
        ''', (name, email, phone, location, user_type, preferred_language, session['user_id']))
        
        conn.commit()
        conn.close()
        
        session['user_name'] = name
        session['user_email'] = email
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/photo', methods=['POST'])
@api_login_required
def upload_profile_photo():
    """Upload profile photo"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f"profile_{session['user_id']}_{timestamp}_{filename}"
            
            # Create uploads directory if needed
            profile_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
            os.makedirs(profile_dir, exist_ok=True)
            
            file_path = os.path.join(profile_dir, new_filename)
            file.save(file_path)
            
            url = f'/static/uploads/profiles/{new_filename}'
            
            # Update database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET profile_photo = ? WHERE id = ?', (url, session['user_id']))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'url': url}), 200
        
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/stats', methods=['GET'])
@api_login_required
def get_profile_stats():
    """Get profile statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        user_id = session['user_id']
        
        # Count products posted
        cursor.execute('SELECT COUNT(*) FROM products WHERE user_id = ?', (user_id,))
        products_count = cursor.fetchone()[0]
        
        # Count rentals posted
        cursor.execute('SELECT COUNT(*) FROM rental_items WHERE user_id = ?', (user_id,))
        rentals_count = cursor.fetchone()[0]
        
        # Count product requirements
        cursor.execute('SELECT COUNT(*) FROM customer_requirements WHERE user_id = ?', (user_id,))
        product_reqs_count = cursor.fetchone()[0]
        
        # Count rental requirements
        cursor.execute('SELECT COUNT(*) FROM rental_requirements WHERE user_id = ?', (user_id,))
        rental_reqs_count = cursor.fetchone()[0]
        
        # Count contacts made (from history)
        cursor.execute("SELECT COUNT(*) FROM user_history WHERE user_id = ? AND action_type = 'contacted'", (user_id,))
        contacts_count = cursor.fetchone()[0]
        
        # Count feedback received
        cursor.execute('SELECT COUNT(*) FROM user_feedback WHERE farmer_id = ?', (user_id,))
        feedback_count = cursor.fetchone()[0]
        
        # Average rating
        cursor.execute('SELECT COALESCE(AVG(rating), 0) FROM user_feedback WHERE farmer_id = ?', (user_id,))
        avg_rating = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'products_posted': products_count,
                'rentals_posted': rentals_count,
                'product_requirements': product_reqs_count,
                'rental_requirements': rental_reqs_count,
                'contacts_made': contacts_count,
                'feedback_received': feedback_count,
                'average_rating': round(avg_rating, 1)
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/my-products', methods=['GET'])
@api_login_required
def get_my_products():
    """Get products posted by current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, category, price, quantity, unit, images, status, created_at
            FROM products WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (session['user_id'],))
        products = cursor.fetchall()
        conn.close()
        
        products_list = []
        for p in products:
            images = json.loads(p['images']) if p['images'] else []
            products_list.append({
                'id': p['id'],
                'name': p['name'],
                'category': p['category'],
                'price': p['price'],
                'quantity': p['quantity'],
                'unit': p['unit'],
                'images': images,
                'status': p['status'] or 'active',
                'created_at': p['created_at']
            })
        
        return jsonify({'success': True, 'products': products_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/my-rentals', methods=['GET'])
@api_login_required
def get_my_rentals():
    """Get rental items posted by current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ri.*, 
                   COALESCE(AVG(rf.rating), 0) as avg_rating,
                   COUNT(rf.id) as review_count
            FROM rental_items ri
            LEFT JOIN rental_feedback rf ON ri.id = rf.rental_id
            WHERE ri.user_id = ?
            GROUP BY ri.id
            ORDER BY ri.created_at DESC
        ''', (session['user_id'],))
        rentals = cursor.fetchall()
        conn.close()
        
        rentals_list = []
        for r in rentals:
            images = json.loads(r['images']) if r['images'] else []
            rentals_list.append({
                'id': r['id'],
                'name': r['name'],
                'category': r['category'],
                'price_per_day': r['price_per_day'],
                'location': r['location'],
                'images': images,
                'status': r['availability_status'] or 'available',
                'avg_rating': round(r['avg_rating'], 1),
                'review_count': r['review_count'],
                'created_at': r['created_at']
            })
        
        return jsonify({'success': True, 'rentals': rentals_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/my-product-requirements', methods=['GET'])
@api_login_required
def get_my_product_requirements():
    """Get product requirements posted by current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, customer_name, product_name, quantity, location, phone_number, status, created_at
            FROM customer_requirements WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (session['user_id'],))
        requirements = cursor.fetchall()
        conn.close()
        
        reqs_list = []
        for r in requirements:
            reqs_list.append({
                'id': r['id'],
                'customer_name': r['customer_name'],
                'product_name': r['product_name'],
                'quantity': r['quantity'],
                'location': r['location'],
                'phone_number': r['phone_number'],
                'status': r['status'] or 'active',
                'created_at': r['created_at']
            })
        
        return jsonify({'success': True, 'requirements': reqs_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/my-rental-requirements', methods=['GET'])
@api_login_required
def get_my_rental_requirements():
    """Get rental requirements posted by current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, farmer_name, phone_number, rental_category, field_area, village, mandal, district, status, created_at
            FROM rental_requirements WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (session['user_id'],))
        requirements = cursor.fetchall()
        conn.close()
        
        reqs_list = []
        for r in requirements:
            reqs_list.append({
                'id': r['id'],
                'farmer_name': r['farmer_name'],
                'phone_number': r['phone_number'],
                'rental_category': r['rental_category'],
                'field_area': r['field_area'],
                'village': r['village'],
                'mandal': r['mandal'],
                'district': r['district'],
                'status': r['status'] or 'active',
                'created_at': r['created_at']
            })
        
        return jsonify({'success': True, 'requirements': reqs_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/feedback', methods=['GET'])
@api_login_required
def get_profile_feedback():
    """Get feedback received by current user (for products they own)"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Please login'}), 401
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT uf.*, p.name as product_name
            FROM user_feedback uf
            LEFT JOIN products p ON uf.product_id = p.id
            WHERE uf.farmer_id = ?
            ORDER BY uf.created_at DESC
        ''', (user_id,))
        feedbacks = cursor.fetchall()
        
        # Calculate average
        cursor.execute('SELECT COALESCE(AVG(rating), 0), COUNT(*) FROM user_feedback WHERE farmer_id = ?', (user_id,))
        avg_result = cursor.fetchone()
        
        conn.close()
        
        feedback_list = []
        for f in feedbacks:
            # Parse images and videos JSON strings
            images = []
            videos = []
            try:
                if f['images']:
                    images = json.loads(f['images']) if isinstance(f['images'], str) else f['images']
                if f['videos']:
                    videos = json.loads(f['videos']) if isinstance(f['videos'], str) else f['videos']
            except:
                pass
            
            feedback_list.append({
                'id': f['id'],
                'reviewer_name': f['reviewer_name'],
                'reviewer_phone': f['reviewer_phone'],
                'rating': f['rating'],
                'comment': f['comment'],
                'product_name': f['product_name'],
                'images': images,
                'videos': videos,
                'created_at': f['created_at']
            })
        
        return jsonify({
            'success': True,
            'feedbacks': feedback_list,
            'average_rating': round(avg_result[0], 1),
            'total_reviews': avg_result[1]
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/my-feedback', methods=['GET'])
@api_login_required
def get_my_feedback():
    """Get feedback submitted by current user (for products they reviewed)"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Please login'}), 401
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT uf.*, p.name as product_name
            FROM user_feedback uf
            LEFT JOIN products p ON uf.product_id = p.id
            WHERE uf.user_id = ?
            ORDER BY uf.created_at DESC
        ''', (user_id,))
        feedbacks = cursor.fetchall()
        
        # Calculate average
        cursor.execute('SELECT COALESCE(AVG(rating), 0), COUNT(*) FROM user_feedback WHERE user_id = ?', (user_id,))
        avg_result = cursor.fetchone()
        
        conn.close()
        
        feedback_list = []
        for f in feedbacks:
            # Parse images and videos JSON strings
            images = []
            videos = []
            try:
                if f['images']:
                    images = json.loads(f['images']) if isinstance(f['images'], str) else f['images']
                if f['videos']:
                    videos = json.loads(f['videos']) if isinstance(f['videos'], str) else f['videos']
            except:
                pass
            
            feedback_list.append({
                'id': f['id'],
                'product_name': f['product_name'],
                'rating': f['rating'],
                'comment': f['comment'],
                'images': images,
                'videos': videos,
                'created_at': f['created_at']
            })
        
        return jsonify({
            'success': True,
            'feedbacks': feedback_list,
            'average_rating': round(avg_result[0], 1),
            'total_reviews': avg_result[1]
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback for a farmer/product"""
    try:
        data = request.get_json()
        
        farmer_name = data.get('farmer_name', '').strip()
        reviewer_name = data.get('reviewer_name', '').strip()
        reviewer_phone = data.get('reviewer_phone', '').strip()
        rating = data.get('rating')
        comment = data.get('comment', '').strip()
        product_id = data.get('product_id')
        
        if not farmer_name or not reviewer_name or not rating:
            return jsonify({'success': False, 'message': 'Farmer name, reviewer name and rating are required'}), 400
        
        rating = int(rating)
        if rating < 1 or rating > 5:
            return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Find farmer by name
        cursor.execute('SELECT id FROM users WHERE name = ?', (farmer_name,))
        farmer = cursor.fetchone()
        farmer_id = farmer['id'] if farmer else None
        
        user_id = session.get('user_id')
        
        cursor.execute('''
            INSERT INTO user_feedback (user_id, farmer_id, product_id, reviewer_name, reviewer_phone, rating, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, farmer_id, product_id, reviewer_name, reviewer_phone, rating, comment))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Feedback submitted successfully'}), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products/<int:product_id>/feedback', methods=['POST'])
def submit_product_feedback(product_id):
    """Submit feedback for a product with optional images and videos"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Please login to submit feedback'}), 401
        
        # Get user name
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user_name = user['name']
        
        # Check if product exists
        cursor.execute('SELECT id, user_id FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        farmer_id = product['user_id']
        
        # Check for duplicate feedback
        cursor.execute('''
            SELECT id FROM user_feedback
            WHERE product_id = ? AND user_id = ?
        ''', (product_id, user_id))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return jsonify({'success': False, 'message': 'You have already submitted feedback for this product'}), 400
        
        # Get form data
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()
        
        # Validate rating
        if not rating:
            conn.close()
            return jsonify({'success': False, 'message': 'Rating is required'}), 400
        
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                conn.close()
                return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        except (ValueError, TypeError):
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid rating value'}), 400
        
        # Handle file uploads
        images = []
        videos = []
        
        # Process image files
        if 'images' in request.files:
            image_files = request.files.getlist('images')
            for img_file in image_files:
                if img_file and img_file.filename:
                    if not allowed_file(img_file.filename):
                        continue
                    if len(img_file.read()) > MAX_IMAGE_SIZE:
                        continue
                    img_file.seek(0)
                    
                    # Save image
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    filename = secure_filename(img_file.filename)
                    ext = filename.rsplit('.', 1)[1].lower()
                    new_filename = f'feedback_product_{product_id}_{user_id}_{timestamp}_{filename}'
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'feedback', new_filename)
                    img_file.save(filepath)
                    images.append(f'feedback/{new_filename}')
        
        # Process video files
        if 'videos' in request.files:
            video_files = request.files.getlist('videos')
            for vid_file in video_files:
                if vid_file and vid_file.filename:
                    ext = vid_file.filename.rsplit('.', 1)[1].lower() if '.' in vid_file.filename else ''
                    if ext not in ALLOWED_VIDEO_EXTENSIONS:
                        continue
                    if len(vid_file.read()) > MAX_VIDEO_SIZE:
                        continue
                    vid_file.seek(0)
                    
                    # Save video
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    filename = secure_filename(vid_file.filename)
                    new_filename = f'feedback_product_{product_id}_{user_id}_{timestamp}_{filename}'
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'feedback', new_filename)
                    vid_file.save(filepath)
                    videos.append(f'feedback/{new_filename}')
        
        # Insert feedback
        images_json = json.dumps(images) if images else None
        videos_json = json.dumps(videos) if videos else None
        
        cursor.execute('''
            INSERT INTO user_feedback (user_id, farmer_id, product_id, reviewer_name, reviewer_phone, rating, comment, images, videos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, farmer_id, product_id, user_name, None, rating, comment or None, images_json, videos_json))
        
        feedback_id = cursor.lastrowid
        conn.commit()
        
        # Get updated average rating
        cursor.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as review_count
            FROM user_feedback
            WHERE product_id = ?
        ''', (product_id,))
        rating_info = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Feedback submitted successfully',
            'feedback_id': feedback_id,
            'avg_rating': round(rating_info['avg_rating'], 1),
            'review_count': rating_info['review_count']
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products/<int:product_id>/feedback', methods=['GET'])
def get_product_feedback(product_id):
    """Get all feedback for a product"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if product exists
        cursor.execute('SELECT id, name FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        if not product:
            conn.close()
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        # Get feedback
        cursor.execute('''
            SELECT uf.*, u.name as user_name_from_db
            FROM user_feedback uf
            LEFT JOIN users u ON uf.user_id = u.id
            WHERE uf.product_id = ?
            ORDER BY uf.created_at DESC
        ''', (product_id,))
        feedbacks = cursor.fetchall()
        
        # Calculate average rating
        cursor.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as review_count
            FROM user_feedback
            WHERE product_id = ?
        ''', (product_id,))
        rating_info = cursor.fetchone()
        
        conn.close()
        
        feedback_list = []
        for fb in feedbacks:
            # Parse images and videos JSON strings
            images = []
            videos = []
            try:
                if fb['images']:
                    images = json.loads(fb['images']) if isinstance(fb['images'], str) else fb['images']
                if fb['videos']:
                    videos = json.loads(fb['videos']) if isinstance(fb['videos'], str) else fb['videos']
            except:
                pass
            
            feedback_list.append({
                'id': fb['id'],
                'user_name': fb['reviewer_name'] or fb['user_name_from_db'] or 'Anonymous',
                'rating': fb['rating'],
                'comment': fb['comment'],
                'images': images,
                'videos': videos,
                'created_at': fb['created_at']
            })
        
        return jsonify({
            'success': True,
            'product_name': product['name'],
            'avg_rating': round(rating_info['avg_rating'], 1),
            'review_count': rating_info['review_count'],
            'feedbacks': feedback_list
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rental-requirements', methods=['POST'])
def post_rental_requirement():
    """Post a new rental requirement"""
    try:
        data = request.get_json()
        
        farmer_name = data.get('farmer_name', '').strip()
        phone_number = data.get('phone_number', '').strip()
        rental_category = data.get('rental_category', '').strip()
        field_area = data.get('field_area', '').strip()
        village = data.get('village', '').strip()
        mandal = data.get('mandal', '').strip()
        district = data.get('district', '').strip()
        
        if not farmer_name or not phone_number or not rental_category:
            return jsonify({'success': False, 'message': 'Farmer name, phone number, and rental category are required'}), 400
        
        user_id = session.get('user_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO rental_requirements (user_id, farmer_name, phone_number, rental_category, field_area, village, mandal, district)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, farmer_name, phone_number, rental_category, field_area, village, mandal, district))
        
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create notification for all users
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users')
        users = cursor.fetchall()
        location_str = f"{village}, {mandal}, {district}" if village and mandal and district else (district or village or '')
        for user in users:
            cursor.execute('''
                INSERT INTO notifications (user_id, category, title, message, related_item_id, related_item_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user['id'], 'rental_requirement_posted', 'New Rental Requirement', 
                  f'{farmer_name} needs {rental_category} rental in {location_str}', req_id, 'rental_requirement'))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Rental requirement posted successfully',
            'requirement_id': req_id
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rental-requirements', methods=['GET'])
def get_rental_requirements():
    """Get all rental requirements"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM rental_requirements 
            WHERE status = 'active'
            ORDER BY created_at DESC
        ''')
        requirements = cursor.fetchall()
        conn.close()
        
        reqs_list = []
        for r in requirements:
            reqs_list.append({
                'id': r['id'],
                'farmer_name': r['farmer_name'],
                'phone_number': r['phone_number'],
                'rental_category': r['rental_category'],
                'field_area': r['field_area'],
                'village': r['village'],
                'mandal': r['mandal'],
                'district': r['district'],
                'status': r['status'],
                'created_at': r['created_at']
            })
        
        return jsonify({'success': True, 'requirements': reqs_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/contact', methods=['POST'])
def contact():
    """Handle contact form submission"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        contact_info = data.get('contact_info', '').strip()
        description = data.get('description', '').strip()
        
        if not all([name, contact_info, description]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO contact_messages (name, contact_info, description)
            VALUES (?, ?, ?)
        ''', (name, contact_info, description))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Message sent successfully'}), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    """Get all products"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.name as farmer_name, u.location as farmer_location
            FROM products p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.created_at DESC
        ''')
        products = cursor.fetchall()
        conn.close()
        
        products_list = []
        for product in products:
            images = json.loads(product['images']) if product['images'] else []
            products_list.append({
                'id': product['id'],
                'user_id': product['user_id'],
                'category': product['category'],
                'name': product['name'],
                'description': product['description'],
                'quantity': product['quantity'],
                'unit': product['unit'],
                'price': product['price'],
                'images': images,
                'farmer_name': product['farmer_name'],
                'farmer_location': product['farmer_location'],
                'created_at': product['created_at']
            })
        
        return jsonify({'success': True, 'products': products_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products', methods=['POST'])
@api_login_required
def create_product():
    """Create a new product"""
    try:
        data = request.get_json()
        
        category = data.get('category', '').strip()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        quantity = float(data.get('quantity', 0))
        unit = data.get('unit', 'kg').strip()
        price = float(data.get('price', 0))
        images = data.get('images', [])
        
        # Validation
        if not all([category, name, description]):
            return jsonify({'success': False, 'message': 'Category, name, and description are required'}), 400
        
        if quantity <= 0 or price <= 0:
            return jsonify({'success': False, 'message': 'Quantity and price must be greater than 0'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (user_id, category, name, description, quantity, unit, price, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], category, name, description, quantity, unit, price, json.dumps(images)))
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create transaction record
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, type, description, amount)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], 'product_created', f'Created product: {name}', 0))
        conn.commit()
        conn.close()
        
        # Create notification for all users (except the creator)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE id != ?', (session['user_id'],))
        users = cursor.fetchall()
        for user in users:
            cursor.execute('''
                INSERT INTO notifications (user_id, category, title, message, related_item_id, related_item_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user['id'], 'product_posted', 'New Product Available', 
                  f'{name} ({category}) has been posted', product_id, 'product'))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Product created successfully'}), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@api_login_required
def delete_product(product_id):
    """Delete a product"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if product belongs to user
        cursor.execute('SELECT user_id FROM products WHERE id = ?', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            conn.close()
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        if product['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Product deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/requirements', methods=['GET'])
def get_requirements():
    """Get all customer requirements"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customer_requirements ORDER BY created_at DESC')
        requirements = cursor.fetchall()
        conn.close()
        
        requirements_list = []
        for req in requirements:
            requirements_list.append({
                'id': req['id'],
                'customer_name': req['customer_name'],
                'product_name': req['product_name'],
                'quantity': req['quantity'],
                'location': req['location'],
                'phone_number': req['phone_number'],
                'pin_code': req['pin_code'] if 'pin_code' in req.keys() else '',
                'special_instructions': req['special_instructions'] if 'special_instructions' in req.keys() else '',
                'preferred_delivery_date': req['preferred_delivery_date'] if 'preferred_delivery_date' in req.keys() else '',
                'created_at': req['created_at']
            })
        
        return jsonify({'success': True, 'requirements': requirements_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/requirements', methods=['POST'])
def create_requirement():
    """Create a new customer requirement"""
    try:
        data = request.get_json()
        
        customer_name = data.get('customer_name', '').strip()
        product_name = data.get('product_name', '').strip()
        quantity = data.get('quantity', '').strip()
        location = data.get('location', '').strip()
        phone_number = data.get('phone_number', '').strip()
        pin_code = data.get('pin_code', '').strip()
        special_instructions = data.get('special_instructions', '').strip()
        preferred_delivery_date = data.get('preferred_delivery_date', '').strip()
        
        # Validation
        if not all([customer_name, product_name, quantity, location, phone_number]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO customer_requirements (customer_name, product_name, quantity, location, phone_number, pin_code, special_instructions, preferred_delivery_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (customer_name, product_name, quantity, location, phone_number, pin_code, special_instructions, preferred_delivery_date))
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create notification for all users
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users')
        users = cursor.fetchall()
        for user in users:
            cursor.execute('''
                INSERT INTO notifications (user_id, category, title, message, related_item_id, related_item_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user['id'], 'product_requirement_posted', 'New Product Requirement', 
                  f'{customer_name} needs {quantity} of {product_name} in {location}', req_id, 'product_requirement'))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Requirement posted successfully'}), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/transactions', methods=['GET'])
@api_login_required
def get_transactions():
    """Get user transactions"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
        ''', (session['user_id'],))
        transactions = cursor.fetchall()
        conn.close()
        
        transactions_list = []
        for trans in transactions:
            transactions_list.append({
                'id': trans['id'],
                'type': trans['type'],
                'description': trans['description'],
                'amount': trans['amount'],
                'created_at': trans['created_at']
            })
        
        return jsonify({'success': True, 'transactions': transactions_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications', methods=['GET'])
@api_login_required
def get_notifications():
    """Get all notifications for the current user"""
    try:
        category = request.args.get('category', None)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if category and category != 'all':
            cursor.execute('''
                SELECT * FROM notifications
                WHERE user_id = ? AND category = ?
                ORDER BY created_at DESC
            ''', (session['user_id'], category))
        else:
            cursor.execute('''
                SELECT * FROM notifications
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (session['user_id'],))
        
        notifications = cursor.fetchall()
        conn.close()
        
        notifications_list = []
        for notif in notifications:
            notifications_list.append({
                'id': notif['id'],
                'category': notif['category'],
                'title': notif['title'],
                'message': notif['message'],
                'related_item_id': notif['related_item_id'],
                'related_item_type': notif['related_item_type'],
                'is_read': bool(notif['is_read']),
                'created_at': notif['created_at']
            })
        
        return jsonify({'success': True, 'notifications': notifications_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/<int:notification_id>/read', methods=['PUT'])
@api_login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify notification belongs to user
        cursor.execute('SELECT user_id FROM notifications WHERE id = ?', (notification_id,))
        notif = cursor.fetchone()
        
        if not notif:
            conn.close()
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
        
        if notif['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        cursor.execute('''
            UPDATE notifications SET is_read = 1 WHERE id = ?
        ''', (notification_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Notification marked as read'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['PUT'])
@api_login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0
        ''', (session['user_id'],))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'All notifications marked as read'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@api_login_required
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify notification belongs to user
        cursor.execute('SELECT user_id FROM notifications WHERE id = ?', (notification_id,))
        notif = cursor.fetchone()
        
        if not notif:
            conn.close()
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
        
        if notif['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        cursor.execute('DELETE FROM notifications WHERE id = ?', (notification_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Notification deleted'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/unread-count', methods=['GET'])
@api_login_required
def get_unread_count():
    """Get count of unread notifications"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM notifications
            WHERE user_id = ? AND is_read = 0
        ''', (session['user_id'],))
        
        result = cursor.fetchone()
        conn.close()
        
        return jsonify({'success': True, 'count': result['count']}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
@api_login_required
def upload_file():
    """Handle file uploads"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
            file.save(filepath)
            
            # Return relative URL
            url = url_for('static', filename=f'uploads/products/{filename}')
            return jsonify({'success': True, 'url': url}), 200
        
        return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Perplexity API configuration
PERPLEXITY_API_KEY = "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"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

@app.route('/api/crop/details', methods=['POST'])
def get_crop_details():
    """Get comprehensive crop details using Perplexity API"""
    try:
        data = request.get_json()
        crop_name = data.get('crop_name', '').strip()
        
        if not crop_name:
            return jsonify({'success': False, 'message': 'Crop name is required'}), 400
        
        # Build comprehensive prompt for crop details
        prompt = f"""Provide comprehensive cultivation information for "{crop_name}" crop for Indian farmers. Structure the information EXACTLY with the following emoji headings and sections:

🧠 Crop Overview
- Brief description, botanical name and family
- Economic importance and main uses
- Major growing regions in India

🧭 Growth Stages & Duration
- Complete lifecycle from seed to harvest
- Time duration for each growth stage
- Key developmental milestones
- Total crop duration

🌱 Soil & Climate Requirements
- Ideal soil type (pH, texture, composition)
- Temperature requirements (min, max, optimal)
- Rainfall/humidity needs
- Sunlight requirements
- Altitude preferences

🧪 Fertilisers & Nutrient Management
- NPK requirements at different stages
- Organic vs chemical fertilizer recommendations
- Application schedule and dosage
- Micronutrient needs
- Soil amendments

🐛 Pest & Disease Management
- Common pests affecting {crop_name}
- Major diseases and their symptoms
- Integrated pest management strategies
- Organic and chemical control methods
- Preventive measures

💧 Irrigation & Water Management
- Water requirements (liters/acre or mm)
- Irrigation schedule and frequency
- Critical watering stages
- Irrigation methods (drip, sprinkler, flood)
- Water conservation tips

🚜 Cultivation Steps
- Land preparation
- Seed selection and treatment
- Sowing/planting method and spacing
- Transplanting (if applicable)
- Intercultural operations
- Weeding schedule

📦 Post-Harvest Handling & Storage
- Harvesting indicators and method
- Post-harvest processing
- Storage conditions and duration
- Packaging requirements
- Quality grading

📈 Market Intelligence
- Current market demand trends
- Average market price range in India (₹/quintal or ₹/kg)
- Peak selling season
- Major mandis/markets
- Export potential
- Value-added products

🌾 Popular Varieties
- List 5-7 popular varieties/cultivars of {crop_name}
- Each variety's special characteristics
- Yield potential
- Disease resistance traits

☀️ Climate & Weather Forecast
- Best planting season (Kharif/Rabi/Zaid)
- Weather-related risks
- Climate change impact
- Adaptation strategies

🔍 AI Suitability & Recommendation Summary
- Overall profitability assessment
- Risk level (Low/Medium/High)
- Suitable for small/medium/large farms
- Key success factors
- Common mistakes to avoid
- Final recommendation for farmers

Format with emoji headings EXACTLY as shown above. Use bullet points (•) for details under each section. Keep language simple and practical for farmers. Include specific numbers and data where possible."""
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Try different models
        models_to_try = ["sonar-small-online", "sonar-pro", "sonar-medium-online", "llama-3.1-sonar-small-128k-online"]
        
        last_error = None
        for model_name in models_to_try:
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert agricultural advisor for Indian farmers. Provide detailed, accurate, and practical farming information."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4000
                }
                
                response = requests.post(PERPLEXITY_API_URL, json=payload, headers=headers, timeout=45)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if 'choices' in result and len(result['choices']) > 0:
                        crop_info = result['choices'][0]['message']['content']
                        return jsonify({
                            'success': True,
                            'details': crop_info
                        }), 200
                    else:
                        continue
                else:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', '')
                        if 'model' in error_msg.lower() or 'invalid' in error_msg.lower():
                            last_error = error_msg
                            continue
                        else:
                            last_error = error_msg
                            break
                    except:
                        last_error = f'HTTP {response.status_code}'
                        continue
                        
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                break
        
        return jsonify({
            'success': False,
            'message': 'Could not load detailed information. Please try again later.'
        }), 500
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """Handle AI chat requests using Perplexity API"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        language = data.get('language', 'en')
        crop_context = data.get('crop_context', '')  # Optional crop context for better responses
        
        if not user_message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        # Language names for prompt
        language_names = {
            "en": "English",
            "te": "Telugu",
            "hi": "Hindi",
            "ta": "Tamil",
            "kn": "Kannada"
        }
        
        # Build the prompt
        language_instruction = ""
        if language != 'en':
            language_instruction = f"Please respond in {language_names.get(language, 'English')} language. "
        
        context_instruction = ""
        if crop_context:
            context_instruction = f"\n\nContext: The user is asking about {crop_context} crop. Provide specific and relevant information related to this crop."
        
        system_prompt = f"""{language_instruction}
You are CTF.ai Agricultural Assistant, an expert farming advisor for Indian farmers. Your role is to provide:

- Practical crop cultivation guidance
- Pest and disease management solutions
- Fertilizer and soil health recommendations
- Market intelligence and pricing trends
- Weather and climate advice
- Best farming practices and techniques
- Seasonal crop suggestions
{context_instruction}

Guidelines:
- Keep responses clear, concise, and actionable (max 250 words)
- Use bullet points when listing multiple items
- Include specific numbers, measurements, or timeframes when relevant
- Be friendly, supportive, and farmer-focused
- If asked about non-agricultural topics, politely redirect to farming
"""
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Try different model names in order of preference
        models_to_try = ["sonar-small-online", "sonar-pro", "sonar-medium-online", "llama-3.1-sonar-small-128k-online"]
        
        # Try different models until one works
        last_error = None
        for model_name in models_to_try:
            try:
                # Prepare the request payload
                payload = {
                    "model": model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
                
                response = requests.post(PERPLEXITY_API_URL, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract the response text
                    if 'choices' in result and len(result['choices']) > 0:
                        ai_response = result['choices'][0]['message']['content']
                    elif 'message' in result:
                        ai_response = result['message']
                    else:
                        continue  # Try next model
                    
                    return jsonify({
                        'success': True,
                        'response': ai_response
                    }), 200
                else:
                    # Check if it's a model error
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', '')
                        if 'model' in error_msg.lower() or 'invalid' in error_msg.lower():
                            last_error = error_msg
                            continue  # Try next model
                        else:
                            last_error = error_msg
                            break  # Different error, don't try other models
                    except:
                        last_error = f'HTTP {response.status_code}'
                        continue
                        
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                break  # Network error, don't try other models
        
        # If we get here, all models failed
        # Provide user-friendly error message
        if last_error and ('model' in last_error.lower() or 'invalid' in last_error.lower()):
            error_message = 'AI service configuration issue. Please contact support.'
        elif last_error and ('timeout' in last_error.lower()):
            error_message = 'Request timed out. Please try again.'
        elif last_error and ('network' in last_error.lower() or 'connection' in last_error.lower()):
            error_message = 'Network error. Please check your internet connection and try again.'
        else:
            error_message = 'AI service is temporarily unavailable. Please try again in a moment.'
        
        return jsonify({'success': False, 'message': error_message}), 500
        
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout. Please try again.'}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'message': f'Network error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def clean_web_content(content):
    """Clean web content for better extraction"""
    # Remove excessive whitespace
    content = re.sub(r'\s+', ' ', content)
    # Remove common noise patterns
    content = re.sub(r'(Cookie|Privacy|Terms|Menu|Navigation|Skip to content)', '', content, flags=re.IGNORECASE)
    return content.strip()

def detect_source_portal(url):
    """Detect the source portal from URL"""
    if not url:
        return "Unknown"
    
    url_lower = url.lower()
    portals = {
        "india.gov.in": "India Gov Schemes Portal",
        "agricoop.gov.in": "Ministry of Agriculture & Farmers Welfare",
        "pmkisan.gov.in": "PM Kisan Samman Nidhi Portal",
        "pmfby.gov.in": "PM Fasal Bima Yojana",
        "mygov.in": "MyGov Scheme Portal",
        "nabard.org": "NABARD",
        "enam.gov.in": "e-NAM",
        "pmksy.gov.in": "Pradhan Mantri Krishi Sinchai Yojana",
        "rythubandhu.telangana.gov.in": "Telangana Rythu Bandhu",
        "agri.telangana.gov.in": "Telangana Agriculture Department",
        "ysrrythubharosa.ap.gov.in": "Andhra Pradesh YSR Rythu Bharosa",
        "apagrisnet.gov.in": "Andhra Pradesh Agriculture",
        "tn.gov.in": "Tamil Nadu Government",
        "tnesevai.tn.gov.in": "Tamil Nadu e-Services",
        "raitamitra.karnataka.gov.in": "Karnataka Raitha Mitra",
        "mahadbt.maharashtra.gov.in": "Maharashtra DBT",
        "krishijagran.com": "Krishi Jagran",
        "agrifarming.in": "Agri Farming",
        "sarkariyojana.com": "Sarkari Yojana"
    }
    
    for key, name in portals.items():
        if key in url_lower:
            return name
    return "Government Portal"

@app.route('/api/schemes/extract', methods=['POST'])
def extract_schemes():
    """Extract government schemes from web content using AI"""
    try:
        data = request.get_json()
        web_content = data.get('content', '').strip()
        url = data.get('url', '').strip()
        
        if not web_content and not url:
            return jsonify({'success': False, 'message': 'Content or URL is required'}), 400
        
        source_portal = detect_source_portal(url)
        
        # If URL is provided, try to fetch content
        if url and not web_content:
            try:
                response = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5'
                })
                if response.status_code == 200:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        # Remove script, style, and other non-content elements
                        for element in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
                            element.decompose()
                        # Get text content
                        web_content = soup.get_text(separator=' ', strip=True)
                        web_content = clean_web_content(web_content)
                    except ImportError:
                        # If BeautifulSoup is not available, use raw text
                        web_content = clean_web_content(response.text)
            except Exception as e:
                return jsonify({'success': False, 'message': f'Failed to fetch URL: {str(e)}'}), 400
        
        if not web_content:
            return jsonify({'success': False, 'message': 'Could not extract content from URL'}), 400
        
        # Clean the content
        web_content = clean_web_content(web_content)
        
        # Limit content size but keep more for better extraction
        content_preview = web_content[:12000] if len(web_content) > 12000 else web_content
        
        # Build the enhanced extraction prompt
        extraction_prompt = f"""You are an AI system designed to automatically extract Government Schemes and Subsidies information from web pages, news articles, and official portals.

Source Portal: {source_portal}
URL: {url if url else 'Content provided directly'}

Your task is to read the given webpage content and accurately identify ALL government schemes mentioned.

Extract ONLY Government Schemes related to:
- Agriculture and farming
- Farmers welfare and support
- Subsidies (fertilizer, seeds, machinery, irrigation)
- Financial support and direct benefit transfers
- Crop insurance and PM Fasal Bima Yojana
- Irrigation schemes (drip, sprinkler, water management)
- Farm loans and credit schemes
- Machinery and equipment subsidies
- Soil health and organic farming
- Market reforms and e-NAM
- State-specific farmer welfare programs

For each scheme found, extract the following fields in clean JSON format:

{{
  "scheme_name": "",
  "start_date": "",
  "end_date": "",
  "description": "",
  "benefits": "",
  "eligibility": "",
  "required_documents": "",
  "apply_link": "",
  "official_website": "",
  "state": "",
  "category": "",
  "last_updated": ""
}}

### CRITICAL EXTRACTION RULES:
1. Extract scheme_name: Look for official scheme names like "PM Kisan", "Rythu Bandhu", "Fasal Bima Yojana", etc.
2. Extract dates: Look for application dates, enrollment periods, scheme launch dates. Format as YYYY-MM-DD.
3. Extract description: Full scheme overview, objectives, and purpose.
4. Extract benefits: Financial amounts (₹), percentage subsidies, coverage details.
5. Extract eligibility: Who can apply (farmers, land owners, specific states, income criteria).
6. Extract required_documents: Aadhaar, land records, bank details, etc.
7. Extract apply_link: Direct application URLs if mentioned.
8. Extract official_website: Main portal URL for the scheme.
9. Extract state: "All India" for central schemes, specific state name for state schemes.
10. Extract category: Agriculture, Insurance, Subsidy, Loan, Irrigation, etc.
11. Extract last_updated: When the information was last updated.

### IMPORTANT:
- If any field is not available in the content, return an empty string "" - DO NOT invent or add fake details.
- Dates must be in format: YYYY-MM-DD. If only year is available, use YYYY-01-01.
- DO NOT include navigation menus, ads, footer text, or unrelated content.
- Extract only official government scheme information.
- Combine multi-line text into single clean paragraphs.
- If multiple schemes exist, return an array of JSON objects: [{{...}}, {{...}}]
- If only one scheme exists, still return as array: [{{...}}]
- DO NOT add emojis, markdown, or extra formatting.
- Output MUST be valid JSON only - no explanations, no text before/after JSON.

### State Detection:
- Central schemes: "All India"
- Telangana schemes: "Telangana"
- Andhra Pradesh schemes: "Andhra Pradesh"
- Tamil Nadu schemes: "Tamil Nadu"
- Karnataka schemes: "Karnataka"
- Maharashtra schemes: "Maharashtra"
- Other states: Extract state name from content

### Date Intelligence:
- If scheme is ongoing/live with no end date: set "end_date": ""
- If scheme has enrollment period: extract both start_date and end_date
- If only year mentioned: use YYYY-01-01 format
- Current date context: {datetime.now().strftime('%Y-%m-%d')}

Now extract ALL Government Schemes from this content:

{content_preview}

Return ONLY valid JSON array format, no other text."""

        # Override prompt with stricter user-specified instructions (JSON-only)
        extraction_prompt = f"""You are an AI system designed to automatically extract Government Schemes and Subsidies related to agriculture and farmers from any webpage content.

Primary data sources include (but are not limited to):
- https://www.india.gov.in
- https://agricoop.gov.in
- https://pmkisan.gov.in
- https://pmfby.gov.in
- https://www.mygov.in/schemes/

Source Portal: {source_portal}
URL: {url if url else 'Content provided directly'}

Your task:
1. Read the webpage text provided below.
2. Identify ONLY the government schemes related to: Agriculture, Farmers, Subsidies, Irrigation, Machinery subsidies, Loans/Credit, Crop insurance, Seeds/Fertilizers, Rural development, Financial/welfare support, farmer-centric government programs.
3. Extract each scheme in this exact JSON structure:
[
  {{
    "scheme_name": "",
    "start_date": "",
    "end_date": "",
    "description": "",
    "benefits": "",
    "eligibility": "",
    "required_documents": "",
    "apply_link": "",
    "official_website": "",
    "state": "",
    "category": "",
    "last_updated": ""
  }}
]

RULES
- Return ONLY valid JSON. No text, no explanation.
- Do NOT add, guess, or invent missing information.
- Leave missing fields as empty strings.
- Combine multiline content into clean single-paragraph text.
- Dates must follow YYYY-MM-DD. If only year is known, use YYYY-01-01.
- If a scheme has no end date → set "end_date": "".
- If state is not mentioned → set "state": "All India".
- If multiple schemes exist → return an array; if none exist → return [].
- Ignore ads, navigation menus, unrelated articles, or political content.
- Extract only legitimate Government schemes and official application links.
- Detect expired schemes based on dates if present.
- Output MUST be valid JSON array only.

State hints:
- Central schemes: "All India"
- Telangana: "Telangana"
- Andhra Pradesh: "Andhra Pradesh"
- Tamil Nadu: "Tamil Nadu"
- Karnataka: "Karnataka"
- Maharashtra: "Maharashtra"

Date intelligence:
- Ongoing/live with no end date: end_date = ""
- Enrollment period: capture both start_date and end_date
- Current date context: {datetime.now().strftime('%Y-%m-%d')}

Now extract ALL Government Schemes from this content:

{content_preview}

Return ONLY the JSON array, nothing else."""
        
        def try_extract_with_perplexity():
            nonlocal last_error
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Try different models
            models_to_try = ["sonar-small-online", "sonar-pro", "sonar-medium-online", "llama-3.1-sonar-small-128k-online"]
            
            for model_name in models_to_try:
                try:
                    payload = {
                        "model": model_name,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert at extracting structured information from web content. Always return valid JSON only, no additional text."
                            },
                            {
                                "role": "user",
                                "content": extraction_prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4000
                    }
                    
                    response = requests.post(PERPLEXITY_API_URL, json=payload, headers=headers, timeout=45)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        if 'choices' in result and len(result['choices']) > 0:
                            return result['choices'][0]['message']['content']
                        else:
                            continue
                    else:
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('error', {}).get('message', '')
                            if 'model' in error_msg.lower() or 'invalid' in error_msg.lower():
                                last_error = error_msg
                                continue
                            else:
                                last_error = error_msg
                                break
                        except:
                            last_error = f'HTTP {response.status_code}'
                            continue
                            
                except requests.exceptions.RequestException as e:
                    last_error = str(e)
                    break
            return None

        def try_extract_with_openai():
            nonlocal last_error
            if not OPENAI_API_KEY:
                return None
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at extracting structured information from web content. Always return valid JSON only, no additional text."
                    },
                    {
                        "role": "user",
                        "content": extraction_prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 3000
            }
            try:
                response = requests.post(OPENAI_API_URL, json=payload, headers=headers, timeout=45)
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        return result['choices'][0]['message']['content']
                else:
                    try:
                        err = response.json()
                        last_error = err.get('error', {}).get('message', f'HTTP {response.status_code}')
                    except:
                        last_error = f'HTTP {response.status_code}'
            except requests.exceptions.RequestException as e:
                last_error = str(e)
            return None

        def parse_json_response(extracted_text):
            nonlocal last_error
            if not extracted_text:
                return None
            extracted_text = extracted_text.strip()
            schemes_json = None
            # Strategy 1: Try to find JSON array or object using regex
            json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', extracted_text, re.DOTALL)
            if json_match:
                try:
                    schemes_json = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            # Strategy 2: Try parsing the entire text if it's JSON
            if schemes_json is None:
                try:
                    schemes_json = json.loads(extracted_text)
                except json.JSONDecodeError:
                    pass
            # Strategy 3: Try to find JSON between code blocks
            if schemes_json is None:
                code_block_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```', extracted_text, re.DOTALL)
                if code_block_match:
                    try:
                        schemes_json = json.loads(code_block_match.group(1))
                    except json.JSONDecodeError:
                        pass
            # Strategy 4: Try to extract JSON from markdown code blocks without language tag
            if schemes_json is None:
                code_match = re.search(r'```\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```', extracted_text, re.DOTALL)
                if code_match:
                    try:
                        schemes_json = json.loads(code_match.group(1))
                    except json.JSONDecodeError:
                        pass
            return schemes_json

        def clean_and_respond(schemes_json):
            nonlocal last_error
            if schemes_json is not None:
                if isinstance(schemes_json, dict):
                    schemes_json = [schemes_json]
                cleaned_schemes = []
                for scheme in schemes_json:
                    if isinstance(scheme, dict):
                        # Ensure scheme_name exists (required field)
                        scheme_name = scheme.get('scheme_name', '').strip()
                        if not scheme_name:
                            continue  # Skip schemes without name
                        
                        # Ensure ALL fields are present with proper defaults per user's JSON structure
                        cleaned_scheme = {
                            'scheme_name': scheme_name,
                            'start_date': scheme.get('start_date', '').strip() or '',
                            'end_date': scheme.get('end_date', '').strip() or '',
                            'description': scheme.get('description', '').strip() or '',
                            'benefits': scheme.get('benefits', '').strip() or '',
                            'eligibility': scheme.get('eligibility', '').strip() or '',
                            'required_documents': scheme.get('required_documents', '').strip() or '',
                            'apply_link': scheme.get('apply_link', '').strip() or '',
                            'official_website': scheme.get('official_website', url if url else '').strip() or '',
                            'state': scheme.get('state', 'All India').strip() or 'All India',
                            'category': scheme.get('category', '').strip() or '',
                            'last_updated': scheme.get('last_updated', '').strip() or ''
                        }
                        cleaned_schemes.append(cleaned_scheme)
                if cleaned_schemes:
                    return jsonify({
                        'success': True,
                        'schemes': cleaned_schemes,
                        'source': source_portal,
                        'url': url
                    }), 200
                else:
                    if last_error is None:
                        last_error = 'No valid schemes found in extracted data'
            else:
                if last_error is None:
                    last_error = 'Could not parse JSON from AI response'
            return None

        # Try Perplexity first
        last_error = None
        extracted = try_extract_with_perplexity()
        if extracted:
            parsed = parse_json_response(extracted)
            resp = clean_and_respond(parsed)
            if resp:
                return resp

        # Fallback to OpenAI if available
        extracted = try_extract_with_openai()
        if extracted:
            parsed = parse_json_response(extracted)
            resp = clean_and_respond(parsed)
            if resp:
                return resp
        
        # Provide helpful error message
        error_message = 'Could not extract schemes from the provided content.'
        if last_error:
            if 'timeout' in last_error.lower():
                error_message = 'Request timed out. The website may be slow. Please try again.'
            elif 'json' in last_error.lower() or 'parse' in last_error.lower():
                error_message = 'Could not parse scheme data. Please try with a different URL or ensure the content contains scheme information.'
            elif 'no valid schemes' in last_error.lower():
                error_message = 'No government schemes found in the provided content. Please try a different URL or page.'
            else:
                error_message = f'Extraction failed: {last_error}'
        
        # Per rules: if no schemes are found, return an empty array (still valid JSON)
        return jsonify({
            'success': True,
            'schemes': [],
            'source': source_portal,
            'url': url,
            'message': error_message
        }), 200
        
    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Invalid JSON response from AI service'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schemes', methods=['GET'])
def get_schemes():
    """Get all saved government schemes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM government_schemes ORDER BY created_at DESC')
        schemes = cursor.fetchall()
        conn.close()
        
        schemes_list = []
        for scheme in schemes:
            schemes_list.append({
                'id': scheme['id'],
                'scheme_name': scheme['scheme_name'],
                'start_date': scheme['start_date'],
                'end_date': scheme['end_date'],
                'description': scheme['description'],
                'benefits': scheme['benefits'],
                'eligibility': scheme['eligibility'],
                'required_documents': scheme['required_documents'],
                'apply_link': scheme['apply_link'],
                'official_website': scheme['official_website'],
                'state': scheme['state'],
                'category': scheme['category'],
                'last_updated': scheme['last_updated'],
                'created_at': scheme['created_at']
            })
        
        return jsonify({'success': True, 'schemes': schemes_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schemes', methods=['POST'])
def save_scheme():
    """Save a government scheme"""
    try:
        data = request.get_json()
        
        scheme_name = data.get('scheme_name', '').strip()
        if not scheme_name:
            return jsonify({'success': False, 'message': 'Scheme name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO government_schemes (
                scheme_name, start_date, end_date, description, benefits,
                eligibility, required_documents, apply_link, official_website,
                state, category, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            scheme_name,
            data.get('start_date', ''),
            data.get('end_date', ''),
            data.get('description', ''),
            data.get('benefits', ''),
            data.get('eligibility', ''),
            data.get('required_documents', ''),
            data.get('apply_link', ''),
            data.get('official_website', ''),
            data.get('state', 'All India'),
            data.get('category', ''),
            data.get('last_updated', '')
        ))
        conn.commit()
        scheme_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Scheme saved successfully',
            'scheme_id': scheme_id
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/schemes/<int:scheme_id>', methods=['DELETE'])
def delete_scheme(scheme_id):
    """Delete a government scheme"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM government_schemes WHERE id = ?', (scheme_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Scheme deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==========================================
# RENTAL ITEMS API ROUTES
# ==========================================

@app.route('/api/rentals', methods=['GET'])
def get_rentals():
    """Get all rental items with average ratings"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.name as owner_name, u.phone as owner_phone, u.location as owner_location,
                   COALESCE(AVG(rf.rating), 0) as avg_rating,
                   COUNT(rf.id) as review_count
            FROM rental_items r
            JOIN users u ON r.user_id = u.id
            LEFT JOIN rental_feedback rf ON r.id = rf.rental_id
            GROUP BY r.id
            ORDER BY r.created_at DESC
        ''')
        rentals = cursor.fetchall()
        conn.close()
        
        rentals_list = []
        for rental in rentals:
            images = json.loads(rental['images']) if rental['images'] else []
            rentals_list.append({
                'id': rental['id'],
                'user_id': rental['user_id'],
                'name': rental['name'],
                'category': rental['category'],
                'description': rental['description'],
                'price_per_hour': rental['price_per_hour'],
                'price_per_day': rental['price_per_day'],
                'location': rental['location'],
                'availability_status': rental['availability_status'],
                'images': images,
                'owner_name': rental['owner_name'],
                'owner_phone': rental['owner_phone'],
                'owner_location': rental['owner_location'],
                'avg_rating': round(rental['avg_rating'], 1),
                'review_count': rental['review_count'],
                'created_at': rental['created_at']
            })
        
        return jsonify({'success': True, 'rentals': rentals_list}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals', methods=['POST'])
@api_login_required
def create_rental():
    """Create a new rental item"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        category = data.get('category', '').strip()
        description = data.get('description', '').strip()
        price_per_hour = data.get('price_per_hour')
        price_per_day = float(data.get('price_per_day', 0))
        location = data.get('location', '').strip()
        images = data.get('images', [])
        
        # Validation
        if not all([name, category, price_per_day, location]):
            return jsonify({'success': False, 'message': 'Name, category, price per day, and location are required'}), 400
        
        if price_per_day <= 0:
            return jsonify({'success': False, 'message': 'Price must be greater than 0'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rental_items (user_id, name, category, description, price_per_hour, price_per_day, location, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], name, category, description, price_per_hour, price_per_day, location, json.dumps(images)))
        
        rental_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create notification for all users (except the creator)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE id != ?', (session['user_id'],))
        users = cursor.fetchall()
        for user in users:
            cursor.execute('''
                INSERT INTO notifications (user_id, category, title, message, related_item_id, related_item_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user['id'], 'rental_posted', 'New Rental Item Available', 
                  f'{name} ({category}) is now available for rent', rental_id, 'rental'))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Rental item created successfully',
            'rental_id': rental_id
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>', methods=['GET'])
def get_rental_detail(rental_id):
    """Get a single rental item with its feedback"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get rental item
        cursor.execute('''
            SELECT r.*, u.name as owner_name, u.phone as owner_phone, u.location as owner_location
            FROM rental_items r
            JOIN users u ON r.user_id = u.id
            WHERE r.id = ?
        ''', (rental_id,))
        rental = cursor.fetchone()
        
        if not rental:
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        # Get feedback for this rental
        cursor.execute('''
            SELECT rf.*, u.name as user_name
            FROM rental_feedback rf
            LEFT JOIN users u ON rf.user_id = u.id
            WHERE rf.rental_id = ?
            ORDER BY rf.created_at DESC
        ''', (rental_id,))
        feedbacks = cursor.fetchall()
        
        # Calculate average rating
        cursor.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as review_count
            FROM rental_feedback
            WHERE rental_id = ?
        ''', (rental_id,))
        rating_info = cursor.fetchone()
        
        conn.close()
        
        images = json.loads(rental['images']) if rental['images'] else []
        
        feedback_list = []
        for fb in feedbacks:
            feedback_list.append({
                'id': fb['id'],
                'reviewer_name': fb['reviewer_name'] or fb['user_name'] or 'Anonymous',
                'rating': fb['rating'],
                'comment': fb['comment'],
                'created_at': fb['created_at']
            })
        
        return jsonify({
            'success': True,
            'rental': {
                'id': rental['id'],
                'name': rental['name'],
                'category': rental['category'],
                'description': rental['description'],
                'price_per_hour': rental['price_per_hour'],
                'price_per_day': rental['price_per_day'],
                'location': rental['location'],
                'availability_status': rental['availability_status'],
                'images': images,
                'owner_name': rental['owner_name'],
                'owner_phone': rental['owner_phone'],
                'owner_location': rental['owner_location'],
                'avg_rating': round(rating_info['avg_rating'], 1),
                'review_count': rating_info['review_count'],
                'feedbacks': feedback_list,
                'created_at': rental['created_at']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>', methods=['DELETE'])
@api_login_required
def delete_rental(rental_id):
    """Delete a rental item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if rental belongs to user
        cursor.execute('SELECT user_id FROM rental_items WHERE id = ?', (rental_id,))
        rental = cursor.fetchone()
        
        if not rental:
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        if rental['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Delete associated feedback first
        cursor.execute('DELETE FROM rental_feedback WHERE rental_id = ?', (rental_id,))
        # Delete rental item
        cursor.execute('DELETE FROM rental_items WHERE id = ?', (rental_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Rental item deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==========================================
# RENTAL FEEDBACK API ROUTES
# ==========================================

@app.route('/api/rentals/<int:rental_id>/feedback', methods=['GET'])
def get_rental_feedback(rental_id):
    """Get all feedback for a rental item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if rental exists
        cursor.execute('SELECT id FROM rental_items WHERE id = ?', (rental_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        # Get feedback
        cursor.execute('''
            SELECT rf.*, u.name as user_name
            FROM rental_feedback rf
            LEFT JOIN users u ON rf.user_id = u.id
            WHERE rf.rental_id = ?
            ORDER BY rf.created_at DESC
        ''', (rental_id,))
        feedbacks = cursor.fetchall()
        
        # Calculate average rating
        cursor.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as review_count
            FROM rental_feedback
            WHERE rental_id = ?
        ''', (rental_id,))
        rating_info = cursor.fetchone()
        
        conn.close()
        
        feedback_list = []
        for fb in feedbacks:
            feedback_list.append({
                'id': fb['id'],
                'reviewer_name': fb['reviewer_name'] or fb['user_name'] or 'Anonymous',
                'rating': fb['rating'],
                'comment': fb['comment'],
                'created_at': fb['created_at']
            })
        
        return jsonify({
            'success': True,
            'avg_rating': round(rating_info['avg_rating'], 1),
            'review_count': rating_info['review_count'],
            'feedbacks': feedback_list
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>/feedback', methods=['POST'])
def submit_rental_feedback(rental_id):
    """Submit feedback for a rental item"""
    try:
        data = request.get_json()
        
        rating = data.get('rating')
        comment = data.get('comment', '').strip()
        reviewer_name = data.get('reviewer_name', '').strip()
        
        # Validation
        if not rating:
            return jsonify({'success': False, 'message': 'Rating is required'}), 400
        
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid rating value'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if rental exists
        cursor.execute('SELECT id FROM rental_items WHERE id = ?', (rental_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        # Get user_id if logged in
        user_id = session.get('user_id')
        
        # If user is logged in and no reviewer_name provided, use their name
        if user_id and not reviewer_name:
            cursor.execute('SELECT name FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if user:
                reviewer_name = user['name']
        
        # Insert feedback
        cursor.execute('''
            INSERT INTO rental_feedback (rental_id, user_id, reviewer_name, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (rental_id, user_id, reviewer_name or 'Anonymous', rating, comment))
        
        feedback_id = cursor.lastrowid
        conn.commit()
        
        # Get updated average rating
        cursor.execute('''
            SELECT COALESCE(AVG(rating), 0) as avg_rating, COUNT(*) as review_count
            FROM rental_feedback
            WHERE rental_id = ?
        ''', (rental_id,))
        rating_info = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Feedback submitted successfully',
            'feedback_id': feedback_id,
            'avg_rating': round(rating_info['avg_rating'], 1),
            'review_count': rating_info['review_count']
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>/feedback/<int:feedback_id>', methods=['DELETE'])
@api_login_required
def delete_rental_feedback(rental_id, feedback_id):
    """Delete a feedback entry (only by the owner or admin)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if feedback exists and belongs to user
        cursor.execute('''
            SELECT rf.user_id, r.user_id as owner_id
            FROM rental_feedback rf
            JOIN rental_items r ON rf.rental_id = r.id
            WHERE rf.id = ? AND rf.rental_id = ?
        ''', (feedback_id, rental_id))
        feedback = cursor.fetchone()
        
        if not feedback:
            conn.close()
            return jsonify({'success': False, 'message': 'Feedback not found'}), 404
        
        # Allow deletion if user is the feedback author or the rental owner
        if feedback['user_id'] != session['user_id'] and feedback['owner_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        cursor.execute('DELETE FROM rental_feedback WHERE id = ?', (feedback_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Feedback deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==========================================
# RENTAL MEDIA API ROUTES (Photos & Videos)
# ==========================================

@app.route('/api/rentals/<int:rental_id>/media', methods=['GET'])
def get_rental_media(rental_id):
    """Get all media (photos and videos) for a rental item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if rental exists
        cursor.execute('SELECT id FROM rental_items WHERE id = ?', (rental_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        # Get all media for this rental
        cursor.execute('''
            SELECT id, rental_id, media_type, media_path, filename, file_size, uploaded_at
            FROM rental_media
            WHERE rental_id = ?
            ORDER BY uploaded_at DESC
        ''', (rental_id,))
        media_items = cursor.fetchall()
        conn.close()
        
        media_list = []
        for media in media_items:
            media_list.append({
                'id': media['id'],
                'rental_id': media['rental_id'],
                'media_type': media['media_type'],
                'media_path': media['media_path'],
                'filename': media['filename'],
                'file_size': media['file_size'],
                'uploaded_at': media['uploaded_at']
            })
        
        # Separate images and videos
        images = [m for m in media_list if m['media_type'] == 'image']
        videos = [m for m in media_list if m['media_type'] == 'video']
        
        return jsonify({
            'success': True,
            'media': media_list,
            'images': images,
            'videos': videos,
            'total_count': len(media_list),
            'image_count': len(images),
            'video_count': len(videos)
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>/media', methods=['POST'])
@api_login_required
def upload_rental_media(rental_id):
    """Upload media (photos/videos) for a rental item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if rental exists and belongs to user
        cursor.execute('SELECT user_id FROM rental_items WHERE id = ?', (rental_id,))
        rental = cursor.fetchone()
        
        if not rental:
            conn.close()
            return jsonify({'success': False, 'message': 'Rental item not found'}), 404
        
        if rental['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized - only owner can upload media'}), 403
        
        if 'media' not in request.files:
            conn.close()
            return jsonify({'success': False, 'message': 'No media file provided'}), 400
        
        files = request.files.getlist('media')
        if not files or all(f.filename == '' for f in files):
            conn.close()
            return jsonify({'success': False, 'message': 'No files selected'}), 400
        
        uploaded_media = []
        errors = []
        
        for file in files:
            if file and file.filename:
                if not allowed_media_file(file.filename):
                    errors.append(f'{file.filename}: Invalid file type. Allowed: JPG, PNG, WEBP, MP4, WEBM')
                    continue
                
                # Check file size
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset to beginning
                
                media_type = get_media_type(file.filename)
                max_size = MAX_VIDEO_SIZE if media_type == 'video' else MAX_IMAGE_SIZE
                
                if file_size > max_size:
                    max_mb = max_size // (1024 * 1024)
                    errors.append(f'{file.filename}: File too large. Max {max_mb}MB for {media_type}s')
                    continue
                
                # Generate unique filename
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"rental_{rental_id}_{timestamp}_{original_filename}"
                
                # Save file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'rentals', filename)
                file.save(file_path)
                
                # Store relative path for database
                relative_path = f"/static/uploads/rentals/{filename}"
                
                # Insert into database
                cursor.execute('''
                    INSERT INTO rental_media (rental_id, media_type, media_path, filename, file_size)
                    VALUES (?, ?, ?, ?, ?)
                ''', (rental_id, media_type, relative_path, original_filename, file_size))
                
                media_id = cursor.lastrowid
                uploaded_media.append({
                    'id': media_id,
                    'rental_id': rental_id,
                    'media_type': media_type,
                    'media_path': relative_path,
                    'filename': original_filename,
                    'file_size': file_size
                })
        
        conn.commit()
        conn.close()
        
        if not uploaded_media and errors:
            return jsonify({
                'success': False,
                'message': 'No files were uploaded',
                'errors': errors
            }), 400
        
        return jsonify({
            'success': True,
            'message': f'{len(uploaded_media)} file(s) uploaded successfully',
            'uploaded': uploaded_media,
            'errors': errors if errors else None
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/rentals/<int:rental_id>/media/<int:media_id>', methods=['DELETE'])
@api_login_required
def delete_rental_media(rental_id, media_id):
    """Delete a media file from a rental item"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if media exists and get rental owner
        cursor.execute('''
            SELECT rm.media_path, r.user_id as owner_id
            FROM rental_media rm
            JOIN rental_items r ON rm.rental_id = r.id
            WHERE rm.id = ? AND rm.rental_id = ?
        ''', (media_id, rental_id))
        media = cursor.fetchone()
        
        if not media:
            conn.close()
            return jsonify({'success': False, 'message': 'Media not found'}), 404
        
        # Only owner can delete media
        if media['owner_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Delete file from filesystem - extract filename from media_path
        # media_path format: /static/uploads/rentals/filename.ext
        media_filename = os.path.basename(media['media_path'])
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'rentals', media_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        cursor.execute('DELETE FROM rental_media WHERE id = ?', (media_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Media deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# User History API Routes
# ============================================

@app.route('/api/history', methods=['GET'])
@api_login_required
def get_user_history():
    """Get user activity history with optional filters"""
    try:
        # Get filter parameters
        action_type = request.args.get('action_type', '')
        item_type = request.args.get('item_type', '')
        search_query = request.args.get('search', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query with filters
        query = '''
            SELECT * FROM user_history
            WHERE user_id = ?
        '''
        params = [session['user_id']]
        
        if action_type:
            query += ' AND action_type = ?'
            params.append(action_type)
        
        if item_type:
            query += ' AND item_type = ?'
            params.append(item_type)
        
        if search_query:
            query += ' AND (item_name LIKE ? OR owner_name LIKE ? OR location LIKE ?)'
            search_pattern = f'%{search_query}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if start_date:
            query += ' AND DATE(created_at) >= DATE(?)'
            params.append(start_date)
        
        if end_date:
            query += ' AND DATE(created_at) <= DATE(?)'
            params.append(end_date)
        
        # Get total count for pagination
        count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # Add ordering and pagination
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        history_items = cursor.fetchall()
        conn.close()
        
        history_list = []
        for item in history_items:
            extra_data = None
            if item['extra_data']:
                try:
                    extra_data = json.loads(item['extra_data'])
                except (json.JSONDecodeError, TypeError):
                    extra_data = None
            
            history_list.append({
                'id': item['id'],
                'action_type': item['action_type'],
                'item_type': item['item_type'],
                'item_id': item['item_id'],
                'item_name': item['item_name'],
                'owner_name': item['owner_name'],
                'location': item['location'],
                'action_status': item['action_status'],
                'extra_data': extra_data,
                'created_at': item['created_at']
            })
        
        return jsonify({
            'success': True,
            'history': history_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'total_pages': (total_count + per_page - 1) // per_page
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/history', methods=['POST'])
@api_login_required
def add_history_entry():
    """Add a new history entry"""
    try:
        data = request.get_json()
        
        action_type = data.get('action_type', '').strip()
        item_type = data.get('item_type', '').strip()
        item_id = data.get('item_id')
        item_name = data.get('item_name', '').strip()
        owner_name = data.get('owner_name', '').strip()
        location = data.get('location', '').strip()
        action_status = data.get('action_status', 'completed').strip()
        extra_data = data.get('extra_data')
        
        # Validation
        if not action_type or not item_type or not item_name:
            return jsonify({
                'success': False,
                'message': 'action_type, item_type, and item_name are required'
            }), 400
        
        # Validate action_type
        valid_actions = ['contacted', 'liked', 'feedback', 'viewed', 'created', 'saved', 'rented', 'responded']
        if action_type.lower() not in valid_actions:
            return jsonify({
                'success': False,
                'message': f'Invalid action_type. Must be one of: {", ".join(valid_actions)}'
            }), 400
        
        # Validate item_type
        valid_items = ['product', 'rental', 'requirement', 'scheme']
        if item_type.lower() not in valid_items:
            return jsonify({
                'success': False,
                'message': f'Invalid item_type. Must be one of: {", ".join(valid_items)}'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Convert extra_data to JSON string if provided
        extra_data_str = json.dumps(extra_data) if extra_data else None
        
        cursor.execute('''
            INSERT INTO user_history (user_id, action_type, item_type, item_id, item_name, owner_name, location, action_status, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session['user_id'],
            action_type.lower(),
            item_type.lower(),
            item_id,
            item_name,
            owner_name,
            location,
            action_status,
            extra_data_str
        ))
        
        history_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'History entry added successfully',
            'history_id': history_id
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/history/<int:history_id>', methods=['DELETE'])
@api_login_required
def delete_history_entry(history_id):
    """Delete a history entry"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if entry belongs to user
        cursor.execute('SELECT user_id FROM user_history WHERE id = ?', (history_id,))
        entry = cursor.fetchone()
        
        if not entry:
            conn.close()
            return jsonify({'success': False, 'message': 'History entry not found'}), 404
        
        if entry['user_id'] != session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        cursor.execute('DELETE FROM user_history WHERE id = ?', (history_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'History entry deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/history/clear', methods=['DELETE'])
@api_login_required
def clear_history():
    """Clear all history for current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM user_history WHERE user_id = ?', (session['user_id'],))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Cleared {deleted_count} history entries'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/history/stats', methods=['GET'])
@api_login_required
def get_history_stats():
    """Get history statistics for current user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get counts by action type
        cursor.execute('''
            SELECT action_type, COUNT(*) as count
            FROM user_history
            WHERE user_id = ?
            GROUP BY action_type
        ''', (session['user_id'],))
        action_stats = {row['action_type']: row['count'] for row in cursor.fetchall()}
        
        # Get counts by item type
        cursor.execute('''
            SELECT item_type, COUNT(*) as count
            FROM user_history
            WHERE user_id = ?
            GROUP BY item_type
        ''', (session['user_id'],))
        item_stats = {row['item_type']: row['count'] for row in cursor.fetchall()}
        
        # Get total count
        cursor.execute('SELECT COUNT(*) FROM user_history WHERE user_id = ?', (session['user_id'],))
        total_count = cursor.fetchone()[0]
        
        # Get recent activity (last 7 days)
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM user_history
            WHERE user_id = ? AND created_at >= DATE('now', '-7 days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        ''', (session['user_id'],))
        recent_activity = {row['date']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total_count,
                'by_action': action_stats,
                'by_item': item_stats,
                'recent_activity': recent_activity
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==========================================
# LIVE PRICES API ROUTES
# ==========================================

@app.route('/api/live-prices', methods=['POST'])
def create_live_price():
    """Create a new live market price post"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    try:
        product_name = request.form.get('product_name', '').strip()
        category = request.form.get('category', '').strip()
        min_price = request.form.get('min_price')
        max_price = request.form.get('max_price')
        price_unit = request.form.get('price_unit', 'Kg')
        price_trend = request.form.get('price_trend', 'stable')
        market_name = request.form.get('market_name', '').strip()
        phone = request.form.get('phone', '').strip()
        area = request.form.get('area', '').strip()
        city = request.form.get('city', '').strip()
        district = request.form.get('district', '').strip()
        state = request.form.get('state', '').strip()
        pin_code = request.form.get('pin_code', '').strip()
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        if not product_name or not category or not min_price or not max_price or not phone:
            return jsonify({'success': False, 'message': 'Product name, category, price range, and phone are required'}), 400

        try:
            min_price = float(min_price)
            max_price = float(max_price)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid price values'}), 400

        if min_price < 0 or max_price < 0 or min_price > max_price:
            return jsonify({'success': False, 'message': 'Invalid price range'}), 400

        lat_val = float(latitude) if latitude else None
        lng_val = float(longitude) if longitude else None

        # Handle image uploads
        image_paths = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for f in files:
                if f and f.filename and allowed_file(f.filename):
                    fname = secure_filename(f.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    fname = f"{timestamp}_{fname}"
                    fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'live_prices', fname)
                    f.save(fpath)
                    image_paths.append(f"static/uploads/live_prices/{fname}")

        # Handle video uploads
        video_paths = []
        if 'videos' in request.files:
            files = request.files.getlist('videos')
            for f in files:
                if f and f.filename:
                    ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else ''
                    if ext in ALLOWED_VIDEO_EXTENSIONS:
                        fname = secure_filename(f.filename)
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        fname = f"{timestamp}_{fname}"
                        fpath = os.path.join(app.config['UPLOAD_FOLDER'], 'live_prices', fname)
                        f.save(fpath)
                        video_paths.append(f"static/uploads/live_prices/{fname}")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO live_prices (user_id, product_name, category, min_price, max_price, price_unit,
                price_trend, market_name, phone, area, city, district, state, pin_code, latitude, longitude, images, videos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], product_name, category, min_price, max_price, price_unit,
              price_trend, market_name, phone, area, city, district, state, pin_code,
              lat_val, lng_val, json.dumps(image_paths), json.dumps(video_paths)))
        conn.commit()
        price_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'message': 'Live price posted successfully', 'id': price_id}), 201

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/live-prices', methods=['GET'])
def get_live_prices():
    """Get all live price posts (only those within 24 hours)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT lp.*, u.name as poster_name
            FROM live_prices lp
            LEFT JOIN users u ON lp.user_id = u.id
            WHERE lp.created_at >= datetime('now', '-24 hours')
            ORDER BY lp.created_at DESC
        ''')
        rows = cursor.fetchall()

        prices = []
        for row in rows:
            price_data = dict(row)
            price_data['images'] = json.loads(price_data.get('images') or '[]')
            price_data['videos'] = json.loads(price_data.get('videos') or '[]')
            # Get feedback stats
            cursor.execute('''
                SELECT COUNT(*) as count, COALESCE(AVG(rating), 0) as avg_rating
                FROM live_price_feedback WHERE price_id = ?
            ''', (price_data['id'],))
            fb = cursor.fetchone()
            price_data['feedback_count'] = fb['count']
            price_data['avg_rating'] = round(fb['avg_rating'], 1)
            prices.append(price_data)

        conn.close()
        return jsonify({'success': True, 'prices': prices}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/live-prices/<int:price_id>', methods=['GET'])
def get_live_price_detail(price_id):
    """Get full details of a single live price post"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT lp.*, u.name as poster_name
            FROM live_prices lp
            LEFT JOIN users u ON lp.user_id = u.id
            WHERE lp.id = ? AND lp.created_at >= datetime('now', '-24 hours')
        ''', (price_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Price post not found or expired'}), 404

        price_data = dict(row)
        price_data['images'] = json.loads(price_data.get('images') or '[]')
        price_data['videos'] = json.loads(price_data.get('videos') or '[]')

        # Get feedback
        cursor.execute('''
            SELECT COUNT(*) as count, COALESCE(AVG(rating), 0) as avg_rating
            FROM live_price_feedback WHERE price_id = ?
        ''', (price_id,))
        fb = cursor.fetchone()
        price_data['feedback_count'] = fb['count']
        price_data['avg_rating'] = round(fb['avg_rating'], 1)

        # Get individual feedback entries
        cursor.execute('''
            SELECT * FROM live_price_feedback
            WHERE price_id = ? ORDER BY created_at DESC
        ''', (price_id,))
        feedbacks = [dict(r) for r in cursor.fetchall()]
        price_data['feedbacks'] = feedbacks

        conn.close()
        return jsonify({'success': True, 'price': price_data}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/live-prices/<int:price_id>/feedback', methods=['POST'])
def submit_live_price_feedback(price_id):
    """Submit feedback for a live price post"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        rating = data.get('rating')
        farmer_name = data.get('farmer_name', '').strip()
        comment = data.get('comment', '').strip()

        if not rating or int(rating) < 1 or int(rating) > 5:
            return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400

        user_id = session.get('user_id')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify post exists and is not expired
        cursor.execute('SELECT id FROM live_prices WHERE id = ? AND created_at >= datetime(\'now\', \'-24 hours\')', (price_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Price post not found or expired'}), 404

        cursor.execute('''
            INSERT INTO live_price_feedback (price_id, user_id, farmer_name, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (price_id, user_id, farmer_name, int(rating), comment))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Feedback submitted successfully'}), 201

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/live-prices/<int:price_id>/feedback', methods=['GET'])
def get_live_price_feedback(price_id):
    """Get all feedback for a live price post"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM live_price_feedback
            WHERE price_id = ? ORDER BY created_at DESC
        ''', (price_id,))
        feedbacks = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
            SELECT COUNT(*) as count, COALESCE(AVG(rating), 0) as avg_rating
            FROM live_price_feedback WHERE price_id = ?
        ''', (price_id,))
        stats = cursor.fetchone()
        conn.close()

        return jsonify({
            'success': True,
            'feedbacks': feedbacks,
            'stats': {
                'count': stats['count'],
                'avg_rating': round(stats['avg_rating'], 1)
            }
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    # Enable debug mode for better error messages
    app.debug = True
    app.run(debug=True, host='0.0.0.0', port=5000)

