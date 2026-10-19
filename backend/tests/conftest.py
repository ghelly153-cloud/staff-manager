import os, sys, shutil, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.fixtures import build
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

H = {"X-Requested-With": "emp-app"}

@pytest.fixture
def env(tmp_path):
    p = tmp_path / "wb.xlsx"; build(str(p))
    s = Settings(source="local", local_workbook_path=str(p), dev_auth=True, data_dir=str(tmp_path / "data"))
    app = create_app(s, run_background=False)
    app.state.sync.refresh(force=True)
    c = TestClient(app)
    def login(role):
        c.cookies.clear(); assert c.post("/auth/dev-login", json={"role": role}, headers=H).status_code == 200
    login("admin")
    class E: pass
    e = E(); e.c, e.app, e.path, e.login, e.sync, e.svc, e.s = c, app, str(p), login, app.state.sync, app.state.svc, s
    return e
