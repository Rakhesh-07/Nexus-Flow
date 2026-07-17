import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "AIFlow - Enterprise Multi-Agent AI Workflow Orchestrator"
    
    # DB & Redis Config
    DATABASE_URL: str = Field(
        default="postgresql://aiflow_user:aiflow_secure_password_9988@localhost:5432/aiflow_db",
        env="DATABASE_URL"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        env="REDIS_URL"
    )
    
    # Chroma Config
    CHROMA_DB_PATH: str = Field(
        default="./chroma_db",
        env="CHROMA_DB_PATH"
    )
    
    # Security Config
    JWT_SECRET: str = Field(
        default="supersecretjwtsignkeyvalue1122334455",
        env="JWT_SECRET"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60,
        env="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    
    # LLM Config
    LLM_PROVIDER: str = Field(
        default="gemini",
        env="LLM_PROVIDER"
    )
    GEMINI_API_KEY: str = Field(
        default="",
        env="GEMINI_API_KEY"
    )
    
    # Default models
    GEMINI_MODEL: str = "gemini-2.0-flash"
    
    # Embeddings Config
    EMBEDDING_PROVIDER: str = Field(
        default="local", # Can be: "local", "gemini"
        env="EMBEDDING_PROVIDER"
    )
    EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2", # For local
        env="EMBEDDING_MODEL"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
