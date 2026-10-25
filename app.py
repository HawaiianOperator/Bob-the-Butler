"""Windows-first compact companion. Desktop automation is not enabled yet."""
import ctypes
import queue
import secrets
import threading
import time
import tkinter as tk
from tkinter import ttk

import serial
from serial.tools import list_ports
from protocol import request, valid_reply

BG = '#ffffff'
CARD = '#f1f4f3'
TEXT = '#1d302b'
MUTED = '#687b74'
GREEN = '#168558'
RED = '#ba3a47'


class Companion:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.connected = False
        self.busy = False
        self.closing = False
        self.ports = {}
        self.attempted = set()
        self.auto_pending = []
        self.auto_mode = False
        self.failure = ''
        root.title('Bob the Butler')
        root.configure(bg=BG)
        root.resizable(False, False)
        self.position()
        self.rounded_window()
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Phone.TCombobox', fieldbackground=CARD, background=CARD,
                        foreground=TEXT, arrowcolor=GREEN, padding=6)
        style.map('Phone.TCombobox', fieldbackground=[('readonly', CARD)],
                  foreground=[('readonly', TEXT)], selectbackground=[('readonly', CARD)],
                  selectforeground=[('readonly', TEXT)])
        root.option_add('*TCombobox*Listbox.background', CARD)
        root.option_add('*TCombobox*Listbox.foreground', TEXT)
        self.shell = tk.Frame(self.surface, bg=BG, padx=16, pady=10)
        self.surface.create_window(8, 8, window=self.shell, anchor='nw', width=344, height=284)
        top = tk.Frame(self.shell, bg=BG)
        top.pack(fill='x')
        self.label(top, 'Bob the Butler', size=12, bold=True).pack(side='left')
        close = tk.Button(top, text='×', command=self.close, bg=BG, fg=MUTED,
                          activebackground=CARD, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 14))
        close.pack(side='right', padx=(8, 0))
        for widget in (top, top.winfo_children()[0]):
            widget.bind('<ButtonPress-1>', self.drag_start)
            widget.bind('<B1-Motion>', self.drag_move)
        self.badge = self.label(top, '●  OFFLINE', size=8, color=MUTED)
        self.badge.pack(side='right')
        self.body = tk.Frame(self.shell, bg=BG)
        self.body.pack(fill='both', expand=True)
        self.offline = tk.Frame(self.body, bg=BG)
        self.online = tk.Frame(self.body, bg=BG)
        self.make_offline()
        self.make_online()
        self.offline.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.scan()
        root.after(75, self.poll)
        root.after(800, self.autodetect)

    def position(self):
        width, height = 360, 300
        left, top, right, bottom = 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            from ctypes import wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        except (AttributeError, OSError):
            pass
        height = min(height, bottom - top - 24)
        self.root.geometry(f'{width}x{height}+{max(left, right-width-18)}+{max(top, bottom-height-18)}')

    def label(self, parent, text, size=11, color=TEXT, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent['bg'], fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), **kw)

    def rounded_window(self):
        # A transparent exterior gives rounded corners on Windows 10 as well as 11.
        self.root.overrideredirect(True)
        transparent = '#ff00ff'
        try:
            self.root.wm_attributes('-transparentcolor', transparent)
        except tk.TclError:
            transparent = BG
        self.root.configure(bg=transparent)
        self.surface = tk.Canvas(self.root, bg=transparent, highlightthickness=0)
        self.surface.pack(fill='both', expand=True)
        self.surface.create_polygon(24, 0, 336, 0, 360, 0, 360, 24,
                                    360, 276, 360, 300, 336, 300,
                                    24, 300, 0, 300, 0, 276, 0, 24, 0, 0,
                                    fill=BG, outline='#dfe8e3', smooth=True, splinesteps=32)

    def drag_start(self, event):
        self.drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag_move(self, event):
        x, y = self.drag_offset
        self.root.geometry(f'+{event.x_root-x}+{event.y_root-y}')

    def icon(self, parent, connected=False):
        canvas = tk.Canvas(parent, width=54, height=58, bg=BG, highlightthickness=0)
        canvas.create_oval(1, 3, 51, 53, fill=CARD, outline='')
        color = GREEN if connected else MUTED
        canvas.create_rectangle(16, 12, 35, 40, outline=color, width=2)
        canvas.create_line(21, 17, 30, 17, fill=color, width=2)
        canvas.create_oval(24, 33, 28, 37, fill=color, outline='')
        canvas.create_oval(32, 32, 51, 51, fill=GREEN if connected else RED, outline=BG, width=2)
        if connected:
            canvas.create_line(37, 41, 40, 44, 46, 38, fill=BG, width=2)
        else:
            canvas.create_line(38, 38, 45, 45, fill=BG, width=2)
            canvas.create_line(45, 38, 38, 45, fill=BG, width=2)
        return canvas

    def make_offline(self):
        hero = tk.Frame(self.offline, bg=BG)
        hero.pack(fill='x', pady=(9, 2))
        self.icon(hero).pack(side='left', padx=(0, 10))
        copy = tk.Frame(hero, bg=BG)
        copy.pack(side='left')
        self.label(copy, 'Hey, let’s connect.', size=15, bold=True).pack(anchor='w')
        self.label(copy, 'Plug in your device to get started.', size=9, color=MUTED).pack(anchor='w', pady=(3, 0))
        self.status = self.label(self.offline, 'Looking for your device…', size=9, color=GREEN,
                                 wraplength=310, justify='left')
        self.status.pack(anchor='w', pady=(2, 8))
        row = tk.Frame(self.offline, bg=BG)
        row.pack(fill='x')
        self.port = ttk.Combobox(row, state='readonly', style='Phone.TCombobox', width=23)
        self.port.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.arrow = tk.Canvas(row, width=36, height=36, bg=BG, highlightthickness=0,
                               cursor='hand2', takefocus=True)
        self.arrow.create_oval(1, 1, 35, 35, fill=GREEN, outline='')
        self.arrow.create_text(18, 17, text='→', fill='white', font=('Segoe UI', 17, 'bold'))
        self.arrow.bind('<Button-1>', lambda event: self.connect_selected() if str(self.arrow['state']) != 'disabled' else None)
        self.arrow.bind('<Return>', lambda event: self.connect_selected() if str(self.arrow['state']) != 'disabled' else None)
        self.arrow.bind('<space>', lambda event: self.connect_selected() if str(self.arrow['state']) != 'disabled' else None)
        self.arrow.pack(side='right')
        self.refresh_button = tk.Button(self.offline, text='↻  Refresh ports', command=self.manual_refresh,
                                        bg=BG, fg=MUTED, activebackground=CARD,
                                        activeforeground=TEXT, relief='flat', cursor='hand2', bd=0,
                                        font=('Segoe UI', 9))
        self.refresh_button.pack(anchor='w', pady=(3, 0))
        self.feedback = self.label(self.offline, '', size=9, color=RED, wraplength=310, justify='left')
        self.feedback.pack(anchor='w', pady=(5, 0))

    def make_online(self):
        hero = tk.Frame(self.online, bg=BG)
        hero.pack(fill='x', pady=(12, 4))
        self.icon(hero, True).pack(side='left', padx=(0, 10))
        copy = tk.Frame(hero, bg=BG)
        copy.pack(side='left')
        self.label(copy, 'You’re connected.', size=16, bold=True).pack(anchor='w')
        self.label(copy, 'Your device is verified.', size=10, color=MUTED).pack(anchor='w', pady=(3, 0))
        self.device_info = self.label(self.online, '', color=GREEN, size=10)
        self.device_info.pack(anchor='w', pady=(4, 6))
        self.label(self.online, 'Task controls and local AI are coming next.', size=9, color=MUTED,
                   wraplength=310, justify='left').pack(anchor='w', pady=(2, 12))
        tk.Button(self.online, text='Disconnect', command=self.disconnect, bg=CARD, fg=TEXT,
                  activebackground='#e2eae5', activeforeground=TEXT, relief='flat',
                  font=('Segoe UI', 10), pady=7, cursor='hand2').pack(fill='x')

    def scan(self):
        previous = self.port.get()
        try:
            items = sorted(list_ports.comports())
        except (OSError, serial.SerialException):
            self.status.configure(text='Couldn’t scan ports. Try Refresh.')
            return
        self.ports = {f'{p.device} · {p.description}': p.device for p in items}
        self.port['values'] = list(self.ports)
        self.port.set(previous if previous in self.ports else next(iter(self.ports), ''))
        current = {p.device for p in items}
        self.attempted.intersection_update(current)
        self.auto_pending = [p.device for p in items if p.vid is not None and p.device not in self.attempted]
        if not self.busy and not self.connected:
            self.arrow.configure(state='normal' if items else 'disabled')
        return items

    def manual_refresh(self):
        self.attempted.clear()
        self.failure = ''
        self.feedback.configure(text='')
        self.scan()

    def autodetect(self):
        if self.closing:
            return
        if not self.busy and not self.connected:
            self.scan()
            if self.auto_pending:
                self.connect(self.auto_pending[0], automatic=True)
            elif not self.failure:
                self.status.configure(text='Choose a port below.' if self.ports else 'Waiting for your USB device…')
        self.root.after(2000, self.autodetect)

    def connect_selected(self):
        device = self.ports.get(self.port.get())
        if device and not self.busy:
            self.connect(device)

    def connect(self, device, automatic=False):
        self.busy = True
        self.auto_mode = automatic
        self.failure = ''
        self.attempted.add(device)
        self.stop.clear()
        self.feedback.configure(text='')
        self.status.configure(text=f'Checking {device}…', fg=GREEN)
        self.arrow.configure(state='disabled')
        self.port.configure(state='disabled')
        self.refresh_button.configure(state='disabled')
        self.worker = threading.Thread(target=self.serial_loop, args=(device,), daemon=True)
        self.worker.start()

    def emit(self, kind, value=''):
        self.events.put((kind, value))

    def exchange(self, connection, send_type, reply_type, timeout):
        nonce = secrets.token_hex(12)
        deadline = time.monotonic() + timeout
        next_send = 0
        pending = bytearray()
        while time.monotonic() < deadline and not self.stop.is_set():
            if time.monotonic() >= next_send:
                connection.write(request(send_type, nonce))
                next_send = time.monotonic() + 1
            pending.extend(connection.read(256))
            while b'\n' in pending:
                raw, _, pending = pending.partition(b'\n')
                if valid_reply(raw, reply_type, nonce):
                    return True
            if len(pending) > 4096:
                pending.clear()
        return False

    def serial_loop(self, device):
        try:
            with serial.Serial(port=None, baudrate=115200, timeout=0.15, write_timeout=0.5) as connection:
                connection.dtr = False
                connection.rts = False
                connection.port = device
                connection.open()
                if not self.exchange(connection, 'hello', 'hello_ack', 5):
                    if not self.stop.is_set():
                        self.emit('error', 'Wrong device or missing firmware. Pick another port and try again.')
                    return
                if self.stop.is_set():
                    return
                self.emit('connected', device)
                while not self.stop.wait(1):
                    if not self.exchange(connection, 'ping', 'pong', 3):
                        if not self.stop.is_set():
                            self.emit('error', 'Your device stopped responding. Reconnect it and try again.')
                        break
        except (serial.SerialException, OSError) as exc:
            if not self.stop.is_set():
                self.emit('error', f'Can’t open {device}. Check the cable, close other serial apps, and try again.')
        finally:
            self.emit('disconnected')

    def show_offline(self):
        self.online.pack_forget()
        self.offline.pack(fill='both', expand=True)
        self.badge.configure(text='●  OFFLINE', fg=MUTED)

    def disconnect(self):
        self.stop.set()
        self.connected = False
        self.show_offline()
        self.status.configure(text='Disconnecting…')

    def poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'connected':
                if self.stop.is_set():
                    continue
                self.connected = True
                self.offline.pack_forget()
                self.online.pack(fill='both', expand=True)
                self.device_info.configure(text=f'{value}  /  USB serial')
                self.badge.configure(text='●  CONNECTED', fg=GREEN)
            elif kind == 'error':
                self.failure = value
                self.feedback.configure(text=value)
            elif kind == 'disconnected':
                self.connected = False
                self.busy = False
                self.show_offline()
                self.port.configure(state='readonly')
                self.refresh_button.configure(state='normal')
                self.arrow.configure(state='normal' if self.ports else 'disabled')
                self.status.configure(text='Let’s try again.' if self.failure else 'Choose a port to reconnect.')
                # Try each USB candidate once; preserve a manual failure until the user retries.
                if self.failure and not self.auto_mode:
                    self.attempted.update(self.ports.values())
        if self.closing and (not self.worker or not self.worker.is_alive()):
            self.root.destroy()
            return
        self.root.after(75, self.poll)

    def close(self):
        self.closing = True
        self.stop.set()
        self.root.withdraw()


if __name__ == '__main__':
    root = tk.Tk()
    Companion(root)
    root.mainloop()
