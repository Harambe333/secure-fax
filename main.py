import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, redirect, url_for, session, abort, send_file, render_template_string
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from pdf_generator import generate_fax_pdf 

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secure-fax-key-2026")
SECURITY_PASSWORD_SALT = 'fax-salt-2026'
ts = URLSafeTimedSerializer(app.secret_key)

# --- DATABASE ---
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url or 'sqlite:///virtual_fax.db', pool_pre_ping=True)
db_session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    fax_number = Column(String(20), unique=True)
    messages = relationship('Message', back_populates='recipient')
    def generate_fax(self):
        if self.id: self.fax_number = f"GFAX-{1000 + self.id}"

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    sender_info = Column(String(100))
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    recipient_id = Column(Integer, ForeignKey('users.id'))
    recipient = relationship('User', back_populates='messages')

Base.metadata.create_all(engine)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

# --- SECURITY ---
@app.after_request
def allow_iframe(response):
    response.headers.pop('X-Frame-Options', None)
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

def send_email(to_email, subject, body):
    try:
        user = os.environ.get('SMTP_USERNAME')
        pwd = os.environ.get('SMTP_PASSWORD')
        if not user or not pwd: return "Missing Credentials"
        
        msg = MIMEMultipart()
        msg['Subject'], msg['From'], msg['To'] = subject, user, to_email
        msg.attach(MIMEText(body, 'plain'))
        
        # Added a 10-second timeout so it doesn't hang the site
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        return str(e)

