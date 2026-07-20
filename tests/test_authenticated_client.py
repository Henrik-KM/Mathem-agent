from mathem_agent.mathem import MathemClient


class Response:
    text = "ok"


def test_get_html_sends_saved_cookie(monkeypatch):
    client = MathemClient(cookie="sessionid=abc")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.get_html("/se/") == "ok"
    assert captured["headers"]["Cookie"] == "sessionid=abc"
