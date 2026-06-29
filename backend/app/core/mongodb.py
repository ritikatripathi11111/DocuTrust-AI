from pymongo import MongoClient
from app.core.config import settings

client = MongoClient(settings.mongodb_uri)

db = client[settings.mongodb_database]

clients_collection = db.clients
documents_collection = db.documents
chunks_collection = db.document_chunks
traces_collection = db.interaction_traces