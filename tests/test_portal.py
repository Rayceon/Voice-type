"""Use a private D-Bus daemon and fake portal, never the user's desktop portal."""
import asyncio
import shutil
import subprocess
import sys

import pytest

from voicetype.portal_trigger import INTERFACE, PATH, REQUEST, PortalTrigger, preferred_trigger


@pytest.mark.parametrize("value,expected", [("ctrl+shift+space", "CTRL+SHIFT+space"),
                                           ("f8", "F8"), ("alt+enter", "ALT+Return")])
def test_portal_shortcut_format(value, expected):
    assert preferred_trigger(value) == expected


@pytest.mark.parametrize("value", ["mouse:x1", "ctrl", "ctrl+shift"])
def test_portal_unsupported_input_is_explicit(value):
    with pytest.raises(ValueError, match="Wayland portal"):
        preferred_trigger(value)


@pytest.mark.skipif(sys.platform != "linux" or not shutil.which("dbus-daemon"),
                    reason="requires private Linux D-Bus daemon")
@pytest.mark.parametrize("mode", ["normal", "deny", "portal_close", "portal_restart", "cancel_prompt"])
def test_portal_wire_authorization_events_and_cleanup(monkeypatch, mode):
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    from voicetype.portal_trigger import DESTINATION
    daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", daemon.stdout.readline().strip())
    events, reports, calls = [], [], []
    closed_paths = []
    listener = PortalTrigger("ctrl+f8", events.append, reports.append)
    session = "/org/freedesktop/portal/desktop/session/test/voice_type"

    async def wait_until(predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(.01)
        raise AssertionError((reports, calls, events))

    async def run():
        bus = await MessageBus().connect()
        await bus.request_name(DESTINATION)
        def handle(msg):
            if msg.message_type != MessageType.METHOD_CALL:
                return
            calls.append(msg.member)
            if msg.member in {"CreateSession", "BindShortcuts"}:
                token = msg.body[-1]["handle_token"].value
                sender = msg.sender.lstrip(":").replace(".", "_")
                path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
                bus.send(Message.new_method_return(msg, "o", [path]))
                if msg.member == "CreateSession":
                    result = {"session_handle": Variant("s", session)}
                    code = 0
                else:
                    assert msg.body[0] == session
                    assert msg.body[1][0][1]["preferred_trigger"].value == "CTRL+F8"
                    if mode == "cancel_prompt":
                        return True  # Permission prompt is left open until Request.Close.
                    code = 1 if mode == "deny" else 0
                    result = {"shortcuts": Variant("a(sa{sv})", [["dictate", {
                        "trigger_description": Variant("s", "Ctrl+F9")}]])}
                bus.send(Message.new_signal(path, REQUEST, "Response", "ua{sv}", [code, result]))
                return True
            if msg.member == "Close":
                closed_paths.append(msg.path)
                bus.send(Message.new_method_return(msg))
                return True
        bus.add_message_handler(handle)
        try:
            listener.start()
            if mode == "cancel_prompt":
                await wait_until(lambda: "BindShortcuts" in calls)
            else:
                await wait_until(lambda: any("被拒绝" in r or "已启用" in r for r in reports))
            if mode in {"deny", "cancel_prompt"}:
                assert not events
            else:
                assert "Ctrl+F9" in reports[-1]  # Show actual, not merely requested binding.
                for member in ["Activated", "Activated", "Deactivated"]:
                    bus.send(Message.new_signal(PATH, INTERFACE, member, "osta{sv}",
                                                [session, "dictate", 100, {}]))
                await wait_until(lambda: events == [True, False])
                # An unrelated app cannot synthesize a recording trigger.
                attacker = await MessageBus().connect()
                attacker.send(Message.new_signal(PATH, INTERFACE, "Activated", "osta{sv}",
                                                  [session, "dictate", 200, {}]))
                await asyncio.sleep(.05)
                attacker.disconnect()
                assert events == [True, False]
                if mode in {"portal_close", "portal_restart"}:
                    bus.send(Message.new_signal(PATH, INTERFACE, "Activated", "osta{sv}",
                                                [session, "dictate", 300, {}]))
                    await wait_until(lambda: events == [True, False, True])
                    if mode == "portal_close":
                        bus.send(Message.new_signal(session, "org.freedesktop.portal.Session", "Closed",
                                                    "a{sv}", [{}]))
                    else:
                        await bus.release_name(DESTINATION)
                    await wait_until(lambda: not listener.thread.is_alive())
                    assert events == [True, False, True, False]
            # stop() waits on the other thread, while our fake portal must keep responding.
            await asyncio.to_thread(listener.stop)
            await wait_until(lambda: "Close" in calls)
            assert not listener.thread.is_alive()
            assert session in closed_paths
            if mode == "cancel_prompt":
                assert any("/request/" in p for p in closed_paths)
        finally:
            await asyncio.to_thread(listener.stop)
            bus.disconnect()
    try:
        asyncio.run(run())
    finally:
        daemon.terminate()
        daemon.communicate(timeout=3)
