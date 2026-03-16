# kilowahti-py

Pure-Python library for Nordic/Baltic electricity spot pricing. Powers the [Kilowahti](https://github.com/Kilowahti/ha-kilowahti) Home Assistant integration and can be used independently in any Python project.

## Installation

```bash
pip install kilowahti
```

Requires Python 3.12+ and aiohttp 3.9+.

## Quick example

```python
import asyncio
import aiohttp
from kilowahti import SpotHintaSource, PriceResolution, spot_effective

async def main():
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_today(session, region="FI", resolution=PriceResolution.HOUR)

    vat_rate = 0.255  # 25.5% Finnish VAT
    for slot in slots:
        price = spot_effective(slot, vat_rate=vat_rate, commission=0.0)
        print(f"{slot.dt_utc.strftime('%H:%M')}  rank {slot.rank:2d}  {price:.2f} c/kWh")

asyncio.run(main())
```

## What's in the box

| Module | Contents |
|--------|----------|
| `kilowahti.models` | Data classes: `PriceSlot`, `TransferGroup`, `FixedPeriod`, `ScoreProfile`, … |
| `kilowahti.calc` | Pure calculation functions — pricing, ranking, control factors, scoring |
| `kilowahti.sources` | `PriceSource` ABC and `SpotHintaSource` (spot-hinta.fi) implementation |
| `kilowahti.const` | API URLs, region list, country VAT presets, unit constants |

Everything public is re-exported from the top-level `kilowahti` namespace:

```python
from kilowahti import PriceSlot, SpotHintaSource, cheapest_window, COUNTRY_PRESETS
```

## Supported regions

`FI`, `EE`, `LT`, `LV`, `DK1`, `DK2`, `NO1`–`NO5`, `SE1`–`SE4`

## Documentation

Full API reference at [docs.kilowahti.fi/lib](https://docs.kilowahti.fi/lib/)

## License

MIT — see [LICENSE](LICENSE)
