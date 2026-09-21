"""User-approved Wayland keyboard shortcuts via the XDG desktop portal.

No raw input reading, root permissions, or compositor-specific configuration.
The desktop may choose a different shortcut; its returned description is shown.
"""
from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

from .triggers import MODIFIERS, parse_trigger

DESTINATION = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"


def preferred_trigger(value):
    required = parse_trigger(value)
    ordinary = required - MODIFIERS
    if not ordinary or any(t.startswith("mouse:") for t in ordinary):
        raise ValueError("Wayland portal 需使用普通键盘键（可加修饰键），不支持鼠标键或纯修饰键。")
    key = next(iter(ordinary))
    names = {"enter": "Return", "esc": "Escape", "tab": "Tab", "backspace": "BackSpace",
             "delete": "Delete", "insert": "Insert", "home": "Home", "end": "End",
             "page_up": "Prior", "page_down": "Next", "left": "Left", "right": "Right",
             "up": "Up", "down": "Down", "caps_lock": "Caps_Lock", "num_lock": "Num_Lock",
             "scroll_lock": "Scroll_Lock", "pause": "Pause", "print_screen": "Print",
             "menu": "Menu", "alt_gr": "ISO_Level3_Shift", "comma": "comma", "period": "period",
             "slash": "slash", "semicolon": "semicolon", "apostrophe": "apostrophe",
             "bracket_left": "bracketleft", "bracket_right": "bracketright", "backslash": "backslash",
             "grave": "grave", "minus": "minus", "equal": "equal",
             "media_play": "XF86AudioPlay", "media_stop": "XF86AudioStop",
             "media_record": "XF86AudioRecord", "media_play_pause": "XF86AudioPlay",
             "media_previous": "XF86AudioPrev", "media_next": "XF86AudioNext",
             "media_volume_mute": "XF86AudioMute", "media_volume_down": "XF86AudioLowerVolume",
             "media_volume_up": "XF86AudioRaiseVolume"}
    key = names.get(key, key.upper() if key.startswith("f") and key[1:].isdigit() else key)
    modifiers = [name for token, name in [("ctrl", "CTRL"), ("alt", "ALT"),
                                         ("shift", "SHIFT"), ("cmd", "LOGO")] if token in required]
    return "+".join(modifiers + [key])


