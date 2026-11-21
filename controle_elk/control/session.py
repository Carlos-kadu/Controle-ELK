import asyncio
from contextlib import AsyncExitStack

from ..ble import transport
from ..storage.preferences import SavedDevice
from .commands import prepare


class DesktopConnection:
    def __init__(self):
        self.connection = AsyncExitStack()
        self.send = None
        self.profile = None
        self.animation = None
        self.animation_writes = asyncio.Lock()

    async def connect(self, target, profile, on_disconnect=None):
        await self.disconnect()
        if isinstance(target, SavedDevice):
            discovered = await transport.discover(target.address)
            if not discovered or discovered[0].model != target.model:
                raise RuntimeError(
                    "A fita salva não apareceu. Confira se está ligada e ao alcance."
                )
            target = discovered[0]

        def disconnected(_):
            if self.send is not None and on_disconnect is not None:
                on_disconnect()

        self.send = await self.connection.enter_async_context(
            transport.connect(target, disconnected)
        )
        self.profile = profile

    def cancel_animation(self):
        animation = self.animation
        if (
            animation is not None
            and not animation.done()
            and not animation.cancelling()
        ):
            animation.cancel()
        return animation

    async def stop(self):
        animation = self.cancel_animation()
        if animation is not None and not animation.done():
            await asyncio.gather(animation, return_exceptions=True)

    async def disconnect(self):
        await self.stop()
        self.send = None
        self.profile = None
        await self.connection.aclose()

    async def reconnect(self, target, profile, on_disconnect):
        from bleak.exc import BleakError

        for delay in (0, 1, 2):
            await asyncio.sleep(delay)
            try:
                await self.connect(target, profile, on_disconnect)
            except (BleakError, OSError, RuntimeError):
                continue
            return
        raise RuntimeError("A fita não respondeu após 3 tentativas.")

    async def command(self, action, values, *, on_started=None):
        if self.send is None:
            raise RuntimeError("Conecte uma fita primeiro.")
        play = prepare(action, values, self.profile)
        if action == "desligar":
            self.cancel_animation()
            await play(self.send)
            return
        if (
            action == "brilho"
            and self.animation is not None
            and not self.animation.done()
            and not self.animation.cancelling()
        ):
            await play(self.send_during_animation)
            return
        await self.stop()
        if action in ("gradiente", "sequencia"):

            async def send_frame(packet, *, settle=False):
                nonlocal on_started
                await self.send_during_animation(packet, settle=settle)
                if on_started:
                    callback, on_started = on_started, None
                    callback()

            send = send_frame if on_started else self.send_during_animation
            self.animation = asyncio.create_task(play(send))
            await self.animation
        else:
            await play(self.send)

    async def send_during_animation(self, packet, *, settle=False):
        async with self.animation_writes:
            await self.send(packet, settle=settle)


async def command_group(connections, action, values, *, on_started=None):
    remaining = len(connections) if on_started else 0

    def first_frame():
        nonlocal remaining
        remaining -= 1
        if remaining == 0:
            on_started()

    async def send_to(label, connection):
        try:
            if on_started:
                await connection.command(action, values, on_started=first_frame)
            else:
                await connection.command(action, values)
        except Exception as error:
            raise RuntimeError(f"{label}: {error}") from error

    try:
        async with asyncio.TaskGroup() as tasks:
            for label, connection in connections:
                tasks.create_task(send_to(label, connection))
    except ExceptionGroup as error:
        raise RuntimeError(str(error.exceptions[0])) from error
