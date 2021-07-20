from __future__ import annotations

from types import TracebackType
from typing import Any, Optional

from juno.http import ClientResponse, ClientSession


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

    async def get_network_information(self) -> Any:
        return await self._request_json("GET", "/v2/network/information")

    async def list_wallets(self) -> list[Any]:
        return await self._request_json("GET", "/v2/wallets")

    async def create_wallet(self, name: str, mnemonic24: list[str], passphrase: str) -> Any:
        if len(mnemonic24) != 24:
            raise ValueError("Mnemonic must be 24 words.")

        mnemonic_sentence = mnemonic24[:15]
        mnemonic_second_factor = mnemonic24[15:]

        return await self._request_json(
            "POST",
            "/v2/wallets",
            {
                name: name,
                mnemonic_sentence: mnemonic_sentence,
                mnemonic_second_factor: mnemonic_second_factor,
                passphrase: passphrase,
            },
        )

    async def get_wallet(self, id_: str) -> Any:
        return await self._request_json("GET", f"/v2/wallets/{id_}")

    async def delete_wallet(self, id_: str) -> None:
        await self._request("DELETE", f"/v2/wallets/{id_}")

    async def list_wallet_addresses(self, id_: str) -> list[Any]:
        return await self._request_json("GET", f"/v2/wallets/{id_}/addresses")

    # TODO: Add send transaction.

    async def _request_json(self, method: str, url: str, json: Any = None) -> Any:
        response = await self._request(method, url, json)
        return await response.json()

    async def _request(self, method: str, url: str, json: Any = None) -> ClientResponse:
        async with self._session.request(
            method=method, url=self._url + url, json=json
        ) as response:
            return response
