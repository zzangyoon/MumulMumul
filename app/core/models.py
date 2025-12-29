import sys
sys.path.append("../..")

from langchain_openai import OpenAIEmbeddings
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
from functools import cache

load_dotenv()

@cache
def openai_chat_model(model_name: str = "gpt-5-mini", temperature: float = 0.0):
    model = init_chat_model(
        model_name,
        temperature=temperature
    )
    return model

@cache
def get_embedding_model():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    # embed_fn = embeddings.embed_documents
    return embeddings