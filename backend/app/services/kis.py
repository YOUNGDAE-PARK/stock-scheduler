import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from ..config import Settings, get_settings


class KisApiError(RuntimeError):
    pass


@dataclass
class KisToken:
    access_token: str
    token_type: str
    expires_at: float


class KisClient:
    DOMESTIC_MULTPRICE_MAX_TICKERS = 30

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None,
        token_expiry_margin_seconds: int = 300,
    ):
        self.settings = settings or get_settings()
        self.http_client = http_client or httpx.Client(timeout=20)
        self.token_expiry_margin_seconds = token_expiry_margin_seconds
        self._token: Optional[KisToken] = None
        self._token_lock = threading.Lock()

    def get_access_token(self, force_refresh: bool = False) -> str:
        with self._token_lock:
            if not force_refresh and self._token and self._token.expires_at > time.time():
                return self._token.access_token

            response = self.http_client.post(
                self.settings.kis_token_url,
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "grant_type": self.settings.kis_grant_type,
                    "appkey": self.settings.kis_app_key,
                    "appsecret": self.settings.kis_app_secret,
                },
            )
            body = self._json_body(response)
            token = body.get("access_token")
            if response.status_code != 200 or not token:
                raise KisApiError(self._error_message("KIS token issue failed", response, body))

            expires_in = int(body.get("expires_in") or 86400)
            expires_at = time.time() + max(0, expires_in - self.token_expiry_margin_seconds)
            self._token = KisToken(
                access_token=token,
                token_type=body.get("token_type") or "Bearer",
                expires_at=expires_at,
            )
            return token

    def invalidate_token(self) -> None:
        with self._token_lock:
            self._token = None

    def request(self, method: str, path: str, *, retry_on_auth_error: bool = True, **kwargs: Any) -> httpx.Response:
        response = self._authorized_request(method, path, **kwargs)
        if retry_on_auth_error and self._is_token_error(response):
            self.invalidate_token()
            response = self._authorized_request(method, path, force_refresh_token=True, **kwargs)
        return response

    def inquire_domestic_price(self, ticker: str) -> Dict[str, Any]:
        response = self.request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={"tr_id": "FHKST01010100", "custtype": "P"},
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        body = self._json_body(response)
        if response.status_code != 200 or body.get("rt_cd") != "0":
            raise KisApiError(self._error_message("KIS domestic price request failed", response, body))
        return body

    def inquire_domestic_prices(self, tickers: List[str], market_div_code: str = "J") -> Dict[str, Any]:
        cleaned_tickers = [ticker.strip() for ticker in tickers if ticker and ticker.strip()]
        if not cleaned_tickers:
            raise ValueError("tickers must contain at least one ticker")

        outputs = []
        raw_chunks = []
        for chunk in self._chunks(cleaned_tickers, self.DOMESTIC_MULTPRICE_MAX_TICKERS):
            body = self._request_domestic_multprice_chunk(chunk, market_div_code)
            raw_chunks.append(body)
            output = body.get("output") or []
            if isinstance(output, list):
                outputs.extend(output)
            elif isinstance(output, dict):
                outputs.append(output)

        return {
            "rt_cd": "0",
            "msg_cd": raw_chunks[-1].get("msg_cd", "") if raw_chunks else "",
            "msg1": raw_chunks[-1].get("msg1", "") if raw_chunks else "",
            "items": [self._normalize_domestic_multprice_row(row) for row in outputs],
            "output": outputs,
            "chunks": len(raw_chunks),
            "requested_tickers": cleaned_tickers,
        }

    def _normalize_domestic_multprice_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ticker": row.get("inter_shrn_iscd", ""),
            "name": row.get("inter_kor_isnm", ""),
            "current_price": row.get("inter2_prpr", ""),
            "previous_close": row.get("inter2_prdy_clpr", ""),
            "change": row.get("inter2_prdy_vrss", ""),
            "change_rate": row.get("prdy_ctrt", ""),
            "volume": row.get("acml_vol", ""),
            "raw": row,
        }

    def _request_domestic_multprice_chunk(self, tickers: List[str], market_div_code: str) -> Dict[str, Any]:
        params = {}
        for index, ticker in enumerate(tickers, start=1):
            params[f"FID_COND_MRKT_DIV_CODE_{index}"] = market_div_code
            params[f"FID_INPUT_ISCD_{index}"] = ticker

        response = self.request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/intstock-multprice",
            headers={"tr_id": "FHKST11300006", "custtype": "P"},
            params=params,
        )
        body = self._json_body(response)
        if response.status_code != 200 or body.get("rt_cd") != "0":
            raise KisApiError(self._error_message("KIS domestic multi price request failed", response, body))
        return body

    def _chunks(self, values: List[str], size: int) -> List[List[str]]:
        return [values[index : index + size] for index in range(0, len(values), size)]

    def _authorized_request(
        self,
        method: str,
        path: str,
        *,
        force_refresh_token: bool = False,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        token = self.get_access_token(force_refresh=force_refresh_token)
        request_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
        }
        if headers:
            request_headers.update(headers)

        url = path if path.startswith("http") else f"{self.settings.kis_base_url}{path}"
        return self.http_client.request(method, url, headers=request_headers, **kwargs)

    def _is_token_error(self, response: httpx.Response) -> bool:
        if response.status_code == 401:
            return True
        if response.status_code not in {400, 403}:
            return False

        body = self._json_body(response)
        message = " ".join(str(body.get(key, "")) for key in ("error_description", "msg1", "msg_cd"))
        return "token" in message.lower() or "토큰" in message

    def _json_body(self, response: httpx.Response) -> Dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _error_message(self, prefix: str, response: httpx.Response, body: Dict[str, Any]) -> str:
        detail = body.get("error_description") or body.get("msg1") or response.text[:200]
        return f"{prefix}: HTTP {response.status_code} {detail}".strip()


_kis_client: Optional[KisClient] = None
_kis_client_lock = threading.Lock()


def get_kis_client() -> KisClient:
    global _kis_client
    with _kis_client_lock:
        if _kis_client is None:
            _kis_client = KisClient()
        return _kis_client


def reset_kis_client() -> None:
    global _kis_client
    with _kis_client_lock:
        if _kis_client is not None:
            _kis_client.http_client.close()
        _kis_client = None
