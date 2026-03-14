import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.db import engine
from app.models import Base


def pytest_runtest_setup():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
