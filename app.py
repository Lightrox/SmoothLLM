from flask import Flask, render_template, request, jsonify, session
import os
import json
import sqlite3
from datetime import datetime, timedelta
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Optional CORS for cross-origin frontend (e.g., Netlify)
try:
    from flask_cors import CORS
    FRONTEND_ORIGIN = os.environ.get('FRONTEND_ORIGIN')
    if FRONTEND_ORIGIN:
        CORS(
            app,
            supports_credentials=True,
            origins=[FRONTEND_ORIGIN]
        )
        # Required for third-party cookie delivery over HTTPS
        app.config.update(
            SESSION_COOKIE_SAMESITE='None',
            SESSION_COOKIE_SECURE=True
        )
except Exception:
    # CORS not installed or not needed; proceed without it
    pass

# Database setup
# Allow overriding the database path via env var for Railway volumes
DATABASE = os.environ.get('DATABASE', os.path.join(os.path.dirname(__file__), 'smoothllm.db'))

def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Prompt history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            is_safe BOOLEAN NOT NULL,
            jailbreak_rate REAL NOT NULL,
            perturbations INTEGER NOT NULL,
            perturbation_type TEXT NOT NULL,
            perturbation_pct INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Password reset tokens table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Verify password against hash."""
    return hash_password(password) == password_hash

# Model loading disabled for Netlify deployment
# Using mock analysis instead

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

@app.route('/health')
def health():
    """Simple health check for Railway."""
    return jsonify({
        'status': 'ok'
    })

@app.route('/signin')
def signin():
    """Render the sign-in page."""
    return render_template('signin.html')

@app.route('/signup')
def signup():
    """Render the sign-up page."""
    return render_template('signup.html')

@app.route('/profile')
def profile():
    """Render the profile page. Client will fetch user via /api/user and redirect if unauthenticated."""
    return render_template('profile.html')

@app.route('/reset-password')
def reset_password_page():
    """Render the password reset page."""
    token = request.args.get('token', '')
    return render_template('reset-password.html', token=token)

@app.route('/api/analyze', methods=['POST'])
def analyze_prompt():
    """Analyze a prompt using SmoothLLM."""
    try:
        data = request.get_json()
        
        # Extract parameters
        prompt = data.get('prompt', '').strip()
        num_copies = data.get('smoothllm_num_copies', 10)
        pert_type = data.get('smoothllm_pert_type', 'RandomPatchPerturbation')
        pert_pct = data.get('smoothllm_pert_pct', 10)
        target_model_name = data.get('target_model', 'tinyllama')
        
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        # Use mock analysis for Netlify deployment
        print("Using mock analysis for Netlify deployment...")
        
        # Simple heuristic to determine if prompt is potentially harmful
        harmful_keywords = [
            'kill', 'murder', 'harm', 'hurt', 'attack', 'destroy', 'poison', 
            'bomb', 'hack', 'steal', 'fraud', 'illegal', 'violence', 'weapon',
            'hate', 'discrimination', 'suicide', 'self-harm', 'dangerous',
            'bomb', 'terrorist', 'threat', 'danger', 'weapon', 'gun'
        ]
        
        prompt_lower = prompt.lower()
        is_harmful = any(keyword in prompt_lower for keyword in harmful_keywords)
        
        # Mock jailbreak percentage (higher for harmful prompts)
        jb_percentage = 75.0 if is_harmful else 15.0
        is_safe = bool(jb_percentage < 50)
        
        result = {
            'jb_percentage': float(jb_percentage),
            'is_safe': is_safe,
            'total_prompts': 1,
            'jailbroken_count': int(1 if not is_safe else 0),
            'mock_response': True,
            'message': 'Using mock analysis (Netlify deployment - no ML models)'
        }
        
        # Save to history if user is logged in
        if 'user_id' in session:
            save_prompt_history(
                user_id=session['user_id'],
                prompt=prompt,
                is_safe=is_safe,
                jailbreak_rate=jb_percentage,
                perturbations=num_copies,
                perturbation_type=pert_type,
                perturbation_pct=pert_pct
            )
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in analyze_prompt: {e}")
        return jsonify({'error': 'Analysis failed'}), 500

@app.route('/api/signin', methods=['POST'])
def api_signin():
    """Handle user sign in."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()
        
        if user and verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            
            return jsonify({
                'success': True,
                'user': {
                    'id': user['id'],
                    'name': user['name'],
                    'email': user['email']
                }
            })
        else:
            return jsonify({'error': 'Invalid email or password'}), 401
            
    except Exception as e:
        print(f"Error in api_signin: {e}")
        return jsonify({'error': 'Sign in failed'}), 500

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """Handle user sign up."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not all([name, email, password]):
            return jsonify({'error': 'All fields are required'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        conn = get_db_connection()
        
        # Check if user already exists
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()
        
        if existing_user:
            conn.close()
            return jsonify({'error': 'User already exists'}), 409
        
        # Create new user
        password_hash = hash_password(password)
        cursor = conn.execute(
            'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
            (name, email, password_hash)
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Set session
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'name': name,
                'email': email
            }
        })
        
    except Exception as e:
        print(f"Error in api_signup: {e}")
        return jsonify({'error': 'Sign up failed'}), 500

@app.route('/api/signout', methods=['POST'])
def api_signout():
    """Handle user sign out."""
    session.clear()
    return jsonify({'success': True})

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get user's prompt history."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        conn = get_db_connection()
        history = conn.execute(
            '''SELECT * FROM prompt_history 
               WHERE user_id = ? 
               ORDER BY created_at DESC 
               LIMIT 50''',
            (session['user_id'],)
        ).fetchall()
        conn.close()
        
        history_list = []
        for item in history:
            history_list.append({
                'id': item['id'],
                'prompt': item['prompt'],
                'is_safe': bool(item['is_safe']),
                'jailbreak_rate': item['jailbreak_rate'],
                'perturbations': item['perturbations'],
                'perturbation_type': item['perturbation_type'],
                'perturbation_pct': item['perturbation_pct'],
                'created_at': item['created_at']
            })
        
        return jsonify({'history': history_list})
        
    except Exception as e:
        print(f"Error in get_history: {e}")
        return jsonify({'error': 'Failed to fetch history'}), 500

def save_prompt_history(user_id, prompt, is_safe, jailbreak_rate, perturbations, perturbation_type, perturbation_pct):
    """Save prompt analysis to history."""
    try:
        conn = get_db_connection()
        conn.execute(
            '''INSERT INTO prompt_history 
               (user_id, prompt, is_safe, jailbreak_rate, perturbations, perturbation_type, perturbation_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, prompt, is_safe, jailbreak_rate, perturbations, perturbation_type, perturbation_pct)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving prompt history: {e}")

@app.route('/api/user', methods=['GET'])
def get_user():
    """Get current user information."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    return jsonify({
        'user': {
            'id': session['user_id'],
            'name': session['user_name'],
            'email': session['user_email']
        }
    })

