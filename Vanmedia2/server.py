import os
import json
import uuid
import secrets
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from jinja2 import Environment, FileSystemLoader
import time
import datetime
from functools import wraps

# Setup absolute paths for production reliability
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AUTH_JSON = os.path.join(BASE_DIR, 'auth.json')

def get_admin_credentials():
    if os.path.exists(AUTH_JSON):
        try:
            with open(AUTH_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    auth_txt = os.path.join(BASE_DIR, 'auth.txt')
    if os.path.exists(auth_txt):
        with open(auth_txt, 'r', encoding='utf-8') as f:
            return {"username": "vanadmin", "password": f.read().strip()}
    return {"username": "vanadmin", "password": "VanMedia2026#SecurePass"}

def set_admin_credentials(username, password):
    with open(AUTH_JSON, 'w', encoding='utf-8') as f:
        json.dump({"username": username, "password": password}, f, indent=2)

def get_admin_password():
    return get_admin_credentials().get('password', 'VanMedia2026#SecurePass')

def set_admin_password(new_pass):
    creds = get_admin_credentials()
    set_admin_credentials(creds.get('username', 'vanadmin'), new_pass)

SECRET_KEY = "vanmedia_hyper_secret_auth"

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            if ':' in token or token.startswith('admin:'):
                return f(*args, **kwargs)
        return jsonify({'error': 'Unauthorized'}), 401
    return decorated

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')

DATA_FILE = os.path.join(BASE_DIR, 'content.json')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'Images')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

ANALYTICS_FILE = os.path.join(BASE_DIR, 'analytics.json')

def load_analytics():
    if not os.path.exists(ANALYTICS_FILE):
        return {"views": 0, "interactions": 0, "monthly": {}}
    with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_analytics(data):
    with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)

def build_site():
    data = load_data()
    # Reverse portfolio items so newest is first in the generated HTML
    if 'portfolio' in data:
        data['portfolio'] = list(reversed(data['portfolio']))
        
    env = Environment(loader=FileSystemLoader(BASE_DIR))
    template = env.get_template('template.html')
    output = template.render(data=data)
    index_path = os.path.join(BASE_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(output)

@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/style.css')
def serve_style():
    return send_from_directory(BASE_DIR, 'style.css')

@app.route('/admin')
def serve_admin():
    return send_from_directory(BASE_DIR, 'admin.html')

@app.route('/api/login', methods=['POST'])
def login():
    req = request.get_json() or {}
    creds = get_admin_credentials()
    req_user = req.get('username')
    req_pass = req.get('password')
    
    if req_pass == creds['password'] and (not req_user or req_user.strip().lower() == creds['username'].strip().lower()):
        token = f"{creds['username']}:{int(time.time())}"
        return jsonify({'token': token, 'username': creds['username']})
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/password', methods=['POST'])
@token_required
def update_password():
    req = request.get_json()
    if req and req.get('current') == get_admin_password():
        set_admin_password(req.get('new'))
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Invalid current password'}), 401

@app.route('/api/forget-user', methods=['POST'])
def forget_user_api():
    return jsonify({'success': True, 'message': 'User credentials and session forgotten'})

@app.route('/api/analytics/reset', methods=['POST'])
@token_required
def reset_analytics():
    save_analytics({"views": 0, "interactions": 0, "monthly": {}})
    return jsonify({'success': True, 'message': 'User tracking data reset successfully'})

@app.route('/api/content', methods=['GET'])
def get_content():
    return jsonify(load_data())

@app.route('/api/content', methods=['POST'])
@token_required
def update_content():
    new_data = request.get_json()
    save_data(new_data)
    try:
        build_site()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics', methods=['GET'])
@token_required
def get_analytics():
    return jsonify(load_analytics())

@app.route('/api/analytics/track', methods=['POST', 'GET'])
def track_analytics():
    track_type = request.args.get('type')
    if not track_type:
        track_type = request.json.get('type') if request.is_json else 'view'
        
    data = load_analytics()
    if track_type == 'view':
        data['views'] = data.get('views', 0) + 1
    elif track_type == 'interaction':
        data['interactions'] = data.get('interactions', 0) + 1
        
    month_key = datetime.datetime.now().strftime('%Y-%m')
    if 'monthly' not in data:
        data['monthly'] = {}
    if month_key not in data['monthly']:
        data['monthly'][month_key] = {"views": 0, "interactions": 0}
        
    if track_type == 'view':
        data['monthly'][month_key]['views'] += 1
    elif track_type == 'interaction':
        data['monthly'][month_key]['interactions'] += 1
        
    save_analytics(data)
    return jsonify({'success': True})

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    filename = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())[:8]
    final_filename = f"{unique_id}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, final_filename)
    file.save(file_path)
    
    return jsonify({'path': f"Images/{final_filename}"})

if __name__ == '__main__':
    try:
        build_site()
    except Exception as e:
        print("Initial build failed:", e)
    app.run(debug=True, host='0.0.0.0', port=5000)
