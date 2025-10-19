import os
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime, timedelta
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

# Enable CORS for all routes
CORS(app, supports_credentials=True, origins=['http://localhost:8000', 'http://127.0.0.1:8000'])

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

# Pomodoro Timer Routes
@app.route("/api/timer/start", methods=["POST"])
@login_required
def start_timer():
    data = get_payload()
    work_duration = data.get("work_duration", 25)  # Default 25 minutes
    break_duration = data.get("break_duration", 5)  # Default 5 minutes
    
    timer_session = {
        "user_id": ObjectId(current_user.id),
        "work_duration": work_duration,
        "break_duration": break_duration,
        "start_time": datetime.utcnow(),
        "status": "working",
        "completed_cycles": 0
    }
    
    result = db.timer_sessions.insert_one(timer_session)
    return jsonify({
        "message": "Timer started",
        "session_id": str(result.inserted_id),
        "work_duration": work_duration,
        "break_duration": break_duration
    }), 201

@app.route("/api/timer/stop", methods=["POST"])
@login_required
def stop_timer():
    data = get_payload()
    session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "Session ID required"}), 400
    
    session = db.timer_sessions.find_one({
        "_id": ObjectId(session_id),
        "user_id": ObjectId(current_user.id)
    })
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    # Update session end time
    db.timer_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"end_time": datetime.utcnow(), "status": "stopped"}}
    )
    
    return jsonify({"message": "Timer stopped"}), 200

@app.route("/api/timer/complete-cycle", methods=["POST"])
@login_required
def complete_cycle():
    data = get_payload()
    session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "Session ID required"}), 400
    
    session = db.timer_sessions.find_one({
        "_id": ObjectId(session_id),
        "user_id": ObjectId(current_user.id)
    })
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    # Increment completed cycles
    db.timer_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$inc": {"completed_cycles": 1}}
    )
    
    return jsonify({"message": "Cycle completed"}), 200

# Study Session History Routes
@app.route("/api/sessions", methods=["GET"])
@login_required
def get_sessions():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit
    
    sessions = list(db.timer_sessions.find({
        "user_id": ObjectId(current_user.id)
    }).sort("start_time", -1).skip(skip).limit(limit))
    
    # Convert ObjectIds to strings for JSON serialization
    for session in sessions:
        session["_id"] = str(session["_id"])
        session["user_id"] = str(session["user_id"])
        if "start_time" in session:
            session["start_time"] = session["start_time"].isoformat()
        if "end_time" in session:
            session["end_time"] = session["end_time"].isoformat()
    
    total = db.timer_sessions.count_documents({"user_id": ObjectId(current_user.id)})
    
    return jsonify({
        "sessions": sessions,
        "total": total,
        "page": page,
        "limit": limit
    }), 200

@app.route("/api/sessions/stats", methods=["GET"])
@login_required
def get_session_stats():
    user_id = ObjectId(current_user.id)
    
    # Get total study time
    pipeline = [
        {"$match": {"user_id": user_id, "status": "stopped"}},
        {"$group": {
            "_id": None,
            "total_cycles": {"$sum": "$completed_cycles"},
            "total_sessions": {"$sum": 1}
        }}
    ]
    
    stats = list(db.timer_sessions.aggregate(pipeline))
    if stats:
        stats = stats[0]
        del stats["_id"]
    else:
        stats = {"total_cycles": 0, "total_sessions": 0}
    
    # Get current streak
    today = datetime.utcnow().date()
    streak = 0
    current_date = today
    
    while True:
        start_of_day = datetime.combine(current_date, datetime.min.time())
        end_of_day = datetime.combine(current_date, datetime.max.time())
        
        has_session = db.timer_sessions.find_one({
            "user_id": user_id,
            "start_time": {"$gte": start_of_day, "$lte": end_of_day}
        })
        
        if has_session:
            streak += 1
            current_date = current_date - timedelta(days=1)
        else:
            break
    
    stats["current_streak"] = streak
    
    return jsonify(stats), 200

# Friends Management Routes
@app.route("/api/friends", methods=["GET"])
@login_required
def get_friends():
    user_doc = db.users.find_one({"_id": ObjectId(current_user.id)})
    friend_ids = [ObjectId(fid) for fid in user_doc.get("friends", [])]
    
    friends = list(db.users.find({"_id": {"$in": friend_ids}}, {
        "_id": 1, "username": 1, "email": 1, "created_at": 1
    }))
    
    # Convert to safe format
    safe_friends = [safe_user(friend) for friend in friends]
    
    return jsonify({"friends": safe_friends}), 200

