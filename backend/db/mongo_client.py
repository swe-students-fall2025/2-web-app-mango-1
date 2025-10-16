import os
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi # for ssl verification with Atlas

load_dotenv()

username = os.getenv("MONGO_USERNAME")
password = os.getenv("MONGO_PASSWORD")
db_name = os.getenv("MONGO_DB_NAME", "project_mango")

if not (username and password):
    raise RuntimeError("Missing MongoDB credentials in .env file")

MONGO_URI = f"mongodb+srv://{username}:{password}@mango.wnciexw.mongodb.net/"

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[db_name]

try:
    client.admin.command("ping")
    print("connected")
except Exception as e:
    print("failed ", e)