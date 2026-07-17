import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from typing import List, Dict, Any, Optional
import os
from api.config import settings
from loguru import logger

# Unified Embedding Function
class AIFlowEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER.lower()
        self.model = settings.EMBEDDING_MODEL
        self._local_model = None

    def __call__(self, input_texts: Documents) -> Embeddings:
        # Cast input_texts
        texts = list(input_texts)
        if self.provider == "local":
            if not self._local_model:
                try:
                    from sentence_transformers import SentenceTransformer
                    # Suppress huggingface warnings
                    os.environ["TOKENIZERS_PARALLELISM"] = "false"
                    logger.info(f"Loading local SentenceTransformer model: {self.model}")
                    self._local_model = SentenceTransformer(self.model)
                except Exception as e:
                    logger.error(f"Failed to load sentence-transformers. Check python environment. Error: {e}")
                    raise e
            embeddings = self._local_model.encode(texts)
            return [emb.tolist() for emb in embeddings]
        
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            # Embed content batching
            res = genai.embed_content(
                model="models/text-embedding-004",
                content=texts,
                task_type="retrieval_document"
            )
            return res['embedding']
        
        else:
            # Simple mock fallback
            logger.warning(f"Unknown embedding provider '{self.provider}'. Returning dummy embeddings.")
            # Return fixed length dummy vector
            return [[0.1] * 384 for _ in texts]


class ChromaService:
    def __init__(self):
        os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.embedding_fn = AIFlowEmbeddingFunction()
        self.collection_name = "aiflow_documents"
        
        # Initialize collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn
        )
        # Initialize semantic cache collection
        self.cache_collection = self.client.get_or_create_collection(
            name="aiflow_cache",
            embedding_function=self.embedding_fn
        )
        logger.info(f"ChromaDB persistent collection '{self.collection_name}' initialized.")

    def add_chunks(self, texts: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """
        Inserts document text chunks with metadata.
        """
        try:
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Successfully added {len(texts)} chunks to ChromaDB.")
        except Exception as e:
            logger.error(f"ChromaDB insert failed: {e}")
            raise e

    def query_similarity(self, query: str, limit: int = 5, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Queries ChromaDB for top similarity matches.
        """
        try:
            kwargs = {}
            if filter_dict:
                kwargs["where"] = filter_dict
                
            results = self.collection.query(
                query_texts=[query],
                n_results=limit,
                **kwargs
            )
            
            formatted_results = []
            if results and results["documents"]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)
                distances = results["distances"][0] if results["distances"] else [0.0] * len(documents)
                ids = results["ids"][0]
                
                for idx in range(len(documents)):
                    formatted_results.append({
                        "id": ids[idx],
                        "document": documents[idx],
                        "metadata": metadatas[idx],
                        "distance": float(distances[idx])
                    })
            return formatted_results
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

    def delete_by_document(self, document_id: int):
        """
        Removes all vector chunks belonging to a PostgreSQL document ID.
        """
        try:
            self.collection.delete(where={"document_id": document_id})
            logger.info(f"Deleted vector chunks matching document_id: {document_id}")
        except Exception as e:
            logger.error(f"ChromaDB delete failed: {e}")

    def get_semantic_cache(self, query: str, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves semantically similar queries and responses from cache.
        Returns the response dictionary if a close match is found.
        """
        import json
        try:
            results = self.cache_collection.query(
                query_texts=[query],
                n_results=1,
                where={"user_id": user_id}
            )
            if results and results["documents"] and len(results["documents"][0]) > 0:
                distance = results["distances"][0][0]
                # Distance threshold of 0.15 indicates highly identical/similar semantically
                if distance < 0.15:
                    cached_metadata = results["metadatas"][0][0]
                    response_json = cached_metadata.get("response_payload")
                    if response_json:
                        logger.info(f"ChromaDB semantic cache hit! Distance: {distance:.4f}")
                        return json.loads(response_json)
        except Exception as e:
            logger.error(f"Semantic cache lookup failed: {e}")
        return None

    def set_semantic_cache(self, query: str, response_payload: Dict[str, Any], user_id: int):
        """
        Saves a query and its response payload in the semantic cache.
        """
        import json
        import uuid
        try:
            doc_id = str(uuid.uuid4())
            self.cache_collection.add(
                documents=[query],
                metadatas=[{
                    "user_id": user_id,
                    "response_payload": json.dumps(response_payload)
                }],
                ids=[doc_id]
            )
            logger.info("Successfully cached query and response in ChromaDB.")
        except Exception as e:
            logger.error(f"ChromaDB semantic cache insert failed: {e}")

# Global service instance
chroma_service = ChromaService()
