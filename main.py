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

# ---------------------------------------------------------
# 1. SETUP & ROBUST DATABASE CONNECTION
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-secure-123")
SECURITY_PASSWORD_SALT = 'safe-salt-secure-fax'
ts = URLSafeTimedSerializer(app.secret_key)

# Database URL Handling
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# FORCE RECOVERY: This engine setting recycles connections to prevent "stuck" states
engine = create_engine(db_url or 'sqlite:///virtual_fax.db', echo=False, pool_pre_ping=True)

# THE FIX: Use scoped_session. This creates a fresh connection for every request.
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

# ---------------------------------------------------------
# 2. TEARDOWN (CRITICAL FOR PREVENTING CRASHES)
# ---------------------------------------------------------
@app.teardown_appcontext
def shutdown_session(exception=None):
    # This runs after EVERY request to ensure the DB connection is clean
    db_session.remove()

# ---------------------------------------------------------
# 3. MODELS
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
# 4. SECURITY & HELPERS
# ---------------------------------------------------------
@app.after_request
def allow_iframe(response):
    response.headers.pop('X-Frame-Options', None)
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

def send_email(to_email, subject, body):
    try:
        user = os.environ.get('SMTP_USERNAME')
        pwd = os.environ.get('SMTP_PASSWORD')
        if not user or not pwd:
            return "Missing SMTP Credentials"
            
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"MAIL ERROR: {e}")
        return str(e)

# ---------------------------------------------------------
# 5. ROUTES
# ---------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    msg = ""
    if request.method == 'POST':
        email = request.form.get('email')
        # Use our safe db_session
        user = db_session.query(User).filter_by(email=email).first()
        if user:
            token = ts.dumps(user.email, salt=SECURITY_PASSWORD_SALT)
            link = url_for('login_token', token=token, _external=True)
            status = send_email(email, "Login", f"Link: {link}")
            if status == True:
                msg = "✅ Link sent!"
            else:
                msg = f"❌ Email Error: {status}"
        else:
            msg = "❌ User not found."

    return f"""
    <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
    <h2>Secure Fax Portal</h2>
    <p>{msg}</p>
    <form method="POST">
        <input type="email" name="email" placeholder="Email" required style="padding: 10px;">
        <button type="submit" style="padding: 10px;">Send Login Link</button>
    </form>
    <br><a href="/register">Create Account</a>
    </body></html>
    """

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        if db_session.query(User).filter_by(email=email).first():
            return "Email already taken. <a href='/'>Login</a>"
        
        try:
            new_user = User(email=email)
            db_session.add(new_user)
            db_session.flush()
            new_user.generate_fax_number()
            db_session.commit()
            return f"Success! ID: {new_user.fax_number} <a href='/'>Login</a>"
        except Exception as e:
            db_session.rollback() # CLEAN UP if there is an error
            return f"Error: {str(e)}"

    return "<form method='POST'><input name='email' placeholder='Email'><button>Register</button></form>"

@app.route('/login/<token>')
def login_token(token):
    try:
        email = ts.loads(token, salt=SECURITY_PASSWORD_SALT, max_age=900)
        user = db_session.query(User).filter_by(email=email).first()
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    except: return "Invalid Link"

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    return "<h1>Logged In!</h1><p>System Online.</p><a href='/logout'>Logout</a>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)