import asyncio

# from juno import ExchangeException
from juno.config import from_env, init_instance
from juno.exchanges import Binance


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        listen_key1 = (await client._user_data_stream._create_listen_key()).data['listenKey']
        listen_key2 = (await client._user_data_stream._create_listen_key()).data['listenKey']
        await client._user_data_stream._update_listen_key(listen_key2)
        await client._user_data_stream._update_listen_key(listen_key1)
        # CAREFUL!! This may delete a listen key to active Juno instance if it's tied to the same
        # account.
        # await client._user_data_stream._delete_listen_key(listen_key2)
        # try:
        #     await client._user_data_stream._update_listen_key(listen_key1)
        # except ExchangeException:
        #     pass
        # await client._user_data_stream._delete_listen_key(listen_key1)


asyncio.run(main())
