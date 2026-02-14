import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, redirect, url_for, session, abort, send_file
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from pdf_generator import generate_fax_pdf 

# ---------------------------------------------------------
# 1. CONFIGURATION & DATABASE SETUP
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-secure-123")
SECURITY_PASSWORD_SALT = 'safe-salt-secure-fax'
ts = URLSafeTimedSerializer(app.secret_key)

# Database Logic
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url or 'sqlite:///virtual_fax.db', echo=False)
Session = sessionmaker(bind=engine)
db_session = Session()
Base = declarative_base()

# ---------------------------------------------------------
# 2. DATABASE MODELS
# ---------------------------------------------------------
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    fax_number = Column(String(20), unique=True, nullable=True) 
    messages = relationship('Message', back_populates='recipient')

    def generate_fax_number(self):
        if self.id:
            self.fax_number = f"GFAX-{1000 + self.id}"

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    sender_info = Column(String(100)) 
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    recipient_id = Column(Integer, ForeignKey('users.id'))
    recipient = relationship('User', back_populates='messages')

Base.metadata.create_all(engine)

# ---------------------------------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------------------------------

# FIX FOR GOOGLE SITES EMBEDDING
@app.after_request
def allow_iframe(response):
    response.headers.pop('X-Frame-Options', None)
    # The "*" allows embedding on ANY site, bypassing Google's strict checks
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

# DEBUGGING EMAIL SENDER
def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = os.environ.get('SMTP_USERNAME')
    msg['To'] = to_email
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        # Check if variables exist
        user = os.environ.get('SMTP_USERNAME')
        pwd = os.environ.get('SMTP_PASSWORD')
        if not user or not pwd:
            print("❌ ERROR: SMTP credentials missing in Render Environment!")
            return "Missing Credentials"

        server = smtplib.SMTP(os.environ.get('SMTP_SERVER', 'smtp.gmail.com'), 587)
        server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        # Print the exact error to the Render Logs so we can see it
        print(f"❌ MAIL ERROR: {str(e)}")
        return str(e)

# ---------------------------------------------------------
# 4. UI TEMPLATES
# ---------------------------------------------------------

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Fax Portal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
        body {{ font-family: 'Inter', sans-serif; }}
    </style>
</head>
<body class="bg-gradient-to-br from-gray-100 to-gray-300 min-h-screen text-gray-800 flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden border border-gray-100">
        <div class="bg-gray-800 p-6 text-center">
            <h1 class="text-white text-xl font-semibold tracking-wide uppercase">Secure Fax Portal</h1>
            <p class="text-gray-400 text-xs mt-1">Encrypted Document Transmission</p>
        </div>
        <div class="p-8">
            {content}
        </div>
        <div class="bg-gray-50 p-4 text-center border-t border-gray-100">
            <p class="text-xs text-gray-400">Powered by GFAX Secure Systems &copy; 2026</p>
        </div>
    </div>
