import base64
import os
import tempfile
from io import BytesIO

# Isolate every test run: its own data dir and vault key, set before poa_skill is imported.
os.environ["POA_DATA_DIR"] = tempfile.mkdtemp(prefix="poa-test-")
os.environ.pop("POA_VAULT_KEY", None)
# Empty (not unset) so a developer's .env can't switch tests to a live model: load_dotenv never
# overrides a variable that already exists.
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["DSPY_CACHE"] = "0"

import socket

import pytest
from PIL import Image, ImageDraw

_connect = socket.socket.connect


def _no_network(self, address):
    """Tests never reach a model or the web: only local sockets may connect."""
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and (host.startswith(("127.", "/")) or host in ("localhost", "::1")):
        return _connect(self, address)
    raise RuntimeError(f"network access in a test: {address!r} (inject a scripted LM / fake kb)")


socket.socket.connect = _no_network

SSN = "123-45-6789"
VETERAN = {
    "first_name": "Jordan",
    "middle_initial": "Q",
    "last_name": "Testveteran",
    "ssn": SSN,
    "date_of_birth": "1988-04-09",
    "branch": "marine_corps",
    "address.line1": "100 Main St",
    "address.city": "Milwaukee",
    "address.state": "Wisconsin",
    "address.zip": "53202",
    "phone": "414-555-0100",
    "email": "jordan@example.com",
}


@pytest.fixture
def signature_uri() -> str:
    img = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).line(
        [(40, 150), (200, 40), (360, 150), (560, 60)], fill=(19, 36, 70, 255), width=6
    )
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def svc(tmp_path):
    from poa_skill.service import PoaService

    return PoaService("test_session_" + tmp_path.name[-8:].replace(".", "_"), data_dir=tmp_path)


@pytest.fixture
def lm():
    from agent.scripted.lm import ScriptedLM

    return ScriptedLM()


@pytest.fixture
def rt(tmp_path, lm):
    """The runtime (orchestrator, intake, claims prep, support) on a fresh store,
    driven by the scripted LM. kb_search uses the offline FAQ: no test touches the network."""
    from agent.runtime import make_runtime
    from agent.scripted.kb import FaqKB

    yield make_runtime(tmp_path, lm, kb=FaqKB())
    assert lm.unused() == {}, f"scripted steps never used: {lm.unused()}"
