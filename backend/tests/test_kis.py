import httpx


def make_settings():
    from backend.app.config import Settings

    return Settings(
        KIS_ENV="virtual",
        KIS_VIRTUAL_APP_KEY="virtual-key",
        KIS_VIRTUAL_APP_SECRET="virtual-secret",
    )


def test_access_token_is_reused_until_expiry():
    from backend.app.services.kis import KisClient

    calls = {"token": 0, "quote": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "token-1", "token_type": "Bearer", "expires_in": 86400})
        calls["quote"] += 1
        return httpx.Response(200, json={"rt_cd": "0", "output": {"stck_prpr": "216000"}})

    client = KisClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.inquire_domestic_price("005930")
    client.inquire_domestic_price("005930")

    assert calls == {"token": 1, "quote": 2}


def test_token_error_invalidates_and_retries_once():
    from backend.app.services.kis import KisClient

    calls = {"token": 0, "quote": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            calls["token"] += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{calls['token']}",
                    "token_type": "Bearer",
                    "expires_in": 86400,
                },
            )

        calls["quote"] += 1
        if calls["quote"] == 1:
            return httpx.Response(401, json={"msg1": "기간이 만료된 토큰입니다."})
        return httpx.Response(200, json={"rt_cd": "0", "output": {"stck_prpr": "216000"}})

    client = KisClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    body = client.inquire_domestic_price("005930")

    assert body["output"]["stck_prpr"] == "216000"
    assert calls == {"token": 2, "quote": 2}


def test_domestic_multi_price_uses_intstock_multprice_api():
    from backend.app.services.kis import KisClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json={"access_token": "token-1", "token_type": "Bearer", "expires_in": 86400})

        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        captured["tr_id"] = request.headers.get("tr_id")
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "msg_cd": "MCA00000",
                "msg1": "정상처리 되었습니다.",
                "output": [
                    {"inter_shrn_iscd": "005930", "inter_kor_isnm": "삼성전자", "inter2_prpr": "216000"},
                    {"inter_shrn_iscd": "000660", "inter_kor_isnm": "SK하이닉스", "inter2_prpr": "310000"},
                ],
            },
        )

    client = KisClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    body = client.inquire_domestic_prices(["005930", "000660"])

    assert captured["path"] == "/uapi/domestic-stock/v1/quotations/intstock-multprice"
    assert captured["tr_id"] == "FHKST11300006"
    assert captured["query"]["FID_COND_MRKT_DIV_CODE_1"] == "J"
    assert captured["query"]["FID_INPUT_ISCD_1"] == "005930"
    assert captured["query"]["FID_COND_MRKT_DIV_CODE_2"] == "J"
    assert captured["query"]["FID_INPUT_ISCD_2"] == "000660"
    assert body["chunks"] == 1
    assert body["requested_tickers"] == ["005930", "000660"]
    assert len(body["output"]) == 2
    assert body["items"][0]["ticker"] == "005930"
    assert body["items"][0]["name"] == "삼성전자"
    assert body["items"][0]["current_price"] == "216000"


def test_domestic_multi_price_chunks_more_than_thirty_tickers():
    from backend.app.services.kis import KisClient

    quote_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json={"access_token": "token-1", "token_type": "Bearer", "expires_in": 86400})

        quote_calls.append(dict(request.url.params))
        return httpx.Response(200, json={"rt_cd": "0", "msg1": "정상처리 되었습니다.", "output": []})

    client = KisClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    body = client.inquire_domestic_prices([f"{index:06d}" for index in range(31)])

    assert body["chunks"] == 2
    assert len(quote_calls) == 2
    assert "FID_INPUT_ISCD_30" in quote_calls[0]
    assert "FID_INPUT_ISCD_31" not in quote_calls[0]
    assert quote_calls[1]["FID_INPUT_ISCD_1"] == "000030"
