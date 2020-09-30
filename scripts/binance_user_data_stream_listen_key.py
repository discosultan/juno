import asyncio

# from juno import ExchangeException
from juno.config import from_env, init_instance
from juno.exchanges import Binance


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        spot_stream = await client._get_user_data_stream('spot')
        spot_listen_key1 = (await spot_stream._create_listen_key()).data['listenKey']
        spot_listen_key2 = (await spot_stream._create_listen_key()).data['listenKey']
        await spot_stream._update_listen_key(spot_listen_key2)
        await spot_stream._update_listen_key(spot_listen_key1)
        # CAREFUL!! This may delete a listen key to active Juno instance if it's tied to the same
        # account.
        # await client._user_data_stream._delete_listen_key(listen_key2)
        # try:
        #     await client._user_data_stream._update_listen_key(listen_key1)
        # except ExchangeException:
        #     pass
        # await client._user_data_stream._delete_listen_key(listen_key1)

        isolated_stream = await client._get_user_data_stream('eth-btc')
        isolated_listen_key = (await isolated_stream._create_listen_key()).data['listenKey']
        await isolated_stream._update_listen_key(isolated_listen_key)


asyncio.run(main())
