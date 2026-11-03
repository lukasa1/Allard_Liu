import base64
import os
import tempfile
from io import BytesIO

# Isolate every test run: its own data dir and vault key, set before poa_skill is imported.
os.environ["POA_DATA_DIR"] = tempfile.mkdtemp(prefix="poa-test-")
os.environ.pop("POA_VAULT_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)

import pytest
from PIL import Image, ImageDraw

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