@app.route('/api/user/stats', methods=['GET'])
def get_user_stats():
    """Get user statistics."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        conn = get_db_connection()
        
        # Get total analyses count
        total_analyses = conn.execute(
            'SELECT COUNT(*) as count FROM prompt_history WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()['count']
        
        # Get safe/unsafe counts
        safe_count = conn.execute(
            'SELECT COUNT(*) as count FROM prompt_history WHERE user_id = ? AND is_safe = 1',
            (session['user_id'],)
        ).fetchone()['count']
        
        unsafe_count = total_analyses - safe_count
        
        # Get average jailbreak rate
        avg_jailbreak = conn.execute(
            'SELECT AVG(jailbreak_rate) as avg_rate FROM prompt_history WHERE user_id = ?',
            (session['user_id'],)
        ).fetchone()['avg_rate'] or 0
        
        conn.close()
        
        return jsonify({
            'total_analyses': total_analyses,
            'safe_prompts': safe_count,
            'unsafe_prompts': unsafe_count,
            'avg_jailbreak_rate': round(avg_jailbreak, 1)
        })
        
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500

@app.route('/api/user/export', methods=['GET'])
def export_user_data():
    """Export user data as JSON."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        conn = get_db_connection()
        
        # Get user info
        user = conn.execute(
            'SELECT * FROM users WHERE id = ?', (session['user_id'],)
        ).fetchone()
        
        # Get user history
        history = conn.execute(
            '''SELECT * FROM prompt_history 
               WHERE user_id = ? 
               ORDER BY created_at DESC''',
            (session['user_id'],)
        ).fetchall()
        
        conn.close()
        
        # Prepare export data
        export_data = {
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'created_at': user['created_at']
            },
            'history': [
                {
                    'id': item['id'],
                    'prompt': item['prompt'],
                    'is_safe': bool(item['is_safe']),
                    'jailbreak_rate': item['jailbreak_rate'],
                    'perturbations': item['perturbations'],
                    'perturbation_type': item['perturbation_type'],
                    'perturbation_pct': item['perturbation_pct'],
                    'created_at': item['created_at']
                }
                for item in history
            ],
            'export_date': datetime.now().isoformat(),
            'total_records': len(history)
        }
        
        return jsonify(export_data)
        
    except Exception as e:
        print(f"Error in export_user_data: {e}")
        return jsonify({'error': 'Failed to export data'}), 500

