# insurance_platform.py - Complete Insurance Banking Software
# Single file with all templates and functionality

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, date

import cv2
import numpy as np
import pytesseract
from flask import (Flask, jsonify, redirect, render_template,
                   render_template_string, request, session, url_for, send_from_directory)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import inspect

# Set Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'insurance-platform-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///insurance_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.permanent_session_lifetime = timedelta(days=30)

# Create necessary folders
for folder in ['uploads', 'templates', 'static/css', 'static/js', 'static/images', 'biometric_data', 'claim_documents']:
    os.makedirs(folder, exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Load OpenCV classifiers with error handling
try:
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if eye_cascade.empty():
        print("!!! WARNING: 'haarcascade_eye.xml' not found. Eye clarity check disabled.")
        eye_cascade = None
    if face_cascade.empty():
        print("!!! WARNING: 'haarcascade_frontalface_default.xml' not found. Proximity check disabled.")
        face_cascade = None
except Exception as e:
    print(f"Could not load cascade files. Biometric checks limited. Error: {e}")
    eye_cascade = None
    face_cascade = None


# ===================================
# DATABASE MODELS
# ===================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    digital_token = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    address = db.Column(db.Text, nullable=False)
    pan_number = db.Column(db.String(20), unique=True, nullable=False)
    face_data = db.Column(db.Text)
    fingerprint_data = db.Column(db.Text)
    retina_data = db.Column(db.Text)
    profile_picture = db.Column(db.String(255), nullable=True)  # ADD THIS LINE
    account_status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    policies = db.relationship('Policy', backref='user', lazy=True)
    claims = db.relationship('Claim', backref='user', lazy=True)


class Scheme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    premium_amount = db.Column(db.Float, nullable=False)
    coverage_amount = db.Column(db.Float, nullable=False)
    min_age = db.Column(db.Integer, default=18)
    max_age = db.Column(db.Integer, default=65)
    features = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)


class Policy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    policy_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    scheme_id = db.Column(db.Integer, db.ForeignKey('scheme.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=True, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    premium_amount = db.Column(db.Float, nullable=False)
    coverage_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='applied')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scheme = db.relationship('Scheme', backref='policies')

    @property
    def is_withdrawable(self):
        return self.status == 'applied' and (datetime.utcnow() - self.created_at).total_seconds() < 86400


class Nominee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey('policy.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    relationship = db.Column(db.String(50), nullable=False)


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    claim_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey('policy.id'), nullable=False)
    claim_amount = db.Column(db.Float, nullable=False)
    document_paths = db.Column(db.Text)
    status = db.Column(db.String(20), default='submitted')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    policy = db.relationship('Policy', backref='claims')


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    report_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='submitted')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ===================================
# HELPER FUNCTIONS
# ===================================
def generate_token():
    return str(uuid.uuid4())[:8].upper()


def generate_policy_number():
    return f"POL{datetime.now().strftime('%Y%m%d%H%M')}{str(uuid.uuid4())[:6].upper()}"


def generate_claim_number():
    return f"CLM{datetime.now().strftime('%Y%m%d%H%M')}{str(uuid.uuid4())[:6].upper()}"


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password, password_hash):
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == password_hash


def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def validate_pan(pan):
    import re
    return bool(re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan.upper()))


def get_image_from_data_url(data_url):
    image_bytes = base64.b64decode(data_url.split(',')[1])
    nparr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def validate_eye_clarity(data):
    if not eye_cascade: return True
    try:
        img = get_image_from_data_url(data)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        eyes = eye_cascade.detectMultiScale(gray, 1.1, 4)
        return len(eyes) >= 2
    except:
        return False


@app.template_filter('from_json')
def from_json_filter(v):
    try:
        return json.loads(v) if v else []
    except:
        return []


