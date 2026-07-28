"""Получить OAuth-токен Яндекс Музыки (Device Flow) для .env.

GUI (по умолчанию):
  python tools/yandex_music_token.py
  или двойной клик: tools\\yandex_music_token.cmd

Консоль:
  python tools/yandex_music_token.py --cli
"""
from __future__ import annotations

import argparse
import re
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
_TOKEN_LINE_RE = re.compile(
    r"^[ \t]*#?[ \t]*YANDEX_MUSIC_TOKEN[ \t]*=.*$",
    re.MULTILINE,
)


def _import_client():
    try:
        from yandex_music import Client
    except ImportError as exc:
        raise RuntimeError(
            "Не установлен пакет yandex-music.\n"
            "В папке бота выполните:\n"
            ".\\.venv\\Scripts\\python.exe -m pip install yandex-music"
        ) from exc
    return Client


def _extract_access(token) -> str:
    return str(getattr(token, "access_token", None) or token)


def fetch_token(on_code) -> str:
    Client = _import_client()
    client = Client()
    token = client.device_auth(on_code=on_code)
    return _extract_access(token)


def save_token_to_env(access: str, env_path: Path = ENV_PATH) -> Path:
    line = f"YANDEX_MUSIC_TOKEN={access}"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        if _TOKEN_LINE_RE.search(text):
            text = _TOKEN_LINE_RE.sub(line, text, count=1)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"\n# Яндекс Музыка (song-request)\n{line}\n"
        env_path.write_text(text, encoding="utf-8")
    else:
        env_path.write_text(
            f"# Яндекс Музыка (song-request)\n{line}\n",
            encoding="utf-8",
        )
    return env_path


def run_cli() -> int:
    def on_code(code) -> None:
        url = getattr(code, "verification_url", None) or "https://ya.ru"
        user_code = getattr(code, "user_code", "?")
        print()
        print(f"Откройте: {url}")
        print(f"Введите код: {user_code}")
        print("Подтвердите вход в аккаунт с Яндекс Плюс…")
        print()
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    print("Запрос Device Flow (Яндекс Музыка)…")
    try:
        access = fetch_token(on_code)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка авторизации: {exc}", file=sys.stderr)
        print("Документация: https://ym.marshal.dev/token", file=sys.stderr)
        return 1

    path = save_token_to_env(access)
    print()
    print(f"Токен сохранён в {path}")
    print("Перезапустите бота.")
    return 0


def run_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Яндекс Музыка — токен для бота")
    root.minsize(480, 360)
    root.geometry("560x420")

    status = tk.StringVar(
        value="Нажмите «Получить токен», затем подтвердите вход в браузере."
    )
    code_var = tk.StringVar(value="—")
    url_var = tk.StringVar(value="—")
    token_var = tk.StringVar(value="")
    busy = {"v": False}

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        frm,
        text="Авторизация Яндекс Музыки (Plus)",
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor=tk.W)

    ttk.Label(
        frm,
        text=(
            "1. Нажмите «Получить токен»\n"
            "2. В браузере войдите в аккаунт с Плюсом и введите код\n"
            "3. Токен сохранится в файл .env бота автоматически"
        ),
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(8, 12))

    info = ttk.Frame(frm)
    info.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(info, text="Код:").grid(row=0, column=0, sticky=tk.W)
    ttk.Label(info, textvariable=code_var, font=("Consolas", 16, "bold")).grid(
        row=0, column=1, sticky=tk.W, padx=(8, 0)
    )
    ttk.Label(info, text="Ссылка:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
    ttk.Label(info, textvariable=url_var, wraplength=480).grid(
        row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0)
    )

    ttk.Label(frm, textvariable=status, wraplength=520).pack(anchor=tk.W, pady=(4, 8))

    token_box = tk.Text(frm, height=4, wrap=tk.WORD, font=("Consolas", 9))
    token_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
    token_box.insert("1.0", "Токен появится здесь после успешного входа…")
    token_box.configure(state=tk.DISABLED)

    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X)

    def set_token_text(text: str) -> None:
        token_box.configure(state=tk.NORMAL)
        token_box.delete("1.0", tk.END)
        token_box.insert("1.0", text)
        token_box.configure(state=tk.DISABLED)

    def ui(fn) -> None:
        root.after(0, fn)

    def on_code(code) -> None:
        url = getattr(code, "verification_url", None) or "https://ya.ru"
        user_code = getattr(code, "user_code", "?")

        def apply() -> None:
            code_var.set(str(user_code))
            url_var.set(str(url))
            status.set("Откройте ссылку в браузере, введите код и подтвердите вход…")
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        ui(apply)

    def start_auth() -> None:
        if busy["v"]:
            return
        busy["v"] = True
        btn_start.configure(state=tk.DISABLED)
        status.set("Запрос кода у Яндекса…")
        code_var.set("…")
        url_var.set("…")
        set_token_text("Ожидание подтверждения в браузере…")

        def worker() -> None:
            try:
                access = fetch_token(on_code)
            except Exception as exc:  # noqa: BLE001

                def fail() -> None:
                    busy["v"] = False
                    btn_start.configure(state=tk.NORMAL)
                    status.set(f"Ошибка: {exc}")
                    set_token_text(str(exc))
                    messagebox.showerror("Ошибка", str(exc))

                ui(fail)
                return

            try:
                path = save_token_to_env(access)
                saved_msg = f"Сохранено в:\n{path}"
            except Exception as exc:  # noqa: BLE001
                path = None
                saved_msg = f"Не удалось записать .env: {exc}"

            def ok() -> None:
                busy["v"] = False
                btn_start.configure(state=tk.NORMAL)
                token_var.set(access)
                set_token_text(access)
                status.set(
                    "Готово. Перезапустите бота. " + saved_msg.replace("\n", " ")
                )
                messagebox.showinfo(
                    "Токен получен",
                    "Авторизация успешна.\n\n"
                    + saved_msg
                    + "\n\nПерезапустите бота, чтобы заказы Яндекс Музыки заработали.",
                )

            ui(ok)

        threading.Thread(target=worker, daemon=True).start()

    def copy_token() -> None:
        access = token_var.get().strip()
        if not access:
            messagebox.showwarning("Нет токена", "Сначала получите токен.")
            return
        root.clipboard_clear()
        root.clipboard_append(access)
        status.set("Токен скопирован в буфер обмена.")

    def open_url() -> None:
        url = url_var.get().strip()
        if url and url not in ("—", "…"):
            webbrowser.open(url)

    btn_start = ttk.Button(btns, text="Получить токен", command=start_auth)
    btn_start.pack(side=tk.LEFT)
    ttk.Button(btns, text="Открыть ссылку", command=open_url).pack(
        side=tk.LEFT, padx=(8, 0)
    )
    ttk.Button(btns, text="Копировать токен", command=copy_token).pack(
        side=tk.LEFT, padx=(8, 0)
    )
    ttk.Button(btns, text="Закрыть", command=root.destroy).pack(side=tk.RIGHT)

    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OAuth-токен Яндекс Музыки для бота")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Консольный режим вместо окна",
    )
    args = parser.parse_args(argv)
    if args.cli:
        return run_cli()

    try:
        import tkinter as tk
    except ImportError:
        print("tkinter недоступен, консольный режим…", file=sys.stderr)
        return run_cli()

    try:
        return run_gui()
    except tk.TclError as exc:
        print(f"GUI недоступен ({exc}), консольный режим…", file=sys.stderr)
        return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
