import src.seestarpy.raw_commands
import src.seestarpy.status
from src.seestarpy import ui as cmds
from src.seestarpy import connection

connection.VERBOSE = False


def test_connection_command():
    payload = src.seestarpy.raw_commands.test_connection()
    assert "connected" in payload.get("result")

def test_get_coords():
    payload = src.seestarpy.status.get_coords()
    assert payload.get("ra") != 0

def test_get_deivce_state():
    payload = src.seestarpy.raw_commands.get_device_state()
    print(payload)
    assert payload["result"]["device"]["product_model"] == "Seestar S50"

def test_get_eq_mode():
    payload = cmds.get_eq_mode()
    assert payload["result"]["mount"]["equ_mode"] == False