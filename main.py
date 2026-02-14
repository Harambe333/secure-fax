import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, redirect, url_for, session, abort, send_file
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from pdf_generator import generate_fax_pdf 

# --- 1. CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-123")
SECURITY_PASSWORD_SALT = 'fax-salt'
ts = URLSafeTimedSerializer(app.secret_key)

# Database Connection Fix (Handles Neon/Postgres and SQLite)
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url or 'sqlite:///virtual_fax.db', pool_pre_ping=True)
db_session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

# --- 2. MODELS ---
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

# --- 3. DATABASE SAFETY VALVE ---
@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

# --- 4. HELPERS & PERMISSIONS ---
@app.after_request
def allow_iframe(response):
    response.headers.pop('X-Frame-Options', None)
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

def send_email(to_email, subject, body):
    try:
        user = os.environ.get('SMTP_USERNAME')
        pwd = os.environ.get('SMTP_PASSWORD')
        msg = MIMEMultipart()
        msg['Subject'], msg['From'], msg['To'] = subject, user, to_email
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"MAIL ERROR: {e}")
        return False

# --- 5. ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    msg = ""
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            token = ts.dumps(user.email, salt=SECURITY_PASSWORD_SALT)
            link = url_for('login_token', token=token, _external=True)
            if send_email(email, "Secure Fax Login", f"Access your portal: {link}"):
                msg = "✅ Check your email for the login link!"
            else:
                msg = "❌ Email error. Check your Render logs."
        else: msg = "❌ Email not found. Please register."
    return f"<h2>Login</h2><p>{msg}</p><form method='POST'><input type='email' name='email' placeholder='Email' required><button>Send Link</button></form><br><a href='/register'>Register</a>"

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        if User.query.filter_by(email=email).first(): return "Email taken."
        try:
            new_user = User(email=email)
            db_session.add(new_user)
            db_session.commit()
            new_user.generate_fax()
            db_session.commit()
            return f"Success! Your GFAX ID: {new_user.fax_number} <br><a href='/'>Login</a>"
        except:
            db_session.rollback()
            return "Server Error. Try again."
    return "<h2>Register</h2><form method='POST'><input name='email' type='email' required><button>Get GFAX Number</button></form>"

@app.route('/login/<token>')
def login_token(token):
    try:
        email = ts.loads(token, salt=SECURITY_PASSWORD_SALT, max_age=3600)
        user = User.query.filter_by(email=email).first()
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    except: return "Invalid or expired link."

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    msgs = Message.query.filter_by(recipient_id=user.id).all()
    inbox = "".join([f"<li>From: {m.sender_info} - <a href='/view/{m.id}'>View PDF</a></li>" for m in msgs])
    return f"<h1>ID: {user.fax_number}</h1><a href='/compose'>Send Fax</a><hr><h3>Inbox</h3><ul>{inbox}</ul><br><a href='/logout'>Logout</a>"

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if 'user_id' not in session: return redirect(url_for('index'))
    if request.method == 'POST':
        target_fax = request.form.get('gfax')
        content = request.form.get('content')
        sender = User.query.get(session['user_id'])
        recipient = User.query.filter_by(fax_number=target_fax).first()
        if recipient:
            msg = Message(sender_info=sender.fax_number, content=content, recipient=recipient)
            db_session.add(msg)
            db_session.commit()
            send_email(recipient.email, "New Fax Received", f"You have a new secure fax from {sender.fax_number}.")
            return "✅ Fax Sent! <a href='/dashboard'>Back</a>"
        return "❌ GFAX number not found."
    return "<h2>Send Fax</h2><form method='POST'><input name='gfax' placeholder='To GFAX-XXXX' required><br><textarea name='content' placeholder='Message...'></textarea><br><button>Send</button></form>"

@app.route('/view/<int:msg_id>')
def view(msg_id):
    if 'user_id' not in session: return redirect(url_for('index'))
    msg = Message.query.get(msg_id)
    if not msg or msg.recipient_id != session['user_id']: abort(403)
    pdf = generate_fax_pdf(msg.sender_info, f"GFAX-{1000+msg.recipient_id}", msg.content, f"fax_{msg_id}.pdf")
    return send_file(pdf)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))