# --- UI TEMPLATE ---
BASE_UI = """
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body { background: linear-gradient(135deg, #f3f4f6 0%, #d1d5db 100%); min-height: 100vh; font-family: sans-serif; }</style>
</head>
<body class="flex items-center justify-center p-6">
    <div class="bg-white p-8 rounded-2xl shadow-2xl w-full max-w-md border border-gray-200">
        <div class="text-center mb-8">
            <h1 class="text-2xl font-bold text-gray-800 uppercase tracking-widest">Secure GFAX</h1>
            <p class="text-gray-400 text-xs">Encrypted Document Portal</p>
        </div>
        {{ content | safe }}
        <div class="mt-8 pt-4 border-t border-gray-100 text-center text-[10px] text-gray-400 uppercase tracking-widest">
            Tauries LLC © 2026
        </div>
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    html = ""
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            token = ts.dumps(user.email, salt=SECURITY_PASSWORD_SALT)
            link = url_for('login_token', token=token, _external=True)
            status = send_email(email, "Login Link", f"Link: {link}")
            
            # EMERGENCY BYPASS: If email fails, show the link on screen!
            if status == True:
                html = "<p class='text-green-600 bg-green-50 p-3 rounded mb-4'>✅ Check your email!</p>"
            else:
                html = f"<div class='bg-yellow-50 p-3 rounded mb-4 text-xs text-yellow-800 font-mono'>⚠️ Email Failed: {status}<br><br><a href='{link}' class='underline font-bold text-blue-600'>CLICK HERE TO LOG IN DIRECTLY</a></div>"
        else:
            html = "<p class='text-red-600 bg-red-50 p-3 rounded mb-4'>❌ Account not found.</p>"

    content = f"""
    {html}
    <form method="POST" class="space-y-4">
        <input type="email" name="email" placeholder="Email Address" required class="w-full p-3 border rounded-lg outline-none focus:ring-2 focus:ring-gray-400">
        <button class="w-full bg-gray-800 text-white p-3 rounded-lg hover:bg-black transition font-bold uppercase text-sm">Send Secure Link</button>
    </form>
    <p class="mt-6 text-center text-sm text-gray-500">Need a number? <a href="/register" class="text-gray-800 font-bold underline">Register</a></p>
    """
    return render_template_string(BASE_UI, content=content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    html = ""
    if request.method == 'POST':
        email = request.form.get('email')
        if User.query.filter_by(email=email).first():
            html = "<p class='text-red-600 mb-4'>Already registered.</p>"
        else:
            try:
                new_user = User(email=email)
                db_session.add(new_user)
                db_session.commit()
                new_user.generate_fax()
                db_session.commit()
                html = f"<div class='text-center'><p class='text-green-600 font-bold'>Success!</p><p class='text-2xl font-mono my-4'>{new_user.fax_number}</p><a href='/' class='underline text-blue-600'>Login Now</a></div>"
                return render_template_string(BASE_UI, content=html)
            except:
                db_session.rollback()
                html = "<p class='text-red-600 mb-4'>Server error.</p>"

    content = f"""
    {html}
    <h2 class="text-lg font-bold mb-4 text-gray-700">Get GFAX Number</h2>
    <form method="POST" class="space-y-4">
        <input name="email" type="email" placeholder="Email" required class="w-full p-3 border rounded-lg outline-none focus:ring-2 focus:ring-gray-400">
        <button class="w-full bg-gray-800 text-white p-3 rounded-lg font-bold uppercase text-sm">Register</button>
    </form>
    <a href="/" class="block mt-4 text-center text-xs text-gray-400 underline">Back</a>
    """
    return render_template_string(BASE_UI, content=content)

@app.route('/login/<token>')
def login_token(token):
    try:
        email = ts.loads(token, salt=SECURITY_PASSWORD_SALT, max_age=3600)
        user = User.query.filter_by(email=email).first()
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    except: return "Invalid link."

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    msgs = Message.query.filter_by(recipient_id=user.id).order_by(Message.timestamp.desc()).all()
    inbox = "".join([f"<div class='p-3 border-b flex justify-between items-center text-sm'><p><b>{m.sender_info}</b><br><span class='text-[10px] text-gray-400'>{m.timestamp.strftime('%Y-%m-%d')}</span></p><a href='/view/{m.id}' class='text-blue-600 underline font-bold'>PDF</a></div>" for m in msgs]) or "<p class='text-gray-400 text-center py-4'>Empty</p>"
    
    content = f"""
    <div class="mb-6 flex justify-between items-end">
        <div><p class="text-[10px] uppercase text-gray-400">Your Number</p><h2 class="text-xl font-mono font-bold text-gray-800">{user.fax_number}</h2></div>
        <a href="/logout" class="text-[10px] uppercase font-bold text-red-400">Logout</a>
    </div>
    <a href="/compose" class="block w-full text-center bg-gray-100 border border-gray-300 p-3 rounded-lg font-bold text-sm text-gray-600 hover:bg-gray-200 mb-6">+ Compose Fax</a>
    <h3 class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2 border-b">Incoming</h3>
    <div class="max-h-60 overflow-y-auto">{inbox}</div>
    """
    return render_template_string(BASE_UI, content=content)

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if 'user_id' not in session: return redirect(url_for('index'))
    html = ""
    if request.method == 'POST':
        target = request.form.get('gfax').upper()
        content = request.form.get('content')
        sender = User.query.get(session['user_id'])
        recipient = User.query.filter_by(fax_number=target).first()
        if recipient:
            msg = Message(sender_info=sender.fax_number, content=content, recipient=recipient)
            db_session.add(msg)
            db_session.commit()
            send_email(recipient.email, "New Fax", f"New secure fax from {sender.fax_number}")
            return render_template_string(BASE_UI, content="<div class='text-center'><p class='text-green-600 mb-4'>✅ Sent!</p><a href='/dashboard' class='underline'>Back to Inbox</a></div>")
        html = "<p class='text-red-600 mb-4'>GFAX ID not found.</p>"

    content = f"""
    {html}
    <h2 class="text-lg font-bold mb-4 text-gray-700 font-mono">Compose Fax</h2>
    <form method="POST" class="space-y-4">
        <input name="gfax" placeholder="To: GFAX-XXXX" required class="w-full p-3 border rounded-lg font-mono text-sm uppercase">
        <textarea name="content" placeholder="Secure message..." rows="5" required class="w-full p-3 border rounded-lg text-sm"></textarea>
        <button class="w-full bg-gray-800 text-white p-3 rounded-lg font-bold uppercase text-sm">Send Transmission</button>
    </form>
    <a href="/dashboard" class="block mt-4 text-center text-xs text-gray-400 underline">Cancel</a>
    """
    return render_template_string(BASE_UI, content=content)

@app.route('/view/<int:msg_id>')
def view(msg_id):
    if 'user_id' not in session: return redirect(url_for('index'))
    msg = Message.query.get(msg_id)
    if not msg or msg.recipient_id != session['user_id']: abort(403)
    user = User.query.get(session['user_id'])
    pdf = generate_fax_pdf(msg.sender_info, user.fax_number, msg.content, f"fax_{msg_id}.pdf")
    return send_file(pdf)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)