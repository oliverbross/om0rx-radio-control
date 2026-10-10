from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.static_files import setup_static_files


def test_fingerprinted_assets_are_cached_but_html_is_revalidated():
    app = FastAPI()
    setup_static_files(app)

    with TestClient(app) as client:
        html = client.get("/")
        versioned = client.get("/main-styles.css?v=webui-test")
        unversioned = client.get("/main-styles.css")
        vendor = client.get("/static/vendor/vue/vue.global.prod.js?v=webui-test")

    assert html.status_code == 200
    assert html.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert vendor.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert unversioned.headers["cache-control"] == "no-cache"