@app.route('/api/user/update', methods=['POST'])
def update_user_profile():
    """Update user profile information."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        
        if not name or not email:
            return jsonify({'error': 'Name and email are required'}), 400
        
        conn = get_db_connection()
        
        # Check if email is already taken by another user
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ? AND id != ?', 
            (email, session['user_id'])
        ).fetchone()
        
        if existing_user:
            conn.close()
            return jsonify({'error': 'Email already in use'}), 409
        
        # Update user information
        conn.execute(
            'UPDATE users SET name = ?, email = ? WHERE id = ?',
            (name, email, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        # Update session
        session['user_name'] = name
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'id': session['user_id'],
                'name': name,
                'email': email
            }
        })
        
    except Exception as e:
        print(f"Error in update_user_profile: {e}")
        return jsonify({'error': 'Failed to update profile'}), 500

@app.route('/api/user/change-password', methods=['POST'])
def change_password():
    """Change user password."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current and new passwords are required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400
        
        conn = get_db_connection()
        
        # Get current user
        user = conn.execute(
            'SELECT password_hash FROM users WHERE id = ?', 
            (session['user_id'],)
        ).fetchone()
        
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        # Verify current password
        if not verify_password(current_password, user['password_hash']):
            conn.close()
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Update password
        new_password_hash = hash_password(new_password)
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (new_password_hash, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Password updated successfully'})
        
    except Exception as e:
        print(f"Error in change_password: {e}")
        return jsonify({'error': 'Failed to change password'}), 500

@app.route('/api/user/delete', methods=['POST'])
def delete_user_account():
    """Delete user account and all associated data."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        password = data.get('password', '')
        
        if not password:
            return jsonify({'error': 'Password confirmation is required'}), 400
        
        conn = get_db_connection()
        
        # Get current user
        user = conn.execute(
            'SELECT password_hash FROM users WHERE id = ?', 
            (session['user_id'],)
        ).fetchone()
        
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            conn.close()
            return jsonify({'error': 'Password is incorrect'}), 401
        
        # Delete user data (cascade will handle prompt_history)
        conn.execute('DELETE FROM users WHERE id = ?', (session['user_id'],))
        conn.commit()
        conn.close()
        
        # Clear session
        session.clear()
        
        return jsonify({'success': True, 'message': 'Account deleted successfully'})
        
    except Exception as e:
        print(f"Error in delete_user_account: {e}")
        return jsonify({'error': 'Failed to delete account'}), 500

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """Send password reset email."""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        conn = get_db_connection()
        
        # Check if user exists
        user = conn.execute(
            'SELECT id, name FROM users WHERE email = ?', (email,)
        ).fetchone()
        
        if not user:
            conn.close()
            # Don't reveal if email exists or not for security
            return jsonify({'success': True, 'message': 'If the email exists, a reset link has been sent'})
        
        # Generate reset token
        reset_token = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=1)  # Token expires in 1 hour
        
        # Store reset token
        conn.execute(
            'INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)',
            (user['id'], reset_token, expires_at)
        )
        conn.commit()
        conn.close()
        
        # Send reset email (in production, you'd use a real email service)
        try:
            send_password_reset_email(email, user['name'], reset_token)
        except Exception as e:
            print(f"Email sending failed: {e}")
            # Still return success for security
        
        return jsonify({'success': True, 'message': 'If the email exists, a reset link has been sent'})
        
    except Exception as e:
        print(f"Error in forgot_password: {e}")
        return jsonify({'error': 'Failed to process request'}), 500

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """Reset password using token."""
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        new_password = data.get('password', '')
        
        if not token or not new_password:
            return jsonify({'error': 'Token and password are required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        conn = get_db_connection()
        
        # Find valid token
        token_record = conn.execute(
            '''SELECT prt.*, u.email FROM password_reset_tokens prt
               JOIN users u ON prt.user_id = u.id
               WHERE prt.token = ? AND prt.used = FALSE AND prt.expires_at > ?''',
            (token, datetime.now())
        ).fetchone()
        
        if not token_record:
            conn.close()
            return jsonify({'error': 'Invalid or expired token'}), 400
        
        # Update password
        new_password_hash = hash_password(new_password)
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (new_password_hash, token_record['user_id'])
        )
        
        # Mark token as used
        conn.execute(
            'UPDATE password_reset_tokens SET used = TRUE WHERE id = ?',
            (token_record['id'],)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Password reset successfully'})
        
    except Exception as e:
        print(f"Error in reset_password: {e}")
        return jsonify({'error': 'Failed to reset password'}), 500

def send_password_reset_email(email, name, token):
    """Send password reset email (mock implementation for demo)."""
    # In a real application, you would use a service like SendGrid, AWS SES, etc.
    reset_url = f"{request.host_url}reset-password?token={token}"
    
    subject = "SmoothLLM - Password Reset Request"
    body = f"""
    Hello {name},
    
    You requested a password reset for your SmoothLLM account.
    
    Click the link below to reset your password:
    {reset_url}
    
    This link will expire in 1 hour.
    
    If you didn't request this reset, please ignore this email.
    
    Best regards,
    SmoothLLM Team
    """
    
    # For demo purposes, just print the email content
    print(f"Password reset email for {email}:")
    print(f"Subject: {subject}")
    print(f"Body: {body}")
    print(f"Reset URL: {reset_url}")
    
    # In production, you would send the actual email here
    # Example with SMTP:
    # msg = MIMEMultipart()
    # msg['From'] = "noreply@smoothllm.com"
    # msg['To'] = email
    # msg['Subject'] = subject
    # msg.attach(MIMEText(body, 'plain'))
    # 
    # server = smtplib.SMTP('smtp.gmail.com', 587)
    # server.starttls()
    # server.login("your-email@gmail.com", "your-password")
    # server.send_message(msg)
    # server.quit()

@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    """Handle file upload and batch processing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        # Check file size (10MB limit)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return jsonify({'success': False, 'message': 'File too large. Maximum size is 10MB'}), 400
        
        # Read file content
        content = file.read().decode('utf-8')
        filename = file.filename
        
        # Process file based on extension
        prompts = []
        if filename.endswith('.json'):
            try:
                data = json.loads(content)
                prompts = data if isinstance(data, list) else [data]
            except json.JSONDecodeError:
                return jsonify({'success': False, 'message': 'Invalid JSON format'}), 400
        elif filename.endswith('.csv'):
            lines = content.split('\n')
            prompts = [line.strip() for line in lines if line.strip()]
        else:  # .txt or other text files
            lines = content.split('\n')
            prompts = [line.strip() for line in lines if line.strip()]
        
        if not prompts:
            return jsonify({'success': False, 'message': 'No valid prompts found in file'}), 400
        
        # Store file processing results
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create file_uploads table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                prompt_count INTEGER NOT NULL,
                processed_count INTEGER DEFAULT 0,
                safe_count INTEGER DEFAULT 0,
                threat_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert file record
        cursor.execute('''
            INSERT INTO file_uploads (filename, file_size, prompt_count)
            VALUES (?, ?, ?)
        ''', (filename, file_size, len(prompts)))
        
        file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'File uploaded successfully. Found {len(prompts)} prompts.',
            'file_id': file_id,
            'prompt_count': len(prompts),
            'prompts': prompts[:10]  # Return first 10 prompts for preview
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error processing file: {str(e)}'}), 500

@app.route('/api/process-batch', methods=['POST'])
def process_batch():
    """Process batch of prompts"""
    try:
        data = request.get_json()
        prompts = data.get('prompts', [])
        file_id = data.get('file_id')
        
        if not prompts:
            return jsonify({'success': False, 'message': 'No prompts provided'}), 400
        
        # Simulate batch processing
        results = []
        safe_count = 0
        threat_count = 0
        
        for i, prompt in enumerate(prompts):
            # Simulate analysis (replace with actual SmoothLLM analysis)
            import random
            is_safe = random.random() > 0.3  # 70% safe, 30% threats
            
            if is_safe:
                safe_count += 1
                status = 'safe'
            else:
                threat_count += 1
                status = 'threat'
            
            results.append({
                'prompt': prompt,
                'status': status,
                'jailbreak_rate': random.uniform(0, 0.8) if not is_safe else random.uniform(0, 0.2),
                'analysis_time': random.uniform(0.1, 0.5)
            })
        
        # Update file upload record
        if file_id:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE file_uploads 
                SET processed_count = ?, safe_count = ?, threat_count = ?
                WHERE id = ?
            ''', (len(prompts), safe_count, threat_count, file_id))
            conn.commit()
            conn.close()
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': len(prompts),
                'safe': safe_count,
                'threats': threat_count,
                'avg_response_time': sum(r['analysis_time'] for r in results) / len(results)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error processing batch: {str(e)}'}), 500

@app.route('/api/dashboard-stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total analyses
        cursor.execute('SELECT COUNT(*) FROM prompt_history')
        total_analyses = cursor.fetchone()[0]
        
        # Get safe prompts (assuming jailbreak_rate < 0.3 means safe)
        cursor.execute('SELECT COUNT(*) FROM prompt_history WHERE jailbreak_rate < 0.3')
        safe_prompts = cursor.fetchone()[0]
        
        # Get threats detected
        cursor.execute('SELECT COUNT(*) FROM prompt_history WHERE jailbreak_rate >= 0.3')
        threats_detected = cursor.fetchone()[0]
        
        # Get average response time (simulated)
        avg_response_time = 0.2  # This would be calculated from actual response times
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_analyses': total_analyses,
                'safe_prompts': safe_prompts,
                'threats_detected': threats_detected,
                'avg_response_time': avg_response_time
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error getting stats: {str(e)}'}), 500

# Initialize database
init_db()

if __name__ == '__main__':
    # Run the app
    app.run(debug=True, host='0.0.0.0', port=5000)
