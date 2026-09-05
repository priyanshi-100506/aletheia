from http_client import upstream_status


class Response:
    status_code = 500

    def json(self):
        return {"error": "upstream unavailable"}


def test_server_error_uses_safe_fallback():
    assert upstream_status(Response()) == "unavailable"