class PortalTrigger:
    def __init__(self, trigger, emit, report):
        self.preferred = preferred_trigger(trigger)
        self.emit, self.report = emit, report
        self.stopped = threading.Event()
        self.loop = self.task = self.bus = None
        self.session = ""
        self.owner = ""
        self.requests = {}
        self.active = False
        self.thread = None

    def start(self):
        self.report("请在系统弹窗确认全局录音键；最终按键以系统授权结果为准。")
        self.thread = threading.Thread(target=self._run, daemon=True, name="voice-type-portal")
        self.thread.start()

    def _run(self):
        asyncio.run(self._serve())

    async def _call(self, **kwargs):
        from dbus_next import Message, MessageType
        response = await asyncio.wait_for(self.bus.call(Message(**kwargs)), 5)
        if response.message_type == MessageType.ERROR:
            raise RuntimeError("桌面未提供可用的 GlobalShortcuts portal；请使用窗口录音或 X11。")
        return response

    async def _request(self, method, signature, body, options=None):
        from dbus_next import Variant
        token = "voice_type_" + uuid4().hex
        sender = self.bus.unique_name.lstrip(":").replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        future = self.loop.create_future()
        self.requests[path] = future
        opts = dict(options or {}, handle_token=Variant("s", token))
        try:
            response = await self._call(destination=self.owner, path=PATH, interface=INTERFACE,
                                        member=method, signature=signature, body=body + [opts])
            if response.body != [path]:
                raise RuntimeError("桌面 portal 返回了不兼容的请求标识，请使用窗口录音。")
            code, results = await asyncio.wait_for(future, 120)
            if code:
                raise RuntimeError("全局录音键授权已取消或被拒绝；可使用窗口录音。")
            return results
        finally:
            # Close an outstanding permission prompt on cancel/timeout.
            self.requests.pop(path, None)
            if future.cancelled() or not future.done():
                try:
                    await self._call(destination=self.owner, path=path, interface=REQUEST, member="Close")
                except Exception:
                    pass

    def _message(self, message):
        from dbus_next import MessageType
        if message.message_type != MessageType.SIGNAL:
            return
        if (message.sender == "org.freedesktop.DBus" and message.interface == "org.freedesktop.DBus"
                and message.member == "NameOwnerChanged" and message.body[:2] == [DESTINATION, self.owner]):
            self.report("桌面快捷键服务已退出或重启，请重新启用录音键。")
            self.task.cancel()
            return
        if message.sender != self.owner:
            return
        if message.interface == REQUEST and message.member == "Response":
            future = self.requests.get(message.path)
            if future and not future.done():
                future.set_result(message.body)
        elif (message.interface == INTERFACE and message.path == PATH
              and message.member in {"Activated", "Deactivated"}
              and message.body[:2] == [self.session, "dictate"]):
            active = message.member == "Activated"
            if active != self.active and not self.stopped.is_set():
                self.active = active
                self.emit(active)
        elif (message.interface == "org.freedesktop.portal.Session"
              and message.path == self.session and message.member == "Closed"):
            self.report("系统已关闭全局录音键会话，请重新启用。")
            self.task.cancel()

    async def _serve(self):
        from dbus_next import Variant
        from dbus_next.aio import MessageBus
        self.loop, self.task = asyncio.get_running_loop(), asyncio.current_task()
        try:
            if self.stopped.is_set():
                return
            self.bus = await asyncio.wait_for(MessageBus().connect(), 5)
            # An already running portal need not have a D-Bus activation file.
            # StartServiceByName can fail in that case even though it owns the name.
            running = await self._call(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                       interface="org.freedesktop.DBus", member="NameHasOwner",
                                       signature="s", body=[DESTINATION])
            if not running.body[0]:
                await self._call(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                 interface="org.freedesktop.DBus", member="StartServiceByName",
                                 signature="su", body=[DESTINATION, 0])
            # Pin its unique name, rejecting unrelated signals.
            owner = await self._call(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                     interface="org.freedesktop.DBus", member="GetNameOwner",
                                     signature="s", body=[DESTINATION])
            self.owner = owner.body[0]
            self.bus.add_message_handler(self._message)
            await self._call(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                             interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[
                                 "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
                                 f"member='NameOwnerChanged',arg0='{DESTINATION}'"])
            for interface in [REQUEST, INTERFACE, "org.freedesktop.portal.Session"]:
                rule = f"type='signal',sender='{self.owner}',interface='{interface}'"
                await self._call(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                 interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[rule])
            created = await self._request("CreateSession", "a{sv}", [], {
                "session_handle_token": Variant("s", "voice_type_" + uuid4().hex)})
            self.session = created["session_handle"].value
            bound = await self._request("BindShortcuts", "oa(sa{sv})sa{sv}", [self.session,
                [["dictate", {"description": Variant("s", "Voice Type 录音"),
                              "preferred_trigger": Variant("s", self.preferred)}]], ""])
            choices = bound.get("shortcuts")
            shortcuts = choices.value if choices else []
            match = next((props for ident, props in shortcuts if ident == "dictate"), None)
            if match is None:
                raise RuntimeError("系统没有绑定录音键，请重新启用并确认授权。")
            description = match.get("trigger_description")
            self.report("Wayland 录音键已启用：" + (description.value if description else "请以系统设置为准"))
            await self.bus.wait_for_disconnect()
            if not self.stopped.is_set():
                self.report("桌面会话总线断开，请重新启用录音键。")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self.stopped.is_set():
                self.report(str(exc) if isinstance(exc, RuntimeError) else
                            "无法连接桌面快捷键 portal；可使用窗口录音或切换 X11。")
        finally:
            if self.active:
                self.active = False
                self.emit(False)
            if self.bus:
                if self.session:
                    try:
                        await self._call(destination=self.owner, path=self.session,
                                         interface="org.freedesktop.portal.Session", member="Close")
                    except Exception:
                        pass
                self.bus.disconnect()

    def stop(self):
        self.stopped.set()
        if self.loop and not self.loop.is_closed() and self.task:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass  # The loop finished between is_closed() and scheduling.
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(1)
