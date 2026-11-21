import argparse
import asyncio
import shlex
import sys

from .ble import protocol, transport
from .control.commands import COMMANDS, HELP, integer, prepare


def announce_loop(action, values):
    if action in ("gradiente", "sequencia") and values and values[-1].lower() == "loop":
        print("Reproduzindo em loop. Pressione Ctrl+C para parar.", flush=True)


def show_effects():
    print("\n".join(protocol.EFFECTS))


async def session(target, profile):
    async with transport.connect(target) as send:
        print(f"Conectado a {target.label}. Digite ajuda ou sair.", flush=True)
        while True:
            try:
                words = shlex.split(input("fita> "))
                match words:
                    case []:
                        continue
                    case ["sair"]:
                        return
                    case ["ajuda"]:
                        print(HELP)
                    case ["efeitos"]:
                        show_effects()
                    case [action, *args]:
                        play = prepare(action, args, profile)
                        announce_loop(action, args)
                        await play(send)
                        print("Comando enviado.")
            except ValueError as error:
                print(error)
            except EOFError:
                return


def choose(options, prompt):
    for index, (label, _) in enumerate(options, 1):
        print(f"{index}. {label}")
    while True:
        answer = input(prompt).strip()
        if answer == "0":
            return None
        try:
            return options[integer([answer], 1, len(options)) - 1][1]
        except ValueError as error:
            print(error)


def select_profile(target, variant):
    if target.model == protocol.MODEL:
        if variant is not None:
            raise ValueError("--variante se aplica à ELK-BLEDOM.")
        return protocol.BLEDOB_PROFILE
    if variant is not None:
        return protocol.BLEDOM_PROFILES[variant]
    if not sys.stdin.isatty():
        raise ValueError("Informe --variante 4 ou --variante 0 para a ELK-BLEDOM.")
    print("A ELK-BLEDOM tem duas variantes. Se a fita não responder, tente a outra.")
    return choose(
        [
            (f"Variante {key}", profile)
            for key, profile in protocol.BLEDOM_PROFILES.items()
        ],
        "Escolha a variante (0 para cancelar): ",
    )


async def run(args):
    if args.action == "efeitos":
        show_effects()
        return
    if not args.endereco:
        print("Buscando fitas Bluetooth compatíveis…", flush=True)
    targets = await transport.discover(args.endereco)
    if not targets:
        raise RuntimeError(
            "Nenhuma ELK-BLEDOB ou ELK-BLEDOM encontrada. Confira a alimentação e feche o app da fita."
        )
    if args.action == "buscar":
        for target in targets:
            print(target.label)
        return

    show_menu = not args.endereco and (args.action == "sessao" or len(targets) > 1)
    if show_menu and args.action != "sessao" and not sys.stdin.isatty():
        raise ValueError(
            "Mais de uma fita encontrada. Use buscar e informe --endereco."
        )
    target = targets[0]
    if show_menu:
        target = choose(
            [(item.label, item) for item in targets],
            "Escolha a fita (0 para cancelar): ",
        )
    if target is None:
        return
    profile = select_profile(target, args.variante)
    if profile is None:
        return
    if args.action == "sessao":
        await session(target, profile)
        return
    play = prepare(args.action, args.values, profile)
    async with transport.connect(target) as send:
        announce_loop(args.action, args.values)
        await play(send)
    print(f"Comando {args.action} enviado para {target.label}.")


def main():
    parser = argparse.ArgumentParser(
        description="Controle Bluetooth de fitas ELK-BLEDOB e ELK-BLEDOM.", epilog=HELP
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="sessao",
        choices=("buscar", "efeitos", "sessao", "interface", *COMMANDS),
    )
    parser.add_argument("values", nargs="*")
    parser.add_argument(
        "--endereco", help="Conecta diretamente ao endereço BLE indicado."
    )
    parser.add_argument(
        "--variante",
        choices=protocol.BLEDOM_PROFILES,
        help="Variante do protocolo ELK-BLEDOM.",
    )
    parser.add_argument(
        "--minimizado",
        action="store_true",
        help="Abre a interface na bandeja do Windows.",
    )
    args = parser.parse_intermixed_args()
    if args.action == "interface":
        if args.values or args.endereco or args.variante:
            parser.error("Escolha o endereço e a variante dentro da interface.")
        from .ui.launch import main as desktop_main

        desktop_main(["--minimizado"] if args.minimizado else [])
        return
    if args.minimizado:
        parser.error("--minimizado se aplica à interface.")
    if args.values and args.action in ("buscar", "efeitos", "sessao"):
        parser.error(f"{args.action} não recebe valores posicionais.")
    from bleak.exc import BleakError

    try:
        asyncio.run(run(args))
    except (BleakError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Erro: {error}\n")
    except EOFError:
        parser.exit(
            1, "Seleção encerrada. Informe --endereco para conectar diretamente.\n"
        )
    except KeyboardInterrupt:
        parser.exit(130, "\nControle interrompido.\n")


if __name__ == "__main__":
    main()
