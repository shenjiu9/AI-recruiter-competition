from app.bootstrap import build_container
from app.interfaces.api.app import create_api
from app.platform.settings import Settings


def create_app():
    return create_api(build_container(Settings()))
