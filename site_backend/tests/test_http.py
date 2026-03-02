from app.http import ok, page_meta


def test_ok_with_meta():
    payload = ok({'x': 1}, limit=10, offset=0)
    assert payload['ok'] is True
    assert payload['data'] == {'x': 1}
    assert payload['meta'] == {'limit': 10, 'offset': 0}


def test_page_meta_with_total():
    meta = page_meta(limit=50, offset=100, total=999)
    assert meta == {'limit': 50, 'offset': 100, 'total': 999}
