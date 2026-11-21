import json

from ..ble import protocol
from ..storage.paths import data_directory

ACTIONS = {
    "ligar": "Ligar",
    "desligar": "Desligar",
    "conectar": "Conectar",
    "gradiente": "Reproduzir ou parar o gradiente",
    "efeito": "Efeito de fábrica",
    "cor": "Cor sólida",
    "proxima_cor": "Próxima cor padrão",
    "sequencia": "Reproduzir ou parar a sequência",
}
DEFAULT_KEYS = {"ligar": "F9", "desligar": "F10", "conectar": "F11"}
DEFAULT_OPTIONS = {"efeito": "degrade-rgb", "cor": "#FF0000", "mostrar_aviso": True}
MODIFIERS = {
    "Ctrl": 2,
    "Ctrl + Alt": 3,
    "Ctrl + Shift": 6,
    "Alt + Shift": 5,
    "Ctrl + Alt + Shift": 7,
}
KEYS = {chr(code): code for code in range(65, 91)}
KEYS.update({str(number): 48 + number for number in range(10)})
KEYS.update({f"F{number}": 111 + number for number in range(1, 12)})


def default_config():
    shortcuts = {action: ("Ctrl", DEFAULT_KEYS.get(action, "")) for action in ACTIONS}
    return False, shortcuts, DEFAULT_OPTIONS.copy()


def shortcut_options(options):
    effect = options.get("efeito", DEFAULT_OPTIONS["efeito"])
    if effect not in protocol.EFFECTS:
        raise ValueError("Escolha um efeito de fábrica.")
    color = protocol.parse_rgb(options.get("cor", DEFAULT_OPTIONS["cor"]))
    show_notice = options.get("mostrar_aviso", DEFAULT_OPTIONS["mostrar_aviso"])
    if not isinstance(show_notice, bool):
        raise ValueError("Escolha se o aviso deve aparecer na tela.")
    return {
        "efeito": effect,
        "cor": "#" + color.hex().upper(),
        "mostrar_aviso": show_notice,
    }


def bindings(config):
    enabled, shortcuts, _ = config
    if not enabled:
        return {}
    result = {}
    for action, (modifier, key) in shortcuts.items():
        if not key:
            continue
        pair = MODIFIERS[modifier] | 0x4000, KEYS[key]
        if pair in result.values():
            raise ValueError("Escolha uma combinação diferente para cada atalho.")
        result[action] = pair
    return result


def load_config():
    try:
        enabled, shortcuts, *saved_options = json.loads(
            (data_directory() / "atalhos.json").read_text(encoding="utf-8")
        )
        if not isinstance(enabled, bool) or not shortcuts.keys() <= ACTIONS.keys():
            raise ValueError
        for modifier, key in shortcuts.values():
            if modifier not in MODIFIERS or (key and key not in KEYS):
                raise ValueError
        _, defaults, options = default_config()
        if saved_options:
            options = shortcut_options(saved_options[0])
        config = enabled, defaults | shortcuts, options
        bindings(config)
        return config
    except (OSError, ValueError, TypeError, AttributeError):
        return default_config()


def save_config(config):
    path = data_directory() / "atalhos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config), encoding="utf-8")
    temporary.replace(path)
