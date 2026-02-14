import os
from flask import Flask

# 1. SETUP (NO DATABASE)
app = Flask(__name__)

# 2. ROUTES
@app.route('/', methods=['GET', 'POST'])
def index():
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: green;">✅ SYSTEM ONLINE</h1>
            <p>The web server is running perfectly.</p>
            <p>Database is currently disconnected for maintenance.</p>
        </body>
    </html>
    """

# 3. HEALTH CHECK (Required by Render)
@app.route('/healthz')
def health():
    return "OK", 200

if __name__ == '__main__':
    app.run(debug=True)