@app.route("/api/friends/add", methods=["POST"])
@login_required
def add_friend():
    data = get_payload()
    friend_username = data.get("username", "").strip()
    
    if not friend_username:
        return jsonify({"error": "Username required"}), 400
    
    # Find friend by username
    friend = db.users.find_one({"username": friend_username})
    if not friend:
        return jsonify({"error": "User not found"}), 404
    
    friend_id = str(friend["_id"])
    user_id = ObjectId(current_user.id)
    
    # Check if already friends
    user_doc = db.users.find_one({"_id": user_id})
    if friend_id in user_doc.get("friends", []):
        return jsonify({"error": "Already friends"}), 409
    
    # Add friend
    db.users.update_one(
        {"_id": user_id},
        {"$push": {"friends": friend_id}}
    )
    
    return jsonify({"message": "Friend added", "friend": safe_user(friend)}), 200

@app.route("/api/friends/remove", methods=["POST"])
@login_required
def remove_friend():
    data = get_payload()
    friend_id = data.get("friend_id", "").strip()
    
    if not friend_id:
        return jsonify({"error": "Friend ID required"}), 400
    
    user_id = ObjectId(current_user.id)
    
    # Remove friend
    result = db.users.update_one(
        {"_id": user_id},
        {"$pull": {"friends": friend_id}}
    )
    
    if result.modified_count == 0:
        return jsonify({"error": "Friend not found"}), 404
    
    return jsonify({"message": "Friend removed"}), 200

# Leaderboard Routes
@app.route("/api/leaderboard", methods=["GET"])
@login_required
def get_leaderboard():
    user_id = ObjectId(current_user.id)
    
    # Get user's friends
    user_doc = db.users.find_one({"_id": user_id})
    friend_ids = [ObjectId(fid) for fid in user_doc.get("friends", [])]
    friend_ids.append(user_id)  # Include current user
    
    # Get leaderboard data
    pipeline = [
        {"$match": {"user_id": {"$in": friend_ids}}},
        {"$group": {
            "_id": "$user_id",
            "total_cycles": {"$sum": "$completed_cycles"},
            "total_sessions": {"$sum": 1}
        }},
        {"$sort": {"total_cycles": -1}},
        {"$limit": 10}
    ]
    
    leaderboard_data = list(db.timer_sessions.aggregate(pipeline))
    
    # Get user details for leaderboard
    user_ids = [item["_id"] for item in leaderboard_data]
    users = {str(user["_id"]): safe_user(user) for user in db.users.find({"_id": {"$in": user_ids}})}
    
    # Format leaderboard
    leaderboard = []
    for i, item in enumerate(leaderboard_data):
        user_id_str = str(item["_id"])
        if user_id_str in users:
            leaderboard.append({
                "rank": i + 1,
                "user": users[user_id_str],
                "total_cycles": item["total_cycles"],
                "total_sessions": item["total_sessions"]
            })
    
    return jsonify({"leaderboard": leaderboard}), 200

# User Settings Routes
@app.route("/api/user/settings", methods=["GET"])
@login_required
def get_user_settings():
    user_doc = db.users.find_one({"_id": ObjectId(current_user.id)})
    
    settings = {
        "default_work_duration": user_doc.get("default_work_duration", 25),
        "default_break_duration": user_doc.get("default_break_duration", 5),
        "notifications_enabled": user_doc.get("notifications_enabled", True)
    }
    
    return jsonify({"settings": settings}), 200

@app.route("/api/user/settings", methods=["PUT"])
@login_required
def update_user_settings():
    data = get_payload()
    
    update_data = {}
    if "default_work_duration" in data:
        update_data["default_work_duration"] = data["default_work_duration"]
    if "default_break_duration" in data:
        update_data["default_break_duration"] = data["default_break_duration"]
    if "notifications_enabled" in data:
        update_data["notifications_enabled"] = data["notifications_enabled"]
    
    if not update_data:
        return jsonify({"error": "No settings provided"}), 400
    
    db.users.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data}
    )
    
    return jsonify({"message": "Settings updated"}), 200

if __name__ == "__main__":
    app.run(debug=True)