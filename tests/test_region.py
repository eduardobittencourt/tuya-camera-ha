import sys
from pathlib import Path
from types import ModuleType

package = ModuleType("custom_components.tuya_camera_bridge")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "tuya_camera_bridge")
]
sys.modules["custom_components.tuya_camera_bridge"] = package

from custom_components.tuya_camera_bridge.region import endpoint_for_country_code  # noqa: E402


def test_brazil_routes_to_american_data_center():
    assert endpoint_for_country_code("+55") == "https://a1.tuyaus.com/api.json"


def test_india_china_and_singapore_have_dedicated_routes():
    assert endpoint_for_country_code("91").endswith("tuyain.com/api.json")
    assert endpoint_for_country_code("86").endswith("tuyacn.com/api.json")
    assert endpoint_for_country_code("65").endswith("iotbing.com/api.json")


def test_europe_is_the_safe_default():
    assert endpoint_for_country_code("39") == "https://a1.tuyaeu.com/api.json"
