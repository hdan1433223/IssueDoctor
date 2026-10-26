from pathlib import Path

import pytest

from issuedoctor import create_app
from issuedoctor.config import Config


@pytest.fixture()
def app(tmp_path: Path):
    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        DATA_DIR = tmp_path
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"

    return create_app(TestConfig)


@pytest.fixture()
def client(app):
    return app.test_client()
