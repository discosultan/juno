import asyncio
from decimal import Decimal

import aiohttp


async def main() -> None:
    async with aiohttp.ClientSession() as client:
        async with client.get(
            'https://www.binance.com/gateway-api/v1/public/margin/vip/spec/list-all'
        ) as resp:
            res = await resp.json()
            for a in res['data']:
                s = a['specs'][0]
                an = a['assetName'].lower()
                ir = Decimal(s['dailyInterestRate']).normalize()
                bl = Decimal(s['borrowLimit']).normalize()
                print_row(an, ir, bl)


def print_row(an: str, ir: Decimal, bl: Decimal) -> None:
    # Do not use logging module here. We use output as codegen.
    print(f"'{an}': BorrowInfo(daily_interest_rate=Decimal('{ir}'), limit=Decimal('{bl}')),")


asyncio.run(main())
