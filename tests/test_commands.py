import asyncio
import unittest
from unittest.mock import patch

from controle_elk.ble.protocol import BLEDOB_PROFILE
from controle_elk.control.commands import parse_gradient, prepare
from controle_elk.control.gradient import changes
from controle_elk.control.session import DesktopConnection


class GradientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequence_holds_each_color_and_restarts_without_interpolation(self):
        writes = []
        red = BLEDOB_PROFILE.color(bytes((255, 0, 0)))
        blue = BLEDOB_PROFILE.color(bytes((0, 0, 255)))

        async def send(packet, *, settle):
            self.assertFalse(settle)
            writes.append(packet)
            if len(writes) == 3:
                raise asyncio.CancelledError

        play = prepare("sequencia", ["FF0000:2", "0000FF:3", "loop"], BLEDOB_PROFILE)
        with patch("controle_elk.control.commands.asyncio.sleep") as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await play(send)
        self.assertEqual(writes, [red, blue, red])
        self.assertEqual([call.args for call in sleep.await_args_list], [(2,), (3,)])

    def test_first_duration_controls_loop_return_with_legacy_fallback(self):
        blue = bytes((0, 0, 255))
        red = bytes((255, 0, 0))
        for first, loop, expected in (
            ("FF0000:2", ["loop"], [(blue, 4), (red, 2)]),
            ("FF0000", ["loop"], [(blue, 4), (red, 4)]),
            ("FF0000:2", [], [(blue, 4)]),
        ):
            self.assertEqual(
                parse_gradient([first, "0000FF:4", *loop]), (red, expected, bool(loop))
            )

    def test_gradient_compiles_sixty_distinct_updates_in_one_second(self):
        steps = list(changes(bytes(3), bytes((255, 0, 0)), 1))
        self.assertEqual(len(steps), 60)
        self.assertEqual(len({rgb for _, rgb in steps}), 60)
        self.assertAlmostEqual(sum(delay for delay, _ in steps), 1)

    async def test_loop_reuses_compiled_packets(self):
        start = BLEDOB_PROFILE.color(bytes((255, 0, 0)))
        end = BLEDOB_PROFILE.color(bytes((254, 0, 0)))
        sent = []

        async def send(packet, *, settle):
            sent.append(packet)
            if len(sent) == 5:
                raise asyncio.CancelledError

        play = prepare("gradiente", ["FF0000", "FE0000:0.01", "loop"], BLEDOB_PROFILE)
        with patch("controle_elk.control.gradient.changes", side_effect=AssertionError):
            with self.assertRaises(asyncio.CancelledError):
                await play(send)
        self.assertEqual(sent, [start, end, start, end, start])

    def test_compilation_compresses_identical_frames_and_keeps_duration(self):
        end = bytes((1, 0, 0))
        steps = list(changes(bytes(3), end, 600))
        self.assertEqual([rgb for _, rgb in steps], [end, None])
        self.assertAlmostEqual(sum(delay for delay, _ in steps), 600)
        self.assertEqual(list(changes(end, end, 600)), [(600, None)])

    async def test_gradient_emits_intermediate_colors_and_reaches_destination(self):
        packets = []

        async def send(packet, *, settle):
            self.assertFalse(settle)
            packets.append(packet)

        play = prepare("gradiente", ["FF0000", "0000FF:0.15"], BLEDOB_PROFILE)
        await play(send)
        self.assertGreater(len(packets), 2)
        self.assertEqual(packets[0], BLEDOB_PROFILE.color(bytes((255, 0, 0))))
        self.assertEqual(packets[-1], BLEDOB_PROFILE.color(bytes((0, 0, 255))))
        self.assertTrue(all(packet[5] == 0 for packet in packets))

    def test_invalid_duration_is_rejected_before_opening_bluetooth(self):
        with self.assertRaises(ValueError):
            prepare("gradiente", ["FF0000", "0000FF:nan"], BLEDOB_PROFILE)

    async def test_power_off_does_not_wait_for_gradient_write_cancellation(self):
        connection = DesktopConnection()
        connection.profile = BLEDOB_PROFILE
        writing_color = asyncio.Event()
        cancelling_color = asyncio.Event()
        finish_cancellation = asyncio.Event()
        commands = []

        async def send(packet, *, settle=True):
            commands.append(packet)
            if not settle:
                writing_color.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    cancelling_color.set()
                    await finish_cancellation.wait()
                    raise

        connection.send = send
        gradient = asyncio.create_task(
            connection.command("gradiente", ["FF0000", "0000FF:3", "loop"])
        )
        try:
            await asyncio.wait_for(writing_color.wait(), 1)
            await asyncio.wait_for(connection.command("desligar", []), 1)
            self.assertTrue(cancelling_color.is_set())
            self.assertFalse(gradient.done())
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[-1], BLEDOB_PROFILE.power(False))
        finally:
            finish_cancellation.set()
            await asyncio.gather(gradient, return_exceptions=True)

    async def test_brightness_waits_for_current_frame_without_stopping_gradient(self):
        connection = DesktopConnection()
        connection.profile = BLEDOB_PROFILE
        first_frame = asyncio.Event()
        release_frame = asyncio.Event()
        another_frame = asyncio.Event()
        packets = []
        writing = False
        brightness_packet = BLEDOB_PROFILE.brightness(45)

        async def send(packet, *, settle=True):
            nonlocal writing
            self.assertFalse(writing)
            writing = True
            try:
                packets.append(packet)
                if len(packets) == 1:
                    first_frame.set()
                    await release_frame.wait()
                elif packet != brightness_packet and brightness_packet in packets:
                    another_frame.set()
            finally:
                writing = False

        connection.send = send
        gradient = asyncio.create_task(
            connection.command("gradiente", ["FF0000", "0000FF:1", "loop"])
        )
        try:
            await asyncio.wait_for(first_frame.wait(), 1)
            brightness = asyncio.create_task(connection.command("brilho", ["45"]))
            await asyncio.sleep(0)
            self.assertFalse(brightness.done())
            release_frame.set()
            await asyncio.wait_for(brightness, 1)
            await asyncio.wait_for(another_frame.wait(), 1)
            self.assertFalse(gradient.done())
            self.assertEqual(packets[1], brightness_packet)
        finally:
            release_frame.set()
            await connection.stop()
            await asyncio.gather(gradient, return_exceptions=True)
