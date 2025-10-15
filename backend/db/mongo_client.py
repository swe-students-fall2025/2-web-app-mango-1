import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

# initialize connection with our database cluster on the cloud
connection = MongoClient(f"mongodb+srv://{username}:{password}@mango.wnciexw.mongodb.net/")