from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    azure_openai_endpoint:str
    azure_openai_deployment: str 
    ollama_model: str 
  
    postgres_dsn: str 

    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None
    

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()