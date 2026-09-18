from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ulpin:ulpin@localhost:5433/ulpin3d"
    demo_dir: str = "/data/demo"
    processor_ver: str = "0.1.0-freeze"


settings = Settings()
