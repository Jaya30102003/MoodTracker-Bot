import os
from google.cloud import dialogflow
from google.oauth2 import service_account
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from langdetect import detect

app = Flask(__name__)

# Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'super_secret_key'
app.secret_key = "super_secret_key"

# Initialize Extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
login_manager = LoginManager()
login_manager.init_app(app)

# Set up Dialogflow Credentials
DIALOGFLOW_PROJECT_ID = "mood-chatbot-cdrq"
GOOGLE_APPLICATION_CREDENTIALS = "mood-chatbot-cdrq-93a7988e6386.json"

# Ensure the environment variable is set
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

# User Model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

# Chat History Model
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)

# Create Tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Home Page
@app.route('/')
def home():
    return redirect(url_for('login'))

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        if User.query.filter_by(username=username).first():
            return "User already exists!"
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            session['user_id'] = user.id
            return redirect(url_for('chat'))
        error = "Invalid credentials!"
    return render_template('login.html', error=error)

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_id', None)
    return redirect(url_for('login'))

# Chat Page
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    user_id = session.get('user_id')
    chats = ChatHistory.query.filter_by(user_id=user_id).all()
    return render_template('chat.html', chats=chats)

# Language Detection Function
def detect_language(text):
    try:
        lang = detect(text)
        if lang.startswith('ta'):
            return 'ta'  # Tamil
        elif lang.startswith('hi'):
            return 'hi'  # Hindi
        else:
            return 'en'  # Default to English
    except:
        return 'en'

# Get Dialogflow Response with Auto Language Detection
def get_dialogflow_response(user_message):
    credentials = service_account.Credentials.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS)
    session_client = dialogflow.SessionsClient(credentials=credentials)

    session = session_client.session_path(DIALOGFLOW_PROJECT_ID, str(current_user.id))

    # Auto-detect language
    detected_lang = detect_language(user_message)

    text_input = dialogflow.TextInput(text=user_message, language_code=detected_lang)
    query_input = dialogflow.QueryInput(text=text_input)

    response = session_client.detect_intent(request={"session": session, "query_input": query_input})
    return response.query_result.fulfillment_text

# Store Chat
@app.route('/chat/store', methods=['POST'])
@login_required
def store_chat():
    data = request.json
    user_message = data['user_message']
    bot_response = get_dialogflow_response(user_message)

    new_chat = ChatHistory(user_id=current_user.id, user_message=user_message, bot_response=bot_response)
    db.session.add(new_chat)
    db.session.commit()
    return jsonify({"bot_response": bot_response})

# Get Chat History
@app.route('/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    chats = ChatHistory.query.filter_by(user_id=current_user.id).all()
    chat_list = [{"user_message": chat.user_message, "bot_response": chat.bot_response} for chat in chats]
    return jsonify(chat_list)

if __name__ == '__main__':
    app.run(debug=True)