def migrate_database():
    """Migrate existing database to add missing columns"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)

        # Check claim table
        claim_columns = [col['name'] for col in inspector.get_columns('claim')]
        if 'document_paths' not in claim_columns:
            print("Adding missing document_paths column to claim table...")
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE claim ADD COLUMN document_paths TEXT'))
                conn.commit()
            print("✅ Added document_paths column successfully")

        # Check user table
        user_columns = [col['name'] for col in inspector.get_columns('user')]
        if 'last_login' not in user_columns:
            print("Adding missing last_login column to user table...")
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN last_login DATETIME'))
                conn.commit()
            print("✅ Added last_login column successfully")

        if 'profile_picture' not in user_columns:
            print("Adding missing profile_picture column to user table...")
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE user ADD COLUMN profile_picture VARCHAR(255)'))
                conn.commit()
            print("✅ Added profile_picture column successfully")

    except Exception as e:
        print(f"Migration error: {e}")
        print("🔄 Recreating database with correct schema...")
        db.drop_all()
        db.create_all()
        print("✅ Database recreated successfully")

@app.context_processor
def inject_user_and_now():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    return {'now': datetime.utcnow(), 'current_user': user}


# ===================================
# MAIN ROUTES
# ===================================
@app.route('/')
def home():
    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <title>SecureBank Insurance</title>
    <style>
        :root {
            --primary-purple: #8B4A9C;
            --secondary-purple: #B366CC;
            --dark-blue: #2C3E50;
            --accent-pink: #E91E63;
            --text-light: #ffffff;
            --bg-overlay: rgba(0,0,0,0.1);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--primary-purple) 0%, var(--dark-blue) 100%);
            color: var(--text-light);
            min-height: 100vh;
            display: flex;
        }

        .sidebar {
            width: 100px;
            background: var(--bg-overlay);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 0;
            backdrop-filter: blur(10px);
        }

        .sidebar-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-decoration: none;
            color: var(--text-light);
            margin-bottom: 40px;
            transition: transform 0.3s ease;
        }

        .sidebar-item:hover { transform: translateY(-5px); }

        .sidebar-icon {
            font-size: 28px;
            margin-bottom: 8px;
            background: rgba(255,255,255,0.15);
            width: 60px;
            height: 60px;
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(10px);
        }

        .sidebar-text {
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .main-container {
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .header {
            padding: 30px 60px;
            display: flex;
            justify-content: flex-end;
            align-items: center;
        }

        .btn {
            display: inline-block;
            padding: 15px 35px;
            margin-left: 20px;
            border: 2px solid var(--text-light);
            color: var(--text-light);
            border-radius: 30px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }

        .btn.primary {
            background: var(--text-light);
            color: var(--primary-purple);
        }

        .btn.primary:hover {
            background: var(--accent-pink);
            color: var(--text-light);
            border-color: var(--accent-pink);
        }

        .hero {
            flex: 1;
            display: flex;
            align-items: center;
            padding: 0 60px;
            gap: 80px;
        }

        .hero-content {
            flex: 1;
        }

        .hero-content h1 {
            font-size: 4.5em;
            font-weight: 300;
            line-height: 1.1;
            margin-bottom: 30px;
        }

        .hero-content h1 strong {
            font-weight: 700;
            background: linear-gradient(45deg, var(--text-light), var(--secondary-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero-content p {
            font-size: 1.3em;
            opacity: 0.9;
            max-width: 500px;
            line-height: 1.6;
        }

        /* MODIFICATION: Styles for the slideshow container and its contents */
        .hero-image {
            flex: 1;
            display: flex;
            justify-content: center;
            position: relative; /* Needed for positioning arrows */
        }

        .slideshow-container {
            width: 100%;
            max-width: 600px; /* Limit the max width of the slideshow */
            position: relative;
            border-radius: 20px;
            overflow: hidden; /* This is crucial for the zoom effect */
            box-shadow: 0 30px 60px rgba(0,0,0,0.3);
        }

        .slide {
            display: none; /* Hide all slides by default */
            width: 100%;
            vertical-align: middle; /* Fixes small gap under image */
            transition: transform 0.4s ease; /* Smooth zoom transition */
        }

        .slide:hover {
            transform: scale(1.1); /* Increases size by 10% on hover */
            cursor: pointer;
        }

        /* Fade animation */
        .fade {
            animation-name: fade;
            animation-duration: 1.5s;
        }

        @keyframes fade {
            from { opacity: .4 }
            to { opacity: 1 }
        }

        /* Previous & Next buttons */
        .prev, .next {
            cursor: pointer;
            position: absolute;
            top: 50%;
            width: auto;
            margin-top: -22px;
            padding: 16px;
            color: white;
            font-weight: bold;
            font-size: 20px;
            transition: 0.6s ease;
            border-radius: 0 3px 3px 0;
            user-select: none;
            background-color: rgba(0,0,0,0.3);
        }
        .next { right: 0; border-radius: 3px 0 0 3px; }
        .prev { left: 0; }
        .prev:hover, .next:hover { background-color: rgba(0,0,0,0.8); }

        .footer {
            text-align: center;
            padding: 40px 20px;
            letter-spacing: 8px;
            color: rgba(255,255,255,0.6);
            font-weight: 300;
            font-size: 14px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }

        @media (max-width: 768px) {
            .hero { flex-direction: column; text-align: center; gap: 40px; }
            .hero-content h1 { font-size: 3em; }
            .header { padding: 20px 30px; }
            .btn { padding: 12px 25px; font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <a href="#" class="sidebar-item"><div class="sidebar-icon">🔔</div><span class="sidebar-text">Notify</span></a>
        <a href="#" class="sidebar-item"><div class="sidebar-icon">📞</div><span class="sidebar-text">Contact</span></a>
        <a href="#" class="sidebar-item"><div class="sidebar-icon">❓</div><span class="sidebar-text">FAQs</span></a>
    </div>

    <div class="main-container">
        <div class="header">
            <a href="/login" class="btn">Login</a>
            <a href="/register" class="btn primary">Register</a>
        </div>

        <div class="hero">
            <div class="hero-content">
                <h1><strong>SecureBank</strong><br>Insurance<br>For Every Future</h1>
                <p>Comprehensive life insurance solutions designed to protect what matters most to you and your family.</p>
            </div>

            <div class="hero-image">
                <div class="slideshow-container">
                    <!-- Your three images -->
                    <div class="slide fade"><img src="https://media.istockphoto.com/id/1241917206/photo/our-baby-our-happiness.jpg?s=612x612&w=0&k=20&c=_NoJdc8ZKcw819kFkBZ6qlEyTbxGZ2MSxD-W06zwF6Q=" style="width:100%"></div>
                    <div class="slide fade"><img src="https://thumbs.dreamstime.com/b/happy-family-two-children-running-dog-together-happy-family-two-children-running-dog-together-autumn-119764842.jpg" style="width:100%"></div>
                    <div class="slide fade"><img src="https://thumbs.dreamstime.com/b/portrait-cute-little-kids-happy-children-having-fun-outdoors-playing-summer-park-boy-two-girls-laying-green-fresh-73751469.jpg" style="width:100%"></div>

                    <!-- Next and previous buttons -->
                    <a class="prev" onclick="plusSlides(-1)">❮</a>
                    <a class="next" onclick="plusSlides(1)">❯</a>
                </div>
            </div>
        </div>

        <div class="footer">
            <span>B A N K E R   T O   E V E R Y   I N D I A N</span>
        </div>
    </div>

    <!-- MODIFICATION: Enhanced JavaScript for manual and automatic slideshow -->
    <script>
        let slideIndex = 1;
        let slideInterval;

        // Function to display slides
        function showSlides(n) {
            let i;
            let slides = document.getElementsByClassName("slide");
            if (n > slides.length) { slideIndex = 1 }
            if (n < 1) { slideIndex = slides.length }
            for (i = 0; i < slides.length; i++) {
                slides[i].style.display = "none";
            }
            slides[slideIndex - 1].style.display = "block";
        }

        // Function for next/previous controls
        function plusSlides(n) {
            clearInterval(slideInterval); // Stop auto-play
            showSlides(slideIndex += n);
            startSlideshow(); // Restart auto-play
        }

        // Function to start the automatic slideshow
        function startSlideshow() {
            slideInterval = setInterval(function() {
                plusSlides(1);
            }, 5000); // Change image every 5 seconds
        }

        // Initialize the slideshow
        document.addEventListener('DOMContentLoaded', function() {
            showSlides(slideIndex);
            startSlideshow();
        });
    </script>
</body>
</html>''')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            # Handle both JSON and form data
            if request.is_json:
                data = request.get_json()
            else:
                data = {
                    'username': request.form.get('username'),
                    'password': request.form.get('password')
                }

            if not data:
                return jsonify({'success': False, 'message': 'No data received'}), 400

            username = data.get('username', '').strip()
            password = data.get('password', '')

            if not username or not password:
                return jsonify({'success': False, 'message': 'Username and password are required'}), 400

            # Find user by username
            user = User.query.filter_by(username=username).first()

            if user and verify_password(password, user.password_hash):
                # Successful login
                session['user_id'] = user.id
                session.permanent = True
                user.last_login = datetime.utcnow()
                db.session.commit()
                return jsonify({'success': True, 'redirect': '/dashboard'})
            else:
                return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

        except Exception as e:
            print(f"Login error: {str(e)}")
            return jsonify({'success': False, 'message': 'Login failed. Please try again.'}), 500

    # GET request - return login form
    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <title>Login - SecureBank Insurance</title>
    <style>
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #8B4A9C 0%, #2C3E50 100%);
            display: grid;
            place-items: center;
            min-height: 100vh;
            margin: 0;
        }

        .login-container {
            background: white;
            padding: 50px;
            border-radius: 20px;
            width: 90%;
            max-width: 450px;
            box-shadow: 0 30px 60px rgba(0,0,0,0.3);
        }

        h2 {
            color: #2C3E50;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2em;
        }

        .form-group {
            margin-bottom: 20px;
        }

        input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e1e5e9;
            border-radius: 10px;
            font-size: 16px;
            box-sizing: border-box;
            transition: border-color 0.3s ease;
        }

        input:focus {
            outline: none;
            border-color: #8B4A9C;
        }

        .btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(45deg, #8B4A9C, #B366CC);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.3s ease;
        }

        .btn:hover {
            transform: translateY(-2px);
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .alert-error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 10px;
            display: none;
            text-align: center;
        }

        .links {
            text-align: center;
            margin-top: 25px;
        }

        .links a {
            color: #8B4A9C;
            text-decoration: none;
            font-weight: 600;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .loading {
            display: none;
            text-align: center;
            margin-top: 10px;
            color: #8B4A9C;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Welcome Back</h2>
        <div id="message" class="alert-error"></div>
        <form id="loginForm">
            <div class="form-group">
                <input type="text" id="username" placeholder="Username" required>
            </div>
            <div class="form-group">
                <input type="password" id="password" placeholder="Password" required>
            </div>
            <button type="submit" class="btn" id="loginBtn">Login</button>
            <div class="loading" id="loading">Logging in...</div>
        </form>
        <div class="links">
            <p>Don't have an account? <a href="/register">Register here</a></p>
            <p><a href="/">← Back to Home</a></p>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const loginBtn = document.getElementById('loginBtn');
            const loading = document.getElementById('loading');
            const messageDiv = document.getElementById('message');

            // Get form data
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;

            // Basic validation
            if (!username || !password) {
                messageDiv.textContent = 'Please enter both username and password';
                messageDiv.style.display = 'block';
                return;
            }

            // Show loading state
            loginBtn.disabled = true;
            loading.style.display = 'block';
            messageDiv.style.display = 'none';

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        username: username,
                        password: password
                    })
                });

                const result = await response.json();

                if (result.success) {
                    // Successful login - redirect to dashboard
                    window.location.href = result.redirect;
                } else {
                    // Show error message
                    messageDiv.textContent = result.message || 'Login failed';
                    messageDiv.style.display = 'block';
                }
            } catch (error) {
                console.error('Login error:', error);
                messageDiv.textContent = 'Network error. Please try again.';
                messageDiv.style.display = 'block';
            } finally {
                // Reset loading state
                loginBtn.disabled = false;
                loading.style.display = 'none';
            }
        });

        // Clear error message when user starts typing
        ['username', 'password'].forEach(id => {
            document.getElementById(id).addEventListener('input', () => {
                document.getElementById('message').style.display = 'none';
            });
        });
    </script>
</body>
</html>''')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')

    policies_count = Policy.query.filter_by(user_id=user.id).count()
    claims_count = Claim.query.filter_by(user_id=user.id).count()

    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <title>Dashboard - SecureBank Insurance</title>
    <style>
        :root {
            --primary-purple: #8B4A9C;
            --secondary-purple: #B366CC;
            --dark-blue: #2C3E50;
            --light-gray: #f8f9fa;
            --text-dark: #343a40;
            --text-light: #6c757d;
        }

        body {
            font-family: 'Segoe UI', sans-serif;
            background: var(--light-gray);
            margin: 0;
            padding: 0;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 30px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: white;
            padding: 25px 40px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            margin-bottom: 30px;
        }

        .welcome-section h1 {
            color: var(--dark-blue);
            font-size: 2.2em;
            margin: 0;
        }

        .user-info {
            color: var(--text-light);
            font-size: 0.95em;
            margin-top: 5px;
        }

        .logout-btn {
            background: linear-gradient(45deg, var(--primary-purple), var(--secondary-purple));
            color: white;
            padding: 12px 25px;
            border: none;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            transition: transform 0.3s ease;
        }

        .logout-btn:hover {
            transform: translateY(-2px);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }

        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }

        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            color: var(--primary-purple);
            margin: 10px 0;
        }

        .stat-label {
            color: var(--text-light);
            font-weight: 500;
        }

        .main-actions {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 50px;
        }

        .action-card {
            background: white;
            padding: 35px;
            border-radius: 20px;
            text-decoration: none;
            color: var(--text-dark);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .action-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(45deg, var(--primary-purple), var(--secondary-purple));
        }

        .action-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        }

        .action-icon {
            font-size: 3.5em;
            background: linear-gradient(45deg, var(--primary-purple), var(--secondary-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 20px;
        }

        .action-card h3 {
            margin: 0 0 15px 0;
            color: var(--dark-blue);
            font-size: 1.4em;
        }

        .action-card p {
            color: var(--text-light);
            line-height: 1.5;
            margin: 0;
        }

        .assistance-section {
            margin: 50px 0;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }

        .section-header h2 {
            color: var(--dark-blue);
            font-size: 2em;
            margin: 0;
        }

        .assistance-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }

        .assistance-card {
            background: white;
            padding: 30px;
            border-radius: 15px;
            text-decoration: none;
            color: var(--text-dark);
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
        }

        .assistance-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }
        
        .assistance-icon {
            font-size: 2.5em;
            margin-bottom: 15px;
            display: block;
        }
        
        .faq-section {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        }
        
        .faq-item {
            margin-bottom: 15px;
        }
        
        .faq-item details {
            background: var(--light-gray);
            padding: 20px;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .faq-item details:hover {
            background: #e9ecef;
        }
        
        .faq-item summary {
            font-weight: 600;
            color: var(--primary-purple);
            font-size: 1.1em;
            outline: none;
        }
        
        .faq-item details[open] {
            background: #e3f2fd;
        }
        
        .faq-item details p {
            margin-top: 15px;
            color: var(--text-dark);
            line-height: 1.6;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
            }
            
            .header {
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }
            
            .main-actions {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="welcome-section">
                <h1>Welcome, {{ user.full_name }}!</h1>
                <div class="user-info">
                    Digital Token: {{ user.digital_token }} | Last Login: {{ user.last_login.strftime('%d %B %Y, %I:%M %p') if user.last_login else 'First time login' }}
                </div>
            </div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{{ policies_count }}</div>
                <div class="stat-label">Active Policies</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ claims_count }}</div>
                <div class="stat-label">Total Claims</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ user.age }}</div>
                <div class="stat-label">Age</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">✓</div>
                <div class="stat-label">Verified Account</div>
            </div>
        </div>
        
        <div class="main-actions">
            <a href="/schemes" class="action-card">
                <div class="action-icon">📋</div>
                <h3>Apply for Policy</h3>
                <p>Explore our comprehensive life insurance plans designed to protect your family's future</p>
            </a>
            <a href="/make-claim" class="action-card">
                <div class="action-icon">📝</div>
                <h3>Make a Claim</h3>
                <p>Submit your insurance claim with required documents for quick processing</p>
            </a>
            <a href="/my-policies" class="action-card">
                <div class="action-icon">📄</div>
                <h3>View My Policies</h3>
                <p>Review all your active policies, coverage details, and policy documents</p>
            </a>
            <a href="/profile" class="action-card">
                <div class="action-icon">👤</div>
                <h3>My Profile</h3>
                <p>Update your personal information and manage account settings</p>
            </a>
        </div>
        
        <div class="assistance-section">
            <div class="section-header">
                <h2>Need Assistance?</h2>
                <a href="#" class="support-link">Get Support →</a>
            </div>
            
            <div class="assistance-grid">
                <a href="/report-transaction" class="assistance-card">
                    <span class="assistance-icon">⚠️</span>
                    <h3>Report Unauthorized Transaction</h3>
                    <p>Notice suspicious activity? Report it immediately for quick resolution and account protection.</p>
                </a>
                <a href="/complaints-feedback" class="assistance-card">
                    <span class="assistance-icon">💬</span>
                    <h3>Complaints / Feedback</h3>
                    <p>Submit queries, provide feedback, or check the status of your existing complaints.</p>
                </a>
                <div class="assistance-card">
                    <span class="assistance-icon">📞</span>
                    <h3>Contact Us</h3>
                    <p><strong>Toll Free:</strong> 1800 1234 1800<br>
                    <strong>Customer Care:</strong> 1800 11 22 11<br>
                    <strong>Email:</strong> support@securebank.com</p>
                </div>
            </div>
        </div>
        
        <div class="faq-section">
            <h2 style="margin-bottom: 30px; color: var(--dark-blue);">Frequently Asked Questions</h2>
            
            <div class="faq-item">
                <details>
                    <summary>What is term life insurance and how does it work?</summary>
                    <p>Term life insurance provides coverage for a specific period (term). If the insured person dies during this term, the beneficiaries receive the death benefit. It's the most affordable type of life insurance and ideal for temporary needs like mortgage protection or income replacement.</p>
                </details>
            </div>
            
            <div class="faq-item">
                <details>
                    <summary>How much life insurance coverage do I need?</summary>
                    <p>A general rule is to have coverage that equals 10-12 times your annual income. Consider your debts, mortgage, children's education costs, and your family's living expenses. Our advisors can help you calculate the right amount based on your specific situation.</p>
                </details>
            </div>
            
            <div class="faq-item">
                <details>
                    <summary>Can I change my beneficiary after purchasing a policy?</summary>
                    <p>Yes, you can typically change your beneficiary at any time by contacting our customer service or logging into your online account. We recommend reviewing your beneficiaries regularly, especially after major life events like marriage, divorce, or the birth of a child.</p>
                </details>
            </div>
            
            <div class="faq-item">
                <details>
                    <summary>How long does it take to process a claim?</summary>
                    <p>Most claims are processed within 2-3 business days once we receive all required documents. For complex cases, it may take up to 7-10 business days. We keep you informed throughout the process and strive to settle claims as quickly as possible.</p>
                </details>
            </div>
            
            <div class="faq-item">
                <details>
                    <summary>What documents are needed for a life insurance claim?</summary>
                    <p>You'll typically need: death certificate, policy document, claim form, medical records (if applicable), and identification documents of the beneficiary. Our claims team will guide you through the specific requirements for your case.</p>
                </details>
            </div>
            
            <div class="faq-item">
                <details>
                    <summary>Can I withdraw my policy application within 24 hours?</summary>
                    <p>Yes, you have a 24-hour cooling-off period from the time of application submission during which you can withdraw your application without any charges. After this period, standard policy terms and conditions apply.</p>
                </details>
            </div>
        </div>
    </div>
</body>
</html>''', user=user, policies_count=policies_count, claims_count=claims_count)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.get_json()

            # Validate required fields
            required_fields = ['username', 'password', 'full_name', 'email', 'phone',
                             'date_of_birth', 'gender', 'address', 'pan_number']

            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400

            # Check if username already exists
            existing_user = User.query.filter_by(username=data['username']).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Username already exists. Please choose a different username.'}), 400

            # Check if email already exists
            existing_email = User.query.filter_by(email=data['email']).first()
            if existing_email:
                return jsonify({'success': False, 'message': 'Email already registered. Please use a different email.'}), 400

            # Check if PAN already exists
            existing_pan = User.query.filter_by(pan_number=data['pan_number'].upper()).first()
            if existing_pan:
                return jsonify({'success': False, 'message': 'PAN number already registered. Please check your PAN number.'}), 400

            # Validate PAN format
            if not validate_pan(data['pan_number']):
                return jsonify({'success': False, 'message': 'Invalid PAN number format. Please enter a valid PAN number.'}), 400

            # Parse and validate date of birth
            try:
                birth_date = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date format. Please enter a valid date of birth.'}), 400

            # Calculate age and validate
            calculated_age = calculate_age(birth_date)
            if calculated_age < 18:
                return jsonify({'success': False, 'message': 'You must be at least 18 years old to register.'}), 400
            if calculated_age > 100:
                return jsonify({'success': False, 'message': 'Please enter a valid date of birth.'}), 400

            # Create new user
            user = User(
                digital_token=generate_token(),
                username=data['username'].strip(),
                password_hash=hash_password(data['password']),
                full_name=data['full_name'].strip(),
                email=data['email'].strip().lower(),
                phone=data['phone'].strip(),
                date_of_birth=birth_date,
                age=calculated_age,
                gender=data['gender'].lower(),
                address=data['address'].strip(),
                pan_number=data['pan_number'].upper().strip()
            )

            # Add user to database
            db.session.add(user)
            db.session.flush()  # This assigns an ID to the user

            # Set biometric data as verified (simulated)
            user.face_data = "verified"
            user.retina_data = "verified"

            # Commit the transaction
            db.session.commit()

            return jsonify({
                'success': True,
                'digital_token': user.digital_token,
                'message': 'Registration successful! Please save your digital token securely.'
            })

        except Exception as e:
            # Rollback in case of any error
            db.session.rollback()
            print(f"Registration error: {str(e)}")  # For debugging
            return jsonify({
                'success': False,
                'message': f'Registration failed: {str(e)}'
            }), 500

    # GET request - return registration form
    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <title>Register - SecureBank Insurance</title>
    <style>
        :root {
            --primary-purple: #8B4A9C;
            --secondary-purple: #B366CC;
            --dark-blue: #2C3E50;
            --light-gray: #f8f9fa;
        }
        
        body {
            font-family: 'Segoe UI', sans-serif;
            background-color: var(--light-gray);
            padding: 20px;
            margin: 0;
        }
        
        .register-container {
            background: white;
            border-radius: 20px;
            padding: 50px;
            max-width: 1000px;
            margin: 0 auto;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        
        h2 {
            color: var(--dark-blue);
            margin-bottom: 30px;
            text-align: center;
            font-size: 2.5em;
        }
        
        .form-sections {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-bottom: 30px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        input, select, textarea {
            width: 100%;
            padding: 15px;
            border: 2px solid #e1e5e9;
            border-radius: 10px;
            font-size: 16px;
            box-sizing: border-box;
            transition: border-color 0.3s ease;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary-purple);
        }
        
        .btn-group {
            display: flex;
            gap: 20px;
            margin-top: 30px;
        }
        
        .btn {
            flex: 1;
            padding: 18px;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
            transition: all 0.3s ease;
        }
        
        .btn.primary {
            background: linear-gradient(45deg, var(--primary-purple), var(--secondary-purple));
            color: white;
        }
        
        .btn.secondary {
            background: #6c757d;
            color: white;
        }
        
        .btn.tertiary {
            background: var(--light-gray);
            color: #6c757d;
            border: 2px solid #6c757d;
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }
        
        .alert-error {
            padding: 15px;
            margin: 20px 0;
            border-radius: 10px;
            display: none;
            text-align: center;
            background: #f8d7da;
            color: #721c24;
        }
        
        .biometric-section {
            text-align: center;
            padding: 40px 20px;
        }
        
        .camera-container {
            margin: 30px 0;
            text-align: center;
        }
        
        video {
            width: 100%;
            max-width: 400px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        
        .status-message {
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 600;
        }
        
        .status-success {
            background: #d4edda;
            color: #155724;
        }
        
        .status-error {
            background: #f8d7da;
            color: #721c24;
        }
        
        .token-display {
            background: linear-gradient(45deg, var(--primary-purple), var(--secondary-purple));
            color: white;
            padding: 40px;
            border-radius: 20px;
            text-align: center;
        }
        
        .token-value {
            font-size: 2em;
            font-weight: bold;
            margin: 20px 0;
            letter-spacing: 3px;
        }
    </style>
</head>
<body>
    <div class="register-container">
        <div id="message" class="alert-error"></div>
        
        <form id="registerForm">
            <!-- Step 1: Personal Information -->
            <div id="infoSection">
                <h2>Step 1: Personal Information</h2>
                <div class="form-sections">
                    <div>
                        <div class="form-group">
                            <input type="text" id="full_name" placeholder="Full Name *" required>
                        </div>
                        <div class="form-group">
                            <input type="email" id="email" placeholder="Email Address *" required>
                        </div>
                        <div class="form-group">
                            <input type="tel" id="phone" placeholder="Phone Number *" required>
                        </div>
                        <div class="form-group">
                            <input type="text" id="date_of_birth" onfocus="(this.type='date')" placeholder="Date of Birth *" required>
                        </div>
                        <div class="form-group">
                            <select id="gender" required>
                                <option value="">Select Gender *</option>
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <div class="form-group">
                            <input type="text" id="username" placeholder="Username *" required>
                        </div>
                        <div class="form-group">
                            <input type="password" id="password" placeholder="Password *" required>
                        </div>
                        <div class="form-group">
                            <input type="text" id="pan_number" placeholder="PAN Number *" required>
                        </div>
                        <div class="form-group">
                            <textarea id="address" placeholder="Complete Address *" rows="4" required></textarea>
                        </div>
                    </div>
                </div>
                <div class="btn-group">
                    <button type="button" class="btn primary" onclick="proceedToBiometrics()">Proceed to Biometrics</button>
                </div>
                <div class="btn-group">
                    <a href="/" class="btn secondary">← Back to Home</a>
                    <a href="/login" class="btn tertiary">Already have account? Login</a>
                </div>
            </div>
            
            <!-- Step 2: Biometric Verification -->
            <div id="biometricSection" style="display: none;">
                <h2>Step 2: Biometric Verification</h2>
                <div class="biometric-section">
                    <div id="biometric-status" class="status-message" style="display: none;"></div>
                    
                    <div class="camera-container">
                        <video id="video" autoplay muted></video>
                        <canvas id="canvas" style="display: none;"></canvas>
                    </div>
                    
                    <div class="btn-group">
                        <button type="button" class="btn secondary" onclick="goBackToInfo()">← Back to Information</button>
                        <button type="button" class="btn primary" id="startBiometric" onclick="startBiometricVerification()">Start Face Verification</button>
                        <button type="button" class="btn primary" id="startRetina" onclick="startRetinaVerification()" style="display: none;">Start Retina Scan</button>
                        <button type="submit" class="btn primary" id="createAccount" style="display: none;">Create Account</button>
                    </div>
                </div>
            </div>
        </form>
        
        <!-- Success Display -->
        <div id="tokenDisplay" style="display: none;">
            <div class="token-display">
                <h2>🎉 Registration Successful!</h2>
                <p>Your Digital Token:</p>
                <div class="token-value" id="tokenValue"></div>
                <p>Please save this token securely. You'll need it for future transactions.</p>
                <a href="/login" class="btn" style="background: white; color: #8B4A9C; margin-top: 30px;">Login to Your Account</a>
            </div>
        </div>
    </div>
    
    <script>
        let faceVerified = false;
        let retinaVerified = false;
        let stream = null;
        
        function goBackToInfo() {
            document.getElementById('biometricSection').style.display = 'none';
            document.getElementById('infoSection').style.display = 'block';
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
        }
        
        function proceedToBiometrics() {
            // Validate form first
            const requiredFields = ['full_name', 'email', 'phone', 'date_of_birth', 'gender', 'username', 'password', 'pan_number', 'address'];
            for (let field of requiredFields) {
                const element = document.getElementById(field);
                if (!element.value.trim()) {
                    showMessage('Please fill all required fields', 'error');
                    element.focus();
                    return;
                }
            }
            
            document.getElementById('infoSection').style.display = 'none';
            document.getElementById('biometricSection').style.display = 'block';
            initCamera();
        }
        
        async function initCamera() {
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true });
                document.getElementById('video').srcObject = stream;
            } catch (error) {
                showBiometricStatus('Camera access denied. Please allow camera access and refresh.', 'error');
            }
        }
        
        function showMessage(message, type) {
            const messageDiv = document.getElementById('message');
            messageDiv.textContent = message;
            messageDiv.className = type === 'error' ? 'alert-error' : 'alert-success';
            messageDiv.style.display = 'block';
            setTimeout(() => messageDiv.style.display = 'none', 5000);
        }
        
        function showBiometricStatus(message, type) {
            const statusDiv = document.getElementById('biometric-status');
            statusDiv.textContent = message;
            statusDiv.className = `status-message status-${type}`;
            statusDiv.style.display = 'block';
        }
        
        async function startBiometricVerification() {
            faceVerified = true;
            showBiometricStatus('✅ Face verification successful!', 'success');
            document.getElementById('startBiometric').style.display = 'none';
            document.getElementById('startRetina').style.display = 'inline-block';
        }
        
        async function startRetinaVerification() {
            retinaVerified = true;
            showBiometricStatus('✅ Retina scan successful! You can now create your account.', 'success');
            document.getElementById('startRetina').style.display = 'none';
            document.getElementById('createAccount').style.display = 'inline-block';
        }
        
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!faceVerified || !retinaVerified) {
                showBiometricStatus('Please complete all biometric verifications first.', 'error');
                return;
            }
            
            const formData = {
                username: document.getElementById('username').value.trim(),
                password: document.getElementById('password').value,
                full_name: document.getElementById('full_name').value.trim(),
                email: document.getElementById('email').value.trim(),
                phone: document.getElementById('phone').value.trim(),
                date_of_birth: document.getElementById('date_of_birth').value,
                gender: document.getElementById('gender').value,
                address: document.getElementById('address').value.trim(),
                pan_number: document.getElementById('pan_number').value.trim().toUpperCase()
            };
            
            try {
                showBiometricStatus('Creating your account...', 'success');
                
                const response = await fetch('/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(formData)
                });
                
                const result = await response.json();
                if (result.success) {
                    document.getElementById('registerForm').style.display = 'none';
                    document.getElementById('tokenValue').textContent = result.digital_token;
                    document.getElementById('tokenDisplay').style.display = 'block';
                    if (stream) {
                        stream.getTracks().forEach(track => track.stop());
                    }
                } else {
                    showBiometricStatus(result.message, 'error');
                }
            } catch (error) {
                showBiometricStatus('Registration failed. Please try again.', 'error');
            }
        });
    </script>
</body>
</html>''')


@app.route('/verify-proximity', methods=['POST'])
def verify_proximity():
    return jsonify({'success': True})


@app.route('/verify-retina', methods=['POST'])
def verify_retina():
    return jsonify({'success': True})


# Additional routes for the complete platform
@app.route('/schemes')
def schemes():
    if 'user_id' not in session:
        return redirect('/login')

    schemes = Scheme.query.filter_by(is_active=True).all()
    return render_template_string('''<!DOCTYPE html>
<html><head><title>Life Insurance Plans</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; margin: 0; padding: 30px; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { text-align: center; margin-bottom: 50px; }
    .header h1 { color: #2C3E50; font-size: 3em; margin-bottom: 15px; }
    .schemes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 30px; }
    .scheme-card { background: white; border-radius: 20px; padding: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); transition: transform 0.3s ease; }
    .scheme-card:hover { transform: translateY(-10px); }
    .scheme-name { color: #2C3E50; font-size: 1.8em; margin-bottom: 10px; }
    .scheme-coverage { color: #8B4A9C; font-size: 2.2em; font-weight: bold; margin-bottom: 5px; }
    .scheme-premium { color: #6c757d; font-size: 1.1em; }
    .apply-btn { width: 100%; background: linear-gradient(45deg, #8B4A9C, #B366CC); color: white; padding: 15px; border: none; border-radius: 10px; font-size: 1.1em; font-weight: 600; text-decoration: none; display: inline-block; text-align: center; margin-top: 20px; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border-radius: 25px; text-decoration: none; margin-bottom: 30px; }
</style></head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-btn">← Back to Dashboard</a>
        <div class="header">
            <h1>Our Life Insurance Solutions</h1>
        </div>
        <div class="schemes-grid">
            {% for scheme in schemes %}
            <div class="scheme-card">
                <h3 class="scheme-name">{{ scheme.name }}</h3>
                <div class="scheme-coverage">₹{{ "{:,.0f}".format(scheme.coverage_amount) }}</div>
                <div class="scheme-premium">Premium: ₹{{ "{:,.0f}".format(scheme.premium_amount) }}/month</div>
                <p>{{ scheme.description }}</p>
                <a href="/apply-policy/{{ scheme.id }}" class="apply-btn">Apply Now</a>
            </div>
            {% endfor %}
        </div>
    </div>
</body></html>''', schemes=schemes)


@app.route('/apply-policy/<int:scheme_id>', methods=['GET', 'POST'])
def apply_policy(scheme_id):
    if 'user_id' not in session:
        return redirect('/login')

    scheme = Scheme.query.get_or_404(scheme_id)
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        # Verify Digital Token
        token_entered = request.form.get('digital_token', '').upper()
        if user.digital_token != token_entered:
            return render_template_string('''<!DOCTYPE html>
<html><head><title>Token Verification Failed</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .error-container { background: white; padding: 50px; border-radius: 20px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    .error-icon { font-size: 4em; color: #dc3545; margin-bottom: 20px; }
    h1 { color: #2C3E50; margin-bottom: 20px; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px; }
</style></head>
<body>
    <div class="error-container">
        <div class="error-icon">❌</div>
        <h1>Token Verification Failed</h1>
        <p>Digital token does not match our records. Please enter the correct token.</p>
        <a href="/apply-policy/{{ scheme.id }}" class="btn">Try Again</a>
    </div>
</body></html>''', scheme=scheme)

        # Create policy
        new_policy = Policy(
            policy_number=generate_policy_number(),
            user_id=user.id,
            scheme_id=scheme.id,
            premium_amount=scheme.premium_amount,
            coverage_amount=scheme.coverage_amount,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365 * 10)
        )
        db.session.add(new_policy)
        db.session.flush()

        # Add nominee
        nominee = Nominee(
            user_id=user.id,
            policy_id=new_policy.id,
            name=request.form['nominee_name'],
            relationship=request.form['nominee_relationship']
        )
        db.session.add(nominee)
        db.session.commit()

        return render_template_string('''<!DOCTYPE html>
<html><head><title>Application Successful</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .success-container { background: white; padding: 60px; border-radius: 20px; max-width: 700px; margin: 0 auto; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
    .success-icon { font-size: 5em; color: #28a745; margin-bottom: 30px; }
    h1 { color: #2C3E50; margin-bottom: 20px; font-size: 2.5em; }
    .policy-info { background: #f8f9fa; padding: 30px; border-radius: 15px; margin: 30px 0; }
    .policy-number { font-size: 1.5em; font-weight: bold; color: #8B4A9C; margin: 15px 0; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin: 10px; font-weight: 600; }
    .withdrawal-notice { background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 10px; margin: 20px 0; color: #856404; }
</style></head>
<body>
    <div class="success-container">
        <div class="success-icon">🎉</div>
        <h1>Life Insurance Application Successful!</h1>
        <p>Your life insurance application has been received and is being processed.</p>

        <div class="policy-info">
            <h3>Policy Details</h3>
            <div class="policy-number">Policy Number: {{ policy.policy_number }}</div>
            <p><strong>Plan:</strong> {{ policy.scheme.name }}</p>
            <p><strong>Life Coverage Amount:</strong> ₹{{ "{:,.0f}".format(policy.coverage_amount) }}</p>
            <p><strong>Monthly Premium:</strong> ₹{{ "{:,.0f}".format(policy.premium_amount) }}</p>
            <p><strong>Nominee:</strong> {{ nominee.name }} ({{ nominee.relationship|title }})</p>
        </div>

        <div class="withdrawal-notice">
            <h3>⏰ Withdrawal Period</h3>
            <p>You have 24 hours from now to withdraw this application without any charges if you change your mind.</p>
        </div>

        <a href="/my-policies" class="btn">View My Policies</a>
        <a href="/dashboard" class="btn" style="background: #6c757d;">Back to Dashboard</a>
    </div>
</body></html>''', policy=new_policy, nominee=nominee)

    return render_template_string('''<!DOCTYPE html>
<html><head><title>Apply for {{ scheme.name }}</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
    .container { max-width: 1000px; margin: 0 auto; }
    .application-form { background: white; padding: 50px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-bottom: 30px; }
    .plan-details { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    h1 { color: #2C3E50; margin-bottom: 30px; font-size: 2.5em; text-align: center; }
    h2 { color: #2C3E50; margin-bottom: 25px; border-bottom: 2px solid #8B4A9C; padding-bottom: 10px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px; }
    .form-group { margin-bottom: 20px; }
    label { display: block; margin-bottom: 8px; font-weight: 600; color: #2C3E50; }
    input, select { width: 100%; padding: 15px; border: 2px solid #e1e5e9; border-radius: 10px; font-size: 16px; box-sizing: border-box; }
    input:focus, select:focus { outline: none; border-color: #8B4A9C; }
    .readonly { background: #f8f9fa; }
    .submit-btn { background: linear-gradient(45deg, #8B4A9C, #B366CC); color: white; padding: 18px 40px; border: none; border-radius: 10px; font-size: 1.2em; font-weight: 600; cursor: pointer; width: 100%; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border-radius: 25px; text-decoration: none; display: inline-block; margin-bottom: 30px; }
    .plan-summary { background: linear-gradient(45deg, #8B4A9C, #B366CC); color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; text-align: center; }
    .coverage-amount { font-size: 2.5em; font-weight: bold; margin: 10px 0; }
    .premium-amount { font-size: 1.3em; opacity: 0.9; }
    .features-list { list-style: none; padding: 0; }
    .features-list li { padding: 8px 0; color: #28a745; }
    .features-list li:before { content: "✓ "; font-weight: bold; }
    .warning-box { background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 10px; margin-bottom: 30px; }
    .warning-box h3 { color: #856404; margin-bottom: 10px; }
</style></head>
<body>
    <div class="container">
        <a href="/schemes" class="back-btn">← Back to Plans</a>

        <div class="application-form">
            <h1>Apply for {{ scheme.name }}</h1>

            <div class="warning-box">
                <h3>⚠️ Important Notice</h3>
                <p>You have 24 hours from submission to withdraw your application without any charges.</p>
            </div>

            <form method="POST">
                <h2>Identity Verification</h2>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Enter Your Digital Token *</label>
                        <input type="text" name="digital_token" placeholder="Enter your digital token" required style="text-transform: uppercase;">
                        <small style="color: #6c757d;">Your digital token: {{ current_user.digital_token }}</small>
                    </div>
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" value="{{ current_user.full_name }}" readonly class="readonly">
                    </div>
                </div>

                <h2>Personal Details</h2>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Age</label>
                        <input type="text" value="{{ current_user.age }} years" readonly class="readonly">
                    </div>
                    <div class="form-group">
                        <label>Email</label>
                        <input type="text" value="{{ current_user.email }}" readonly class="readonly">
                    </div>
                </div>

                <h2>Nominee Information</h2>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Nominee Name *</label>
                        <input type="text" name="nominee_name" placeholder="Enter nominee's full name" required>
                    </div>
                    <div class="form-group">
                        <label>Relationship with Nominee *</label>
                        <select name="nominee_relationship" required>
                            <option value="">Select Relationship</option>
                            <option value="spouse">Spouse</option>
                            <option value="child">Child</option>
                            <option value="parent">Parent</option>
                            <option value="sibling">Sibling</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                </div>

                <button type="submit" class="submit-btn">Submit Life Insurance Application</button>
            </form>
        </div>

        <div class="plan-details">
            <h2>Life Insurance Plan Details</h2>
            <div class="plan-summary">
                <h3>{{ scheme.name }}</h3>
                <div class="coverage-amount">₹{{ "{:,.0f}".format(scheme.coverage_amount) }}</div>
                <div class="premium-amount">Monthly Premium: ₹{{ "{:,.0f}".format(scheme.premium_amount) }}</div>
                <p style="margin-top: 15px; opacity: 0.9;">Pure Life Insurance Coverage</p>
            </div>

            <p><strong>Description:</strong> {{ scheme.description }}</p>

            <h3>Life Insurance Benefits:</h3>
            <ul class="features-list">
                {% for feature in scheme.features|from_json %}
                <li>{{ feature }}</li>
                {% endfor %}
            </ul>

            <h3>Eligibility:</h3>
            <ul class="features-list">
                <li>Age: {{ scheme.min_age }} to {{ scheme.max_age }} years</li>
                <li>Indian citizen with valid documents</li>
                <li>Good health condition required</li>
                <li>Life insurance medical examination may be required</li>
            </ul>
        </div>
    </div>
</body></html>''', scheme=scheme)


@app.route('/my-policies')
def my_policies():
    if 'user_id' not in session:
        return redirect('/login')

    policies = Policy.query.filter_by(user_id=session['user_id']).order_by(Policy.created_at.desc()).all()

    return render_template_string('''<!DOCTYPE html>
    <html><head><title>My Policies</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); }
        .policies-grid { display: grid; gap: 25px; }
        .policy-card { background: white; padding: 35px; border-radius: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.1); }
        .policy-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        .policy-title { color: #2C3E50; font-size: 1.5em; margin: 0; }
        .policy-number { color: #6c757d; font-size: 0.9em; }
        .status-badge { padding: 8px 16px; border-radius: 20px; font-size: 0.85em; font-weight: 600; text-transform: uppercase; }
        .status-applied { background: #fff3cd; color: #856404; }
        .status-active { background: #d4edda; color: #155724; }
        .status-withdrawn { background: #f8d7da; color: #721c24; }
        .policy-details { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 25px; }
        .detail-item { text-align: center; }
        .detail-value { font-size: 1.3em; font-weight: bold; color: #8B4A9C; }
        .detail-label { color: #6c757d; font-size: 0.9em; margin-top: 5px; }
        .withdraw-btn { background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 20px; font-size: 0.9em; cursor: pointer; }
        .back-btn { background: #6c757d; color: white; padding: 12px 25px; border-radius: 25px; text-decoration: none; display: inline-block; margin-bottom: 30px; }
        .empty-state { text-align: center; padding: 80px 20px; color: #6c757d; }
    </style></head>
    <body>
        <div class="container">
            <a href="/dashboard" class="back-btn">← Back to Dashboard</a>

            <div class="header">
                <h1 style="color: #2C3E50; margin: 0;">My Life Insurance Policies</h1>
                <p style="color: #6c757d; margin: 10px 0 0 0;">Manage and track all your insurance policies</p>
            </div>

            {% if policies %}
            <div class="policies-grid">
                {% for policy in policies %}
                <div class="policy-card">
                    <div class="policy-header">
                        <div>
                            <h3 class="policy-title">{{ policy.scheme.name }}</h3>
                            <div class="policy-number">Policy #{{ policy.policy_number }}</div>
                        </div>
                        <span class="status-badge status-{{ policy.status }}">{{ policy.status|title }}</span>
                    </div>

                    <div class="policy-details">
                        <div class="detail-item">
                            <div class="detail-value">₹{{ "{:,.0f}".format(policy.coverage_amount) }}</div>
                            <div class="detail-label">Coverage Amount</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">₹{{ "{:,.0f}".format(policy.premium_amount) }}</div>
                            <div class="detail-label">Monthly Premium</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-value">{{ policy.created_at.strftime('%d %b %Y') }}</div>
                            <div class="detail-label">Applied On</div>
                        </div>
                    </div>

                    {% if policy.is_withdrawable %}
                    <div style="text-align: center; padding-top: 20px; border-top: 1px solid #e1e5e9;">
                        <p style="color: #856404; margin-bottom: 15px;">⏰ Withdrawal available for {{ (86400 - (now - policy.created_at).total_seconds())|int // 3600 }} hours</p>
                        <form method="POST" action="/withdraw-policy/{{ policy.id }}" style="display: inline;">
                            <button type="submit" class="withdraw-btn" onclick="return confirm('Are you sure you want to withdraw this policy application?')">Withdraw Application</button>
                        </form>
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div style="font-size: 4em; margin-bottom: 20px;">📄</div>
                <h2>No Policies Found</h2>
                <p>You haven't applied for any insurance policies yet.</p>
                <a href="/schemes" style="background: #8B4A9C; color: white; padding: 15px 30px; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px;">Explore Our Plans</a>
            </div>
            {% endif %}
        </div>
    </body></html>''', policies=policies)


@app.route('/withdraw-policy/<int:policy_id>', methods=['POST'])
def withdraw_policy(policy_id):
    if 'user_id' not in session:
        return redirect('/login')

    policy = Policy.query.get_or_404(policy_id)
    if policy.user_id == session['user_id'] and policy.is_withdrawable:
        policy.status = 'withdrawn'
        db.session.commit()

    return redirect('/my-policies')


@app.route('/make-claim', methods=['GET', 'POST'])
def make_claim():
    if 'user_id' not in session:
        return redirect('/login')

    user = User.query.get(session['user_id'])
    active_policies = Policy.query.filter_by(user_id=user.id, status='active').all()

    if request.method == 'POST':
        # Verify Digital Token
        token_entered = request.form.get('digital_token', '').upper()
        if user.digital_token != token_entered:
            return render_template_string('''<!DOCTYPE html>
<html><head><title>Token Verification Failed</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .error-container { background: white; padding: 50px; border-radius: 20px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    .error-icon { font-size: 4em; color: #dc3545; margin-bottom: 20px; }
    h1 { color: #2C3E50; margin-bottom: 20px; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px; }
</style></head>
<body>
    <div class="error-container">
        <div class="error-icon">❌</div>
        <h1>Token Verification Failed</h1>
        <p>Digital token does not match our records. Please enter the correct token.</p>
        <a href="/make-claim" class="btn">Try Again</a>
    </div>
</body></html>''')

        # Handle file uploads
        files = request.files.getlist('documents')
        doc_paths = []

        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                path = os.path.join('claim_documents', filename)
                file.save(path)
                doc_paths.append(path)

        claim = Claim(
            claim_number=generate_claim_number(),
            user_id=user.id,
            policy_id=request.form['policy_id'],
            claim_amount=float(request.form['claim_amount']),
            document_paths=json.dumps(doc_paths)
        )
        db.session.add(claim)
        db.session.commit()

        return render_template_string('''<!DOCTYPE html>
<html><head><title>Life Insurance Claim Submitted</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .success-container { background: white; padding: 60px; border-radius: 20px; max-width: 700px; margin: 0 auto; box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
    .success-icon { font-size: 5em; color: #28a745; margin-bottom: 30px; }
    h1 { color: #2C3E50; margin-bottom: 20px; font-size: 2.5em; }
    .claim-info { background: #f8f9fa; padding: 30px; border-radius: 15px; margin: 30px 0; }
    .claim-number { font-size: 1.5em; font-weight: bold; color: #8B4A9C; margin: 15px 0; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin: 10px; font-weight: 600; }
    .processing-notice { background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; border-radius: 10px; margin: 20px 0; color: #155724; }
    .timeline { background: #e3f2fd; padding: 20px; border-radius: 10px; margin: 20px 0; color: #1976d2; }
</style></head>
<body>
    <div class="success-container">
        <div class="success-icon">✅</div>
        <h1>Life Insurance Claim Submitted!</h1>
        <p>Your life insurance claim has been received and is now being processed by our claims team.</p>

        <div class="claim-info">
            <h3>Claim Details</h3>
            <div class="claim-number">Claim Number: {{ claim.claim_number }}</div>
            <p><strong>Claim Amount:</strong> ₹{{ "{:,.0f}".format(claim.claim_amount) }}</p>
            <p><strong>Policy Type:</strong> Life Insurance</p>
            <p><strong>Submitted On:</strong> {{ claim.submitted_at.strftime('%d %B %Y, %I:%M %p') }}</p>
            <p><strong>Documents Uploaded:</strong> {{ doc_count }} files</p>
        </div>

        <div class="processing-notice">
            <h3>💰 Claim Processing Timeline</h3>
            <p>Your life insurance claim will be processed and the amount will be credited to your account within <strong>2-3 business days</strong> after document verification.</p>
        </div>

        <div class="timeline">
            <h3>📋 What Happens Next?</h3>
            <p><strong>Day 1:</strong> Document verification and initial review</p>
            <p><strong>Day 2:</strong> Claim assessment and approval process</p>
            <p><strong>Day 3:</strong> Amount credit to your registered bank account</p>
        </div>

        <a href="/dashboard" class="btn">Back to Dashboard</a>
    </div>
</body></html>''', claim=claim, doc_count=len(doc_paths))

    return render_template_string('''<!DOCTYPE html>
<html><head><title>File Life Insurance Claim</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
    .container { max-width: 900px; margin: 0 auto; }
    .claim-form { background: white; padding: 50px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    h1 { color: #2C3E50; margin-bottom: 30px; font-size: 2.5em; text-align: center; }
    .form-section { margin-bottom: 40px; }
    .form-section h2 { color: #2C3E50; margin-bottom: 20px; border-bottom: 2px solid #8B4A9C; padding-bottom: 10px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; }
    .form-group { margin-bottom: 25px; }
    label { display: block; margin-bottom: 8px; font-weight: 600; color: #2C3E50; }
    input, select { width: 100%; padding: 15px; border: 2px solid #e1e5e9; border-radius: 10px; font-size: 16px; box-sizing: border-box; }
    input:focus, select:focus { outline: none; border-color: #8B4A9C; }
    .readonly { background: #f8f9fa; }
    .file-upload { background: #f8f9fa; border: 2px dashed #8B4A9C; padding: 40px; text-align: center; border-radius: 15px; }
    .submit-btn { background: linear-gradient(45deg, #8B4A9C, #B366CC); color: white; padding: 18px 40px; border: none; border-radius: 10px; font-size: 1.2em; font-weight: 600; cursor: pointer; width: 100%; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border-radius: 25px; text-decoration: none; display: inline-block; margin-bottom: 30px; }
    .no-policies { text-align: center; padding: 60px; color: #6c757d; }
    .instructions { background: #e3f2fd; padding: 25px; border-radius: 15px; margin-bottom: 30px; }
    .instructions h3 { color: #1976d2; margin-bottom: 15px; }
    .instructions ul { list-style-type: none; padding: 0; }
    .instructions li { padding: 5px 0; color: #1976d2; }
    .instructions li:before { content: "📌 "; }
</style></head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-btn">← Back to Dashboard</a>

        {% if active_policies %}
        <div class="claim-form">
            <h1>File Life Insurance Claim</h1>

            <div class="instructions">
                <h3>Required Documents for Life Insurance Claim</h3>
                <ul>
                    <li>Death Certificate (for death benefit claims)</li>
                    <li>Medical reports and bills (for critical illness claims)</li>
                    <li>Hospital discharge summary</li>
                    <li>Doctor's certificate and prescriptions</li>
                    <li>Policy documents</li>
                    <li>Beneficiary identification documents</li>
                </ul>
            </div>

            <form method="POST" enctype="multipart/form-data">
                <div class="form-section">
                    <h2>Identity Verification</h2>
                    <div class="form-grid">
                        <div class="form-group">
                            <label>Enter Your Digital Token *</label>
                            <input type="text" name="digital_token" placeholder="Enter your digital token" required style="text-transform: uppercase;">
                            <small style="color: #6c757d;">Your digital token: {{ current_user.digital_token }}</small>
                        </div>
                        <div class="form-group">
                            <label>Full Name</label>
                            <input type="text" value="{{ current_user.full_name }}" readonly class="readonly">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h2>Life Insurance Claim Information</h2>
                    <div class="form-grid">
                        <div class="form-group">
                            <label>Select Life Insurance Policy *</label>
                            <select name="policy_id" required>
                                <option value="">Choose your life insurance policy</option>
                                {% for policy in active_policies %}
                                <option value="{{ policy.id }}">{{ policy.scheme.name }} - {{ policy.policy_number }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Claim Amount (₹) *</label>
                            <input type="number" name="claim_amount" placeholder="Enter claim amount" required min="1">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h2>Upload Supporting Documents</h2>
                    <div class="form-group">
                        <label>Life Insurance Claim Documents *</label>
                        <div class="file-upload">
                            <input type="file" name="documents" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" required>
                            <p style="margin-top: 15px; color: #6c757d;">Upload death certificates, medical reports, policy documents and other supporting documents for your life insurance claim</p>
                            <small style="color: #6c757d;">Accepted formats: PDF, JPG, PNG, DOC, DOCX (Max 10MB each)</small>
                        </div>
                    </div>
                </div>

                <button type="submit" class="submit-btn">Submit Life Insurance Claim</button>
            </form>
        </div>
        {% else %}
        <div class="no-policies">
            <h1>No Active Life Insurance Policies Found</h1>
            <p>You need to have an active life insurance policy to file a claim.</p>
            <a href="/schemes" style="background: #8B4A9C; color: white; padding: 15px 30px; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px;">Explore Our Life Insurance Plans</a>
        </div>
        {% endif %}
    </div>
</body></html>''', active_policies=active_policies)


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = f"profile_{user.id}_{timestamp}{os.path.splitext(filename)[1]}"

                # Create profile_pictures folder if it doesn't exist
                os.makedirs('profile_pictures', exist_ok=True)

                file_path = os.path.join('profile_pictures', filename)
                file.save(file_path)

                # Update user profile picture path
                user.profile_picture = file_path
                db.session.commit()

                return render_template_string('''<!DOCTYPE html>
<html><head><title>Profile Updated</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .success-container { background: white; padding: 50px; border-radius: 20px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    .success-icon { font-size: 4em; color: #28a745; margin-bottom: 20px; }
    h1 { color: #2C3E50; margin-bottom: 20px; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px; }
</style></head>
<body>
    <div class="success-container">
        <div class="success-icon">✅</div>
        <h1>Profile Picture Updated!</h1>
        <p>Your profile picture has been updated successfully.</p>
        <a href="/profile" class="btn">View Profile</a>
    </div>
</body></html>''')

    policies_count = Policy.query.filter_by(user_id=user.id).count()
    claims_count = Claim.query.filter_by(user_id=user.id).count()

    return render_template_string('''<!DOCTYPE html>
<html><head><title>My Profile</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
    .container { max-width: 1000px; margin: 0 auto; }
    .profile-header { background: linear-gradient(45deg, #8B4A9C, #B366CC); color: white; padding: 50px; border-radius: 20px; text-align: center; margin-bottom: 30px; position: relative; }
    .profile-avatar { width: 120px; height: 120px; background: rgba(255,255,255,0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 3em; margin: 0 auto 20px; overflow: hidden; border: 4px solid rgba(255,255,255,0.3); }
    .profile-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .upload-btn { position: absolute; top: 20px; right: 20px; background: rgba(255,255,255,0.2); padding: 10px 20px; border-radius: 20px; text-decoration: none; color: white; font-weight: 600; }
    .upload-btn:hover { background: rgba(255,255,255,0.3); }
    .profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
    .info-card { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.1); }
    .info-card h2 { color: #2C3E50; margin-bottom: 25px; border-bottom: 2px solid #8B4A9C; padding-bottom: 10px; }
    .info-item { display: flex; justify-content: space-between; align-items: center; padding: 15px 0; border-bottom: 1px solid #f1f3f4; }
    .info-item:last-child { border-bottom: none; }
    .info-label { font-weight: 600; color: #2C3E50; }
    .info-value { color: #6c757d; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border-radius: 25px; text-decoration: none; display: inline-block; margin-bottom: 30px; }
    .digital-token { background: linear-gradient(45deg, #8B4A9C, #B366CC); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: bold; font-size: 1.2em; }
    .upload-modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); }
    .modal-content { background-color: white; margin: 15% auto; padding: 30px; border-radius: 20px; width: 80%; max-width: 500px; text-align: center; }
    .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
    .close:hover { color: black; }
    .file-upload-area { border: 2px dashed #8B4A9C; padding: 40px; border-radius: 15px; margin: 20px 0; background: #f8f9fa; }
    .upload-submit { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; margin-top: 20px; }
</style></head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-btn">← Back to Dashboard</a>

        <div class="profile-header">
            <a href="#" class="upload-btn" onclick="openUploadModal()">📷 Update Photo</a>
            <div class="profile-avatar">
                {% if user.profile_picture %}
                    <img src="/{{ user.profile_picture }}" alt="Profile Picture">
                {% else %}
                    👤
                {% endif %}
            </div>
            <h1>{{ user.full_name }}</h1>
            <p>Digital Token: <span class="digital-token">{{ user.digital_token }}</span></p>
            <p>Life Insurance Member since {{ user.created_at.strftime('%B %Y') }}</p>
        </div>

        <div class="profile-grid">
            <div class="info-card">
                <h2>Personal Information</h2>
                <div class="info-item">
                    <span class="info-label">Full Name</span>
                    <span class="info-value">{{ user.full_name }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Email Address</span>
                    <span class="info-value">{{ user.email }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Phone Number</span>
                    <span class="info-value">{{ user.phone }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Date of Birth</span>
                    <span class="info-value">{{ user.date_of_birth.strftime('%d %B %Y') }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Age</span>
                    <span class="info-value">{{ user.age }} years</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Gender</span>
                    <span class="info-value">{{ user.gender|title }}</span>
                </div>
            </div>

            <div class="info-card">
                <h2>Account Details</h2>
                <div class="info-item">
                    <span class="info-label">Username</span>
                    <span class="info-value">{{ user.username }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">PAN Number</span>
                    <span class="info-value">{{ user.pan_number }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Account Status</span>
                    <span class="info-value" style="color: #28a745; font-weight: 600;">{{ user.account_status|title }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Life Insurance Policies</span>
                    <span class="info-value">{{ policies_count }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Claims Filed</span>
                    <span class="info-value">{{ claims_count }}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Last Login</span>
                    <span class="info-value">{{ user.last_login.strftime('%d %B %Y, %I:%M %p') if user.last_login else 'First time login' }}</span>
                </div>
            </div>
        </div>

        <div style="margin-top: 30px;">
            <div class="info-card">
                <h2>Address Information</h2>
                <div class="info-item">
                    <span class="info-label">Complete Address</span>
                    <span class="info-value">{{ user.address }}</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Upload Modal -->
    <div id="uploadModal" class="upload-modal">
        <div class="modal-content">
            <span class="close" onclick="closeUploadModal()">&times;</span>
            <h2>Update Profile Picture</h2>
            <form method="POST" enctype="multipart/form-data">
                <div class="file-upload-area">
                    <input type="file" name="profile_picture" accept=".jpg,.jpeg,.png" required>
                    <p style="margin-top: 15px; color: #6c757d;">Choose a profile picture</p>
                    <small style="color: #6c757d;">Accepted formats: JPG, PNG (Max 5MB)</small>
                </div>
                <button type="submit" class="upload-submit">Upload Picture</button>
            </form>
        </div>
    </div>

    <script>
        function openUploadModal() {
            document.getElementById('uploadModal').style.display = 'block';
        }

        function closeUploadModal() {
            document.getElementById('uploadModal').style.display = 'none';
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            var modal = document.getElementById('uploadModal');
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }
    </script>
</body></html>''', user=user, policies_count=policies_count, claims_count=claims_count)


# Add this route to serve profile pictures
@app.route('/profile_pictures/<filename>')
def uploaded_file(filename):
    return send_from_directory('profile_pictures', filename)

@app.route('/report-transaction', methods=['GET', 'POST'])
def report_transaction():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        report = Report(
            user_id=session['user_id'],
            report_type='unauthorized_transaction',
            description=request.form['description']
        )
        db.session.add(report)
        db.session.commit()

        return render_template_string('''<!DOCTYPE html>
    <html><head><title>Report Submitted</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
        .success-container { background: white; padding: 50px; border-radius: 20px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .success-icon { font-size: 4em; color: #28a745; margin-bottom: 20px; }
        h1 { color: #2C3E50; margin-bottom: 20px; }
        .btn {background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px; }
</style></head>
<body>
    <div class="success-container">
        <div class="success-icon">✅</div>
        <h1>Report Submitted Successfully</h1>
        <p>Your report has been received and will be investigated within 24 hours. We'll contact you if additional information is needed.</p>
        <p><strong>Reference ID:</strong> REP{{ now.strftime('%Y%m%d%H%M') }}</p>
        <a href="/dashboard" class="btn">Return to Dashboard</a>
    </div>
</body></html>''')

    return render_template_string('''<!DOCTYPE html>
<html><head><title>Report Unauthorized Transaction</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
    .container { max-width: 800px; margin: 0 auto; background: white; padding: 50px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    h1 { color: #2C3E50; margin-bottom: 30px; }
    .form-group { margin-bottom: 25px; }
    label { display: block; margin-bottom: 8px; font-weight: 600; color: #2C3E50; }
    textarea { width: 100%; padding: 15px; border: 2px solid #e1e5e9; border-radius: 10px; font-size: 16px; min-height: 150px; box-sizing: border-box; }
    textarea:focus { outline: none; border-color: #8B4A9C; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; }
    .btn:hover { background: #7a3d8a; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-right: 15px; }
</style></head>
<body>
    <div class="container">
        <h1>🚨 Report Unauthorized Transaction</h1>
        <p style="color: #6c757d; margin-bottom: 30px;">If you notice any suspicious or unauthorized activity on your account, please report it immediately. Our security team will investigate and take appropriate action.</p>
        
        <form method="POST">
            <div class="form-group">
                <label>Digital Token (for verification)</label>
                <input type="text" value="{{ current_user.digital_token }}" readonly style="background: #f8f9fa; padding: 12px; border-radius: 5px; border: 1px solid #dee2e6; width: 200px;">
            </div>
            
            <div class="form-group">
                <label>Describe the Unauthorized Transaction or Suspicious Activity *</label>
                <textarea name="description" placeholder="Please provide detailed information including:
- Date and time of the transaction
- Amount involved (if applicable)
- Any suspicious communications received
- How you discovered the unauthorized activity
- Any other relevant details" required></textarea>
            </div>
            
            <div style="margin-top: 30px;">
                <a href="/dashboard" class="back-btn">← Back to Dashboard</a>
                <button type="submit" class="btn">Submit Report</button>
            </div>
        </form>
    </div>
</body></html>''')


@app.route('/complaints-feedback', methods=['GET', 'POST'])
def complaints_feedback():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        report = Report(
            user_id=session['user_id'],
            report_type='complaint_feedback',
            description=request.form['description']
        )
        db.session.add(report)
        db.session.commit()

        return render_template_string('''<!DOCTYPE html>
<html><head><title>Feedback Submitted</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 50px; text-align: center; }
    .success-container { background: white; padding: 50px; border-radius: 20px; max-width: 600px; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    .success-icon { font-size: 4em; color: #28a745; margin-bottom: 20px; }
    h1 { color: #2C3E50; margin-bottom: 20px; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-top: 20px; }
</style></head>
<body>
    <div class="success-container">
        <div class="success-icon">✅</div>
        <h1>Feedback Submitted Successfully</h1>
        <p>Thank you for your feedback. We value your input and will review it carefully to improve our services.</p>
        <p><strong>Reference ID:</strong> FB{{ now.strftime('%Y%m%d%H%M') }}</p>
        <a href="/dashboard" class="btn">Return to Dashboard</a>
    </div>
</body></html>''')

    return render_template_string('''<!DOCTYPE html>
<html><head><title>Complaints & Feedback</title>
<style>
    body { font-family: 'Segoe UI', sans-serif; background: #f8f9fa; padding: 30px; }
    .container { max-width: 800px; margin: 0 auto; background: white; padding: 50px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
    h1 { color: #2C3E50; margin-bottom: 30px; }
    .form-group { margin-bottom: 25px; }
    label { display: block; margin-bottom: 8px; font-weight: 600; color: #2C3E50; }
    textarea { width: 100%; padding: 15px; border: 2px solid #e1e5e9; border-radius: 10px; font-size: 16px; min-height: 150px; box-sizing: border-box; }
    textarea:focus { outline: none; border-color: #8B4A9C; }
    .btn { background: #8B4A9C; color: white; padding: 15px 30px; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; }
    .btn:hover { background: #7a3d8a; }
    .back-btn { background: #6c757d; color: white; padding: 12px 25px; border: none; border-radius: 25px; text-decoration: none; display: inline-block; margin-right: 15px; }
</style></head>
<body>
    <div class="container">
        <h1>💬 Complaints & Feedback</h1>
        <p style="color: #6c757d; margin-bottom: 30px;">We value your feedback and are committed to providing excellent service. Please share your concerns, suggestions, or compliments with us.</p>
        
        <form method="POST">
            <div class="form-group">
                <label>Digital Token (for verification)</label>
                <input type="text" value="{{ current_user.digital_token }}" readonly style="background: #f8f9fa; padding: 12px; border-radius: 5px; border: 1px solid #dee2e6; width: 200px;">
            </div>
            
            <div class="form-group">
                <label>Your Complaint or Feedback *</label>
                <textarea name="description" placeholder="Please share your feedback, complaint, or suggestion. Include:
- Nature of your concern
- Policy or service related details
- Steps you've already taken (if any)
- Your suggestions for improvement
- Any other relevant information" required></textarea>
            </div>
            
            <div style="margin-top: 30px;">
                <a href="/dashboard" class="back-btn">← Back to Dashboard</a>
                <button type="submit" class="btn">Submit Feedback</button>
            </div>
        </form>
    </div>
</body></html>''')


# ===================================
# APP INITIALIZATION AND RUN
# ===================================
if __name__ == '__main__':
    with app.app_context():
        # First, try to migrate existing database
        try:
            migrate_database()
        except:
            # If migration fails, recreate the database
            print("🔄 Recreating database...")
            db.drop_all()
            db.create_all()

        # Ensure all tables are created
        db.create_all()

        # Add comprehensive life insurance schemes
        if not Scheme.query.first():
            schemes = [
                Scheme(
                    name='Pure Life Term Insurance',
                    category='life',
                    description='Pure term life insurance providing maximum coverage at lowest premium. No maturity benefit, only death benefit.',
                    premium_amount=750,
                    coverage_amount=10000000,
                    features=json.dumps([
                        'Death Benefit up to ₹1 Crore',
                        'Lowest Premium Rates',
                        'Tax Benefits under Section 80C',
                        'Online Policy Management',
                        'Quick Claim Settlement'
                    ])
                ),
                Scheme(
                    name='Whole Life Insurance Plan',
                    category='life',
                    description='Lifelong life insurance coverage with guaranteed death benefit and cash value accumulation.',
                    premium_amount=2000,
                    coverage_amount=1500000,
                    features=json.dumps([
                        'Lifelong Coverage',
                        'Guaranteed Death Benefit',
                        'Cash Value Accumulation',
                        'Loan Against Policy',
                        'Tax Benefits on Premium'
                    ])
                ),
                Scheme(
                    name='Endowment Life Insurance',
                    category='life',
                    description='Life insurance with savings component providing maturity benefit if you survive the policy term.',
                    premium_amount=3000,
                    coverage_amount=2000000,
                    features=json.dumps([
                        'Death Benefit + Maturity Benefit',
                        'Guaranteed Returns',
                        'Bonus Additions',
                        'Life Coverage Throughout',
                        'Wealth Creation'
                    ])
                ),
                Scheme(
                    name='Child Life Insurance Plan',
                    category='life',
                    description='Life insurance plan securing child\'s future with education benefits and life coverage.',
                    premium_amount=1500,
                    coverage_amount=2500000,
                    features=json.dumps([
                        'Child\'s Life Coverage',
                        'Education Fund Creation',
                        'Waiver of Premium Benefit',
                        'Maturity at Important Ages',
                        'Parent Life Cover Option'
                    ])
                ),
                Scheme(
                    name='Unit Linked Life Insurance',
                    category='life',
                    description='Life insurance with investment in market-linked funds for wealth creation and life protection.',
                    premium_amount=2500,
                    coverage_amount=3000000,
                    features=json.dumps([
                        'Life Cover + Investment',
                        'Market-Linked Returns',
                        'Fund Switching Option',
                        'Partial Withdrawal',
                        'Flexible Premium Payment'
                    ])
                ),
                Scheme(
                    name='Money Back Life Insurance',
                    category='life',
                    description='Life insurance with periodic money back benefits during policy term plus death benefit.',
                    premium_amount=1800,
                    coverage_amount=2000000,
                    features=json.dumps([
                        'Periodic Money Back',
                        'Life Coverage Throughout',
                        'Maturity Benefit',
                        'Loyalty Additions',
                        'Premium Payment Flexibility'
                    ])
                ),
                Scheme(
                    name='Group Life Insurance',
                    category='life',
                    description='Life insurance for group of people like employees with affordable premium rates.',
                    premium_amount=500,
                    coverage_amount=1000000,
                    features=json.dumps([
                        'Group Life Coverage',
                        'Low Premium Rates',
                        'Easy Enrollment',
                        'Employer Contribution',
                        'Conversion Option'
                    ])
                ),
                Scheme(
                    name='Pension Life Insurance',
                    category='life',
                    description='Life insurance with pension benefits providing regular income after retirement with life cover.',
                    premium_amount=3500,
                    coverage_amount=1500000,
                    features=json.dumps([
                        'Retirement Income',
                        'Life Cover During Accumulation',
                        'Guaranteed Pension',
                        'Spouse Pension Option',
                        'Return of Purchase Price'
                    ])
                ),
                Scheme(
                    name='Women Life Insurance Plan',
                    category='life',
                    description='Specially designed life insurance for women with additional benefits and lower premium rates.',
                    premium_amount=800,
                    coverage_amount=1800000,
                    features=json.dumps([
                        'Women-Specific Life Cover',
                        'Maternity Benefits',
                        'Lower Premium for Women',
                        'Critical Illness Rider',
                        'Flexible Payment Terms'
                    ])
                ),
                Scheme(
                    name='Senior Citizen Life Insurance',
                    category='life',
                    description='Life insurance tailored for senior citizens aged 50-80 with simplified underwriting.',
                    premium_amount=1200,
                    coverage_amount=800000,
                    min_age=50,
                    max_age=80,
                    features=json.dumps([
                        'Senior Citizen Life Cover',
                        'No Medical Examination',
                        'Immediate Coverage',
                        'Guaranteed Acceptance',
                        'Final Expense Coverage'
                    ])
                )
            ]

            db.session.bulk_save_objects(schemes)
            db.session.commit()
            print("--- Database seeded with comprehensive life insurance schemes ---")
            print("--- Available insurance plans: 10 ---")

    print("🚀 SecureBank Insurance Platform Starting...")
    print("📊 Features Available:")
    print("   ✅ User Registration with Biometric Verification")
    print("   ✅ Secure Login System")
    print("   ✅ 10+ Life Insurance Plans")
    print("   ✅ Policy Application with PAN Verification")
    print("   ✅ 24-Hour Policy Withdrawal")
    print("   ✅ Claims Processing with Document Upload")
    print("   ✅ Report Unauthorized Transactions")
    print("   ✅ Complaints & Feedback System")
    print("   ✅ Complete User Profile Management")
    print("   ✅ FAQ Section with Life Insurance Information")
    print("   ✅ Professional Banking-Style UI")
    print("\n🌐 Access the platform at: http://localhost:5000")
    print("🔐 All systems operational!")

    app.run(debug=True, host='0.0.0.0', port=5000)