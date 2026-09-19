from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ulpin:ulpin@localhost:5433/ulpin3d"
    demo_dir: str = "/data/demo"
    upload_dir: str = "/data/uploads"
    max_upload_bytes: int = 64 * 1024 * 1024
    processor_ver: str = "0.2.0-classical"


settings = Settings()
