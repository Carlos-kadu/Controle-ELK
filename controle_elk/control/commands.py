import asyncio
import math

from ..ble import protocol, transport
from . import gradient

COMMANDS = (
    "ligar",
    "desligar",
    "cor",
    "brilho",
    "efeito",
    "velocidade",
    "sequencia",
    "gradiente",
)
HELP = (
    "ligar | desligar | cor FF6600 | brilho 70 | efeito degrade-rgb | "
    "velocidade 50 | sequencia FF0000:2 00FF00:1 [loop] | "
    "gradiente FF0000[:2] 0000FF:4 00FF00:3 [loop] | efeitos"
)


def integer(args, low, high):
    if len(args) == 1:
        try:
            value = int(args[0])
        except ValueError:
            pass
        else:
            if low <= value <= high:
                return value
    raise ValueError(f"Informe um inteiro de {low} a {high}.")


def timed_color(step):
    value, separator, seconds = step.partition(":")
    if not separator:
        raise ValueError("Use COR:SEGUNDOS para informar a cor e a duração.")
    duration = float(seconds)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("A duração da etapa deve ser positiva e finita.")
    return protocol.parse_rgb(value), duration


def packets(action, args, profile):
    match action, args:
        case "ligar", []:
            packet = profile.power(True)
        case "desligar", []:
            packet = profile.power(False)
        case "cor", [value]:
            packet = profile.color(protocol.parse_rgb(value))
        case "brilho", _:
            packet = profile.brightness(integer(args, 1, 100))
        case "efeito", [name] if name in protocol.EFFECTS:
            packet = profile.effect(name)
        case "velocidade", _:
            packet = profile.speed(integer(args, 0, profile.max_speed))
        case _:
            raise ValueError(f"Comando inválido. {HELP}")
    return [(packet, 0)]


async def send_packets(send, steps):
    for packet, duration in steps:
        await send(packet)
        await asyncio.sleep(max(0, duration - transport.WRITE_INTERVAL))


def parse_gradient(args):
    repeat = bool(args and args[-1].lower() == "loop")
    colors = args[:-1] if repeat else args
    if len(colors) < 2:
        raise ValueError("Use gradiente COR_INICIAL COR_DESTINO:SEGUNDOS.")
    first_color, separator, _ = colors[0].partition(":")
    if repeat and separator:
        start, return_duration = timed_color(colors[0])
    else:
        start, return_duration = protocol.parse_rgb(first_color), None
    stops = [timed_color(step) for step in colors[1:]]
    if repeat and stops[-1][0] != start:
        stops.append((start, return_duration or stops[-1][1]))
    return start, stops, repeat


def parse_sequence(args):
    repeat = bool(args and args[-1].lower() == "loop")
    steps = args[:-1] if repeat else args
    if not steps:
        raise ValueError("Informe pelo menos uma cor e seu tempo.")
    return [timed_color(step) for step in steps], repeat


def prepare(action, args, profile):
    if action == "sequencia":
        colors, repeat = parse_sequence(args)
        sequence = [(profile.color(rgb), seconds) for rgb, seconds in colors]

        async def play_sequence(send):
            while True:
                for packet, seconds in sequence:
                    await send(packet, settle=False)
                    await asyncio.sleep(seconds)
                if not repeat:
                    return

        return play_sequence

    if action != "gradiente":
        steps = packets(action, args, profile)
        return lambda send: send_packets(send, steps)

    start, stops, repeat = parse_gradient(args)
    initial_packet = profile.color(start)
    steps = []
    current = start
    for end, seconds in stops:
        steps.extend(
            (delay, profile.color(rgb) if rgb is not None else None)
            for delay, rgb in gradient.changes(current, end, seconds)
        )
        current = end

    async def play(send):
        clock = asyncio.get_running_loop().time
        frame_time = clock()
        await send(initial_packet, settle=False)
        while True:
            for delay, packet in steps:
                await asyncio.sleep(max(0, delay - (clock() - frame_time)))
                frame_time = clock()
                if packet is not None:
                    await send(packet, settle=False)
            if not repeat:
                await asyncio.sleep(transport.WRITE_INTERVAL)
                return

    return play