</body>
</html>
"""

# ---------------------------------------------------------
# 5. ROUTES
# ---------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    msg = ""
    if request.method == 'POST':
        email = request.form.get('email')
        user = db_session.query(User).filter_by(email=email).first()
        if user:
            token = ts.dumps(user.email, salt=SECURITY_PASSWORD_SALT)
            link = url_for('login_token', token=token, _external=True)
            
            # Try to send email
            email_status = send_email(email, "Secure Login Link", f"Access your secure fax dashboard here: {link}")
            
            if email_status == True:
                msg = "<div class='mb-4 p-3 bg-green-50 text-green-700 text-sm rounded border border-green-200'>✅ Login link sent! Check your inbox.</div>"
            else:
                # SHOW THE ERROR ON SCREEN
                msg = f"<div class='mb-4 p-3 bg-red-50 text-red-700 text-sm rounded border border-red-200'>❌ Email Failed: {email_status}</div>"
        else:
            msg = "<div class='mb-4 p-3 bg-red-50 text-red-700 text-sm rounded border border-red-200'>❌ Account not found. Please register.</div>"

    form_html = f"""
    {msg}
    <form method="POST" class="space-y-6">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
            <input type="email" name="email" required placeholder="you@example.com" 
                   class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 focus:border-gray-500 outline-none transition-all">
        </div>
        <button type="submit" class="w-full bg-gray-800 hover:bg-gray-900 text-white font-medium py-2 rounded-lg transition-colors shadow-lg">
            Send Secure Login Link
        </button>
    </form>
    <div class="mt-6 text-center">
        <a href="/register" class="text-sm text-gray-500 hover:text-gray-800 transition-colors">No account? Create GFAX Number</a>
    </div>
    """
    return BASE_LAYOUT.format(content=form_html)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        if db_session.query(User).filter_by(email=email).first():
            return BASE_LAYOUT.format(content="<div class='text-center text-red-600'>Email already registered. <a href='/' class='underline'>Login</a></div>")
        
        new_user = User(email=email)
        db_session.add(new_user)
        db_session.flush()
        new_user.generate_fax_number()
        db_session.commit()
        
        success_html = f"""
        <div class="text-center">
            <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-4">
                <svg class="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
            </div>
            <h3 class="text-lg font-medium text-gray-900">Registration Successful!</h3>
            <p class="text-sm text-gray-500 mt-2">Your Secure Fax ID is:</p>
            <p class="text-2xl font-bold text-gray-800 my-4 bg-gray-100 py-2 rounded border border-gray-200 tracking-wider">{new_user.fax_number}</p>
            <a href="/" class="block w-full bg-gray-800 text-white py-2 rounded-lg mt-6 hover:bg-gray-900">Go to Login</a>
        </div>
        """
        return BASE_LAYOUT.format(content=success_html)

    reg_form = """
    <h2 class="text-center text-lg font-semibold mb-6 text-gray-700">New Account Registration</h2>
    <form method="POST" class="space-y-6">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
            <input type="email" name="email" required placeholder="you@company.com" 
                   class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 outline-none transition-all">
        </div>
        <button type="submit" class="w-full bg-gray-800 hover:bg-gray-900 text-white font-medium py-2 rounded-lg transition-colors shadow-lg">
            Generate GFAX Number
        </button>
    </form>
    <div class="mt-4 text-center">
        <a href="/" class="text-sm text-gray-500 hover:text-gray-800">Back to Login</a>
    </div>
    """
    return BASE_LAYOUT.format(content=reg_form)

@app.route('/login/<token>')
def login_token(token):
    try:
        email = ts.loads(token, salt=SECURITY_PASSWORD_SALT, max_age=900)
    except:
        return BASE_LAYOUT.format(content="<div class='text-center text-red-500'>Link Expired. <a href='/' class='underline'>Try Again</a></div>")
    
    user = db_session.query(User).filter_by(email=email).first()
    session['user_id'] = user.id
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    user = db_session.query(User).get(session['user_id'])
    messages = db_session.query(Message).filter_by(recipient_id=user.id).all()
    
    msgs_html = ""
    if not messages:
        msgs_html = "<div class='text-center text-gray-400 py-8 italic'>No faxes received yet.</div>"
    else:
        for m in messages:
            msgs_html += f"""
            <div class="flex items-center justify-between p-4 bg-gray-50 border border-gray-200 rounded-lg mb-2 hover:shadow-md transition-shadow">
                <div>
                    <p class="text-xs text-gray-500 font-mono">{m.timestamp.strftime('%Y-%m-%d %H:%M')}</p>
                    <p class="text-sm font-semibold text-gray-800">From: {m.sender_info}</p>
                </div>
                <a href="/view/{m.id}" target="_blank" class="text-xs bg-white border border-gray-300 px-3 py-1 rounded hover:bg-gray-100 text-gray-700 font-medium">
                    View PDF
                </a>
            </div>
            """
    
    dash_content = f"""
    <div class="flex justify-between items-center mb-6 border-b border-gray-200 pb-4">
        <div>
            <h2 class="text-xl font-bold text-gray-800">My Inbox</h2>
            <p class="text-xs text-gray-500 font-mono">ID: {user.fax_number}</p>
        </div>
        <a href="/logout" class="text-xs text-red-500 hover:text-red-700">Logout</a>
    </div>
    
    <div class="mb-6">
        <a href="/compose" class="block w-full text-center bg-gray-800 hover:bg-gray-900 text-white font-medium py-3 rounded-lg shadow-md transition-all">
            + Compose New Fax
        </a>
    </div>
    
    <h3 class="text-xs uppercase tracking-wide text-gray-400 font-bold mb-3">Recent Transmissions</h3>
    <div class="space-y-2">
        {msgs_html}
    </div>
    """
    return BASE_LAYOUT.format(content=dash_content)

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        recipient_gfax = request.form.get('gfax')
        content = request.form.get('content')
        sender = db_session.query(User).get(session['user_id'])
        
        target = db_session.query(User).filter_by(fax_number=recipient_gfax).first()
        if target:
            msg = Message(sender_info=sender.fax_number, content=content, recipient=target)
            db_session.add(msg)
            db_session.commit()
            
            # Send Email Notification
            login_link = url_for('index', _external=True)
            send_email(target.email, "New Secure Fax", f"You have a new secure fax from {sender.fax_number}. Log in to view: {login_link}")
            
            return redirect(url_for('dashboard'))
        else:
            return BASE_LAYOUT.format(content=f"<div class='text-red-500 text-center mb-4'>Error: GFAX Number '{recipient_gfax}' not found.</div><a href='/compose'>Try Again</a>")

    compose_form = """
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-bold text-gray-800">Compose Fax</h2>
        <a href="/dashboard" class="text-xs text-gray-500 hover:text-gray-800">Cancel</a>
    </div>
    <form method="POST" class="space-y-4">
        <div>
            <label class="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">To (GFAX Number)</label>
            <input type="text" name="gfax" required placeholder="GFAX-1002" 
                   class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 outline-none font-mono">
        </div>
        <div>
            <label class="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Message Content</label>
            <textarea name="content" rows="6" required placeholder="Type your secure message here..." 
                      class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-500 outline-none"></textarea>
        </div>
        <button type="submit" class="w-full bg-gray-800 hover:bg-gray-900 text-white font-medium py-3 rounded-lg shadow-lg transition-all">
            Send Secure Transmission
        </button>
    </form>
    """
    return BASE_LAYOUT.format(content=compose_form)

@app.route('/view/<int:msg_id>')
def view(msg_id):
    if 'user_id' not in session: return redirect(url_for('index'))
    msg = db_session.query(Message).get(msg_id)
    if not msg or msg.recipient_id != session['user_id']: abort(403)
    
    sender_name = msg.sender_info
    recipient_name = f"GFAX-{1000+msg.recipient_id}"
    pdf_file = generate_fax_pdf(sender_name, recipient_name, msg.content, f"fax_{msg_id}.pdf")
    
    return send_file(pdf_file, as_attachment=False)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)