import os
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, request
#safer imports
try:
    from backend.db.mongo_client import db
except ModuleNotFoundError:
    from db.mongo_client import db


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# User adapter
class MongoUser(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.username = doc.get("username")
        self.email = doc.get("email")

    @staticmethod
    def get(user_id):
        doc = db.users.find_one({"_id": ObjectId(user_id)})
        return MongoUser(doc) if doc else None
    
@login_manager.user_loader
def load_user(user_id):
    return MongoUser.get(user_id)

# Utility
def get_payload():
    if request.is_json:
        return request.get_json(silent = True) or {}
    return request.form.to_dict()

def safe_user(doc):
    return {
        "_id": str(doc["_id"]),
        "username": doc.get("username"),
        "email": doc.get("email"),
        "created_at": doc.get("created_at"),
    }
#routes
@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "auth"})


@app.route("/auth/register", methods=["POST"])
def register():
    data = get_payload()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not username or not email or not password:
        return jsonify({"error": "Missing fields"}), 400
    
    if db.users.find_one({"email": email}) or db.users.find_one({"username": username}):
        return jsonify({"error": "user already exists"}), 409
    
    hashed_pw = generate_password_hash(password)
    user_doc = {
        "username": username,
        "email": email,
        "password": hashed_pw,
        "friends": [],
        "created_at": datetime.utcnow().isoformat()
    }
    result = db.users.insert_one(user_doc)
    new_user = db.users.find_one({"_id": result.inserted_id})

    login_user(MongoUser(new_user))
    return jsonify({"message": "registered", "user": safe_user(new_user)}), 201

@app.route("/auth/login", methods=["POST"])
def login():
    data = get_payload()
    email_or_username = data.get("email") or data.get("username")
    password = data.get("password", "")

    user = db.users.find_one({
        "$or": [{"email": email_or_username}, {"username": email_or_username}]
    })

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "invalid credentials"}), 401
    
    login_user(MongoUser(user))
    return jsonify({"message": "logged in", "user": safe_user(user)}), 200

@app.route("/auth/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "logged out"}), 200

@app.route("/auth/me", methods=["GET"])
@login_required
def me():
    user_doc = db.users.find_one({"_id": ObjectId(current_user.id)})
    return jsonify({"user": safe_user(user_doc)}), 200

if __name__ == "__main__":
    app.run(debug=True)