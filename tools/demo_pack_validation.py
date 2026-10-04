"""Map the backend's shared pack validator to actionable launch errors."""

from backend.rooms.demo import validate_pack_assets
from tools.launch_support import LaunchError


def validate_demo_pack(pack):
    try:
        return validate_pack_assets(pack)
    except ValueError as error:
        raise LaunchError(str(error)) from None
