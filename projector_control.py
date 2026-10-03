import hashlib
import socket
import threading
import tkinter as tk
from tkinter import ttk

EPSON_PORT = 3629
PJLINK_PORT = 4352
TIMEOUT = 3.0
EPSON_HANDSHAKE = bytes.fromhex("45 53 43 2F 56 50 2E 6E 65 74 10 03 00 00 00 00")


class EpsonProjector:
    def __init__(self, ip):
        self.ip = ip.strip()

    def _session(self):
        s = socket.create_connection((self.ip, EPSON_PORT), timeout=TIMEOUT)
        s.settimeout(TIMEOUT)
        s.sendall(EPSON_HANDSHAKE)
        reply = s.recv(64)
        if not reply.startswith(b"ESC/VP.net"):
            s.close()
            raise RuntimeError(f"Неверный ответ ESC/VP.net: {reply!r}")
        if len(reply) >= 16 and reply[14] not in (0x20, 0x00):
            status = reply[14]
            s.close()
            raise RuntimeError(f"ESC/VP.net отказ, код 0x{status:02X}")
        return s

    def command(self, cmd):
        with self._session() as s:
            s.sendall(cmd.encode("ascii") + b"\r")
            data = b""
            while len(data) < 512:
                chunk = s.recv(128)
                if not chunk:
                    break
                data += chunk
                if b":" in data:
                    break
            return data.decode("ascii", errors="replace").strip()

    def power_status(self):
        return self.command("PWR?")

    def mute_status(self):
        return self.command("MUTE?")


class PJLinkProjector:
    """PJLink Class 1 client for Christie LW720."""
    def __init__(self, ip, password=""):
        self.ip = ip.strip()
        self.password = password

    def command(self, command):
        with socket.create_connection((self.ip, PJLINK_PORT), timeout=TIMEOUT) as s:
            s.settimeout(TIMEOUT)
            greeting = s.recv(128).decode("ascii", errors="replace").strip()

            prefix = ""
            if greeting.startswith("PJLINK 1 "):
                challenge = greeting.split(" ", 2)[2].strip()
                if not self.password:
                    raise RuntimeError("PJLink требует пароль")
                prefix = hashlib.md5((challenge + self.password).encode("utf-8")).hexdigest()
            elif not greeting.startswith("PJLINK 0"):
                raise RuntimeError(f"Неожиданный ответ PJLink: {greeting}")

            payload = prefix + "%1" + command + "\r"
            s.sendall(payload.encode("ascii"))

            data = b""
            while len(data) < 512:
                chunk = s.recv(128)
                if not chunk:
                    break
                data += chunk
                if b"\r" in data:
                    break
            response = data.decode("ascii", errors="replace").strip()
            if "ERRA" in response:
                raise RuntimeError("Ошибка авторизации PJLink")
            return response

    def power_status(self):
        return self.command("POWR ?")

    def mute_status(self):
        return self.command("AVMT ?")


