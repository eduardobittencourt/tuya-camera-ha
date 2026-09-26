"""Route a Tuya account to the same data center as its mobile-app country."""

US_CODES = {
    "1", "7", "51", "52", "53", "54", "55", "56", "57", "58",
    "501", "502", "503", "504", "505", "506", "507", "509", "591",
    "592", "593", "594", "595", "596", "597", "598", "599",
}
INDIA_CODES = {"91"}
CHINA_CODES = {"86"}
ASIA_PACIFIC_CODES = {
    "60", "61", "62", "63", "64", "65", "66", "81", "82", "84",
    "852", "853", "855", "856", "880", "886", "960", "961", "962",
    "963", "964", "965", "966", "967", "968", "970", "971", "972",
    "973", "974", "975", "976", "977", "992", "993", "994", "995",
    "996", "998",
}


def endpoint_for_country_code(country_code: str) -> str:
    """Return Tuya's mobile API endpoint for an international calling code."""
    code = country_code.strip().lstrip("+")
    if code in US_CODES:
        return "https://a1.tuyaus.com/api.json"
    if code in INDIA_CODES:
        return "https://a1.tuyain.com/api.json"
    if code in CHINA_CODES:
        return "https://a1.tuyacn.com/api.json"
    if code in ASIA_PACIFIC_CODES:
        return "https://a1-sg.iotbing.com/api.json"
    return "https://a1.tuyaeu.com/api.json"
