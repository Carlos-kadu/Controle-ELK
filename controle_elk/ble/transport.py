from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .protocol import MODELS, WRITE_UUID

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

WRITE_INTERVAL = 0.1


@dataclass(frozen=True)
class Target:
    device: BLEDevice
    model: str

    @property
    def label(self):
        return f"{self.model}  {self.device.address}"


def identify(device, advertisement):
    for name in (advertisement.local_name, device.name):
        if name and name.upper() in MODELS:
            return Target(device, name.upper())
    return None


async def discover(address=None):
    from bleak import BleakScanner

    if address:
        result = None

        def matches(device, advertisement):
            nonlocal result
            if device.address.upper() == address.upper():
                result = identify(device, advertisement)
            return result is not None

        await BleakScanner.find_device_by_filter(matches, timeout=8)
        return [result] if result else []

    devices = await BleakScanner.discover(timeout=8, return_adv=True)
    targets = (
        identify(device, advertisement) for device, advertisement in devices.values()
    )
    return sorted(
        (target for target in targets if target), key=lambda target: target.label
    )


@asynccontextmanager
async def connect(target, disconnected_callback=None):
    from bleak import BleakClient

    async with BleakClient(
        target.device, timeout=15, disconnected_callback=disconnected_callback
    ) as client:
        characteristic = client.services.get_characteristic(WRITE_UUID)
        if (
            characteristic is None
            or "write-without-response" not in characteristic.properties
        ):
            raise RuntimeError(
                "A fita não expôs a característica FFF3 com escrita sem resposta."
            )

        async def send(packet, *, settle=True):
            await client.write_gatt_char(characteristic, packet, response=False)
            if settle:
                await asyncio.sleep(WRITE_INTERVAL)

        yield send