class EpsonPanel(ttk.LabelFrame):
    def __init__(self, master, name, default_ip):
        super().__init__(master, text=name, padding=12)
        self.ip_var = tk.StringVar(value=default_ip)
        self.status_var = tk.StringVar(value="Не проверен")

        ttk.Label(self, text="IP:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.ip_var, width=18).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0))
        ttk.Label(self, textvariable=self.status_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 10))

        ttk.Button(self, text="ВКЛ", command=lambda: self.run("PWR ON")).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="ВЫКЛ", command=lambda: self.run("PWR OFF")).grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="СТАТУС", command=self.refresh).grid(row=2, column=2, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="A/V MUTE ON", command=lambda: self.run("MUTE ON")).grid(row=3, column=0, columnspan=3, sticky="ew", padx=2, pady=(8, 2))
        ttk.Button(self, text="A/V MUTE OFF", command=lambda: self.run("MUTE OFF")).grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=2)

        for c in range(3):
            self.columnconfigure(c, weight=1)

    def projector(self):
        return EpsonProjector(self.ip_var.get())

    def run(self, cmd):
        def worker():
            try:
                self.after(0, self.status_var.set, "Отправка команды…")
                response = self.projector().command(cmd)
                self.after(0, self.status_var.set, f"OK: {response or cmd}")
            except Exception as e:
                self.after(0, self.status_var.set, f"Ошибка: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        def worker():
            try:
                p = self.projector()
                self.after(0, self.status_var.set, f"{p.power_status()}   {p.mute_status()}")
            except Exception as e:
                self.after(0, self.status_var.set, f"OFFLINE: {e}")
        threading.Thread(target=worker, daemon=True).start()


class ChristiePanel(ttk.LabelFrame):
    def __init__(self, master, default_ip):
        super().__init__(master, text="Christie LW720", padding=12)
        self.ip_var = tk.StringVar(value=default_ip)
        self.password_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Не проверен")

        ttk.Label(self, text="IP:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.ip_var, width=18).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0))
        ttk.Label(self, text="PJLink пароль:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(self, textvariable=self.password_var, show="*", width=18).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Label(self, textvariable=self.status_var).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 10))

        ttk.Button(self, text="ВКЛ", command=lambda: self.run("POWR 1")).grid(row=3, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="ВЫКЛ", command=lambda: self.run("POWR 0")).grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="СТАТУС", command=self.refresh).grid(row=3, column=2, sticky="ew", padx=2, pady=2)
        ttk.Button(self, text="MUTE ON", command=lambda: self.run("AVMT 31")).grid(row=4, column=0, columnspan=3, sticky="ew", padx=2, pady=(8, 2))
        ttk.Button(self, text="MUTE OFF", command=lambda: self.run("AVMT 30")).grid(row=5, column=0, columnspan=3, sticky="ew", padx=2, pady=2)

        for c in range(3):
            self.columnconfigure(c, weight=1)

    def projector(self):
        return PJLinkProjector(self.ip_var.get(), self.password_var.get())

    def run(self, cmd):
        def worker():
            try:
                self.after(0, self.status_var.set, "Отправка команды…")
                response = self.projector().command(cmd)
                self.after(0, self.status_var.set, f"OK: {response}")
            except Exception as e:
                self.after(0, self.status_var.set, f"Ошибка: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        def worker():
            try:
                p = self.projector()
                self.after(0, self.status_var.set, f"{p.power_status()}   {p.mute_status()}")
            except Exception as e:
                self.after(0, self.status_var.set, f"OFFLINE: {e}")
        threading.Thread(target=worker, daemon=True).start()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Theater Projector Control")
        self.geometry("1050x520")
        self.minsize(950, 480)

        ttk.Label(self, text="Theater Projector Control", font=("Segoe UI", 18, "bold")).pack(pady=(16, 4))
        ttk.Label(self, text="2 × Epson ESC/VP.net + Christie LW720 PJLink").pack(pady=(0, 12))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)

        self.p1 = EpsonPanel(body, "Epson EB-G7800", "192.168.1.50")
        self.p2 = EpsonPanel(body, "Epson EB-L1755U", "192.168.1.60")
        self.p3 = ChristiePanel(body, "192.168.1.70")

        self.p1.grid(row=0, column=0, sticky="nsew", padx=6)
        self.p2.grid(row=0, column=1, sticky="nsew", padx=6)
        self.p3.grid(row=0, column=2, sticky="nsew", padx=6)

        for c in range(3):
            body.columnconfigure(c, weight=1)

        allbox = ttk.LabelFrame(self, text="Все 3 проектора", padding=10)
        allbox.pack(fill="x", padx=18, pady=12)
        ttk.Button(allbox, text="MUTE ON — ВСЕ", command=self.all_mute_on).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(allbox, text="MUTE OFF — ВСЕ", command=self.all_mute_off).pack(side="left", fill="x", expand=True, padx=4)

        ttk.Label(
            self,
            text="Для включения по сети в Standby на каждом проекторе должна быть разрешена сетевая связь. Christie использует PJLink TCP 4352."
        ).pack(pady=(0, 12))

    def all_mute_on(self):
        self.p1.run("MUTE ON")
        self.p2.run("MUTE ON")
        self.p3.run("AVMT 31")

    def all_mute_off(self):
        self.p1.run("MUTE OFF")
        self.p2.run("MUTE OFF")
        self.p3.run("AVMT 30")


if __name__ == "__main__":
    App().mainloop()
