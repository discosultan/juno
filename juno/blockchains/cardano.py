from __future__ import annotations

from types import TracebackType
from typing import Any, Literal, Optional, TypedDict

from juno.http import ClientResponse, ClientSession


class SyncProgress(TypedDict):
    status: Literal["ready"]
    # ...


class Epoch(TypedDict):
    epoch_number: int
    epoch_start_time: str


class NetworkInformation(TypedDict):
    sync_progress: SyncProgress
    next_epoch: Epoch


class CreateTransactionResult(TypedDict):
    status: Literal["pending"]
    # ...


class Cardano:
    def __init__(self, url: str = "http://localhost:8090") -> None:
        self._url = url
        self._session = ClientSession(
            name=type(self).__name__,
            raise_for_status=True,
        )

    async def __aenter__(self) -> Cardano:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_network_information(self) -> NetworkInformation:
        return await self._request_json("GET", "/v2/network/information")

    async def list_wallets(self) -> list[Any]:
        return await self._request_json("GET", "/v2/wallets")

    async def create_wallet(self, name: str, mnemonic24: list[str], passphrase: str) -> Any:
        if len(mnemonic24) != 24:
            raise ValueError("Mnemonic must be 24 words.")

        return await self._request_json(
            "POST",
            "/v2/wallets",
            {
                "name": name,
                "mnemonic_sentence": mnemonic24,
                "mnemonic_second_factor": None,
                "passphrase": passphrase,
            },
        )

    async def get_wallet(self, wallet_id: str) -> Any:
        return await self._request_json("GET", f"/v2/wallets/{wallet_id}")

    async def delete_wallet(self, wallet_id: str) -> None:
        await self._request("DELETE", f"/v2/wallets/{wallet_id}")

    async def list_wallet_addresses(self, wallet_id: str) -> list[Any]:
        return await self._request_json("GET", f"/v2/wallets/{wallet_id}/addresses")

    async def create_transaction(
        self, wallet_id: str, passphrase: str, address: str, lovelaces: int
    ) -> CreateTransactionResult:
        return await self._request_json(
            "POST",
            f"/v2/wallets/{wallet_id}/transactions",
            {
                "passphrase": passphrase,
                "payments": [
                    {
                        "address": address,
                        "amount": {"quantity": lovelaces, "unit": "lovelace"},
                        "assets": [],
                    }
                ],
                "withdrawal": "self",
                "metadata": None,
                "time_to_live": {"quantity": 200, "unit": "second"},
            },
        )

    async def _request_json(self, method: str, url: str, json: Any = None) -> Any:
        response = await self._request(method, url, json)
        return await response.json()

    async def _request(self, method: str, url: str, json: Any = None) -> ClientResponse:
        async with self._session.request(
            method=method, url=self._url + url, json=json
        ) as response:
            return response
