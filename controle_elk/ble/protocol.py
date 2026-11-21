import re
from dataclasses import dataclass

MODEL = "ELK-BLEDOB"
BLEDOM = "ELK-BLEDOM"
MODELS = (MODEL, BLEDOM)
WRITE_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

EFFECTS = {
    "salto-rgb": 135,
    "salto-7-cores": 136,
    "degrade-rgb": 137,
    "degrade-7-cores": 138,
    "degrade-vermelho": 139,
    "degrade-verde": 140,
    "degrade-azul": 141,
    "degrade-amarelo": 142,
    "degrade-ciano": 143,
    "degrade-magenta": 144,
    "degrade-branco": 145,
    "degrade-vermelho-verde": 146,
    "degrade-vermelho-azul": 147,
    "degrade-verde-azul": 148,
    "pisca-7-cores": 149,
    "pisca-vermelho": 150,
    "pisca-verde": 151,
    "pisca-azul": 152,
    "pisca-amarelo": 153,
    "pisca-ciano": 154,
    "pisca-magenta": 155,
    "pisca-branco": 156,
}


@dataclass(frozen=True)
class Profile:
    power_prefix: int
    power_on: int
    power_suffix: tuple[int, int]
    color_prefix: int
    color_suffix: int
    brightness_prefix: int
    brightness_suffix: tuple[int, int, int, int]
    effect_values: tuple[int, int]
    max_speed: int

    def power(self, on: bool) -> bytes:
        return bytes(
            (
                0x7E,
                self.power_prefix,
                4,
                self.power_on if on else 0,
                0,
                int(on),
                *self.power_suffix,
                0xEF,
            )
        )

    def color(self, rgb: bytes) -> bytes:
        return bytes((0x7E, self.color_prefix, 5, 3, *rgb, self.color_suffix, 0xEF))

    def brightness(self, percent: int) -> bytes:
        return bytes(
            (0x7E, self.brightness_prefix, 1, percent, *self.brightness_suffix, 0xEF)
        )

    def effect(self, name: str) -> bytes:
        return bytes(
            (0x7E, self.color_prefix, 3, EFFECTS[name], 3, *self.effect_values, 0, 0xEF)
        )

    def speed(self, value: int) -> bytes:
        return bytes((0x7E, self.color_prefix, 2, value, 0, 0, 0, 0, 0xEF))


BLEDOB_PROFILE = Profile(7, 255, (2, 1), 7, 10, 4, (1, 255, 2, 1), (255, 255), 183)
BLEDOM_PROFILES = {
    "4": Profile(4, 240, (255, 0), 7, 10, 4, (1, 255, 2, 1), (255, 255), 255),
    "0": Profile(0, 240, (255, 0), 0, 0, 0, (255, 0, 255, 0), (0, 0), 255),
}


def parse_rgb(value: str) -> bytes:
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        raise ValueError("Use uma cor RGB de seis dígitos, por exemplo FF6600.")
    return bytes.fromhex(value.removeprefix("#"))
