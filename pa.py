#!/usr/bin/env python3
"""
Объединённый менеджер пакетов + ИИ-архитектор
- Современный GUI (customtkinter)
- Выбор глобального/venv Python
- Таблица с чекбоксами для выборочного обновления
- Лог вывода pip в реальном времени
- Категории библиотек (расширяемые, редактируемые)
- LLM-помощник: Ollama и OpenRouter
- Парсинг JSON-ответа от LLM (устойчивый)
- Сохранение настроек + безопасное хранение ключей
- Экспорт в requirements.txt
"""

import sys
import os
import json
import subprocess
import threading
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk  # ← Добавлено ttk

import customtkinter as ctk
import requests
import keyring  # Для безопасного хранения ключей

# ======================= НАСТРОЙКИ ОФОРМЛЕНИЯ =======================
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# ======================= КАТЕГОРИИ БИБЛИОТЕК =======================
CATEGORIES = {
    "Веб-фреймворки и серверы": [
        "FastAPI", "Starlette", "Uvicorn", "Gradio", "Streamlit", "Eel", "Bottle"
    ],
    "HTTP-клиенты и сеть": [
        "Requests", "httpx", "aiohttp", "websocket-client", "websockets", "httpcore", "httptools"
    ],
    "Асинхронность": [
        "AnyIO", "Greenlet", "Gevent", "frozenlist", "propcache", "multidict", "yarl"
    ],
    "Обработка данных / наука": [
        "NumPy", "Pandas", "SciPy", "Matplotlib", "Pillow", "pytesseract", "pdf2image",
        "pdfplumber", "PyMuPDF", "python-docx", "fpdf2"
    ],
    "Машинное обучение / ИИ / LLM": [
        "LangChain", "LangGraph", "LangSmith", "chromadb", "tokenizers", "onnxruntime",
        "huggingface_hub", "ollama", "gradio_client"
    ],
    "GUI / десктоп": [
        "PySide6", "shiboken6", "pyqtgraph", "pygame", "customtkinter"
    ],
    "Утилиты и инфраструктура": [
        "pydantic", "attrs", "click", "typer", "rich", "tqdm", "python-dotenv", "PyYAML",
        "toml", "packaging"
    ],
    "Безопасность и шифрование": [
        "cryptography", "bcrypt", "cffi", "oauthlib"
    ],
    "Базы данных и хранилища": [
        "SQLAlchemy", "chromadb", "PyPika"
    ],
    "Работа с документами и PDF": [
        "pdfplumber", "PyMuPDF", "pypdfium2", "python-docx", "pdf2image", "fpdf2"
    ]
}

def get_category(lib_name):
    """Возвращает категорию для библиотеки по имени (регистронезависимо)."""
    lib_lower = lib_name.lower()
    for cat, libs in CATEGORIES.items():
        for l in libs:
            if l.lower() == lib_lower:
                return cat
    return "Другое / Прочее"

# ======================= КОНФИГУРАЦИЯ =======================
CONFIG_FILE = "pip_manager_config.json"
DEFAULT_CONFIG = {
    "python_path": sys.executable,
    "provider": "Ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2",
    "openrouter_key": "",
    "openrouter_model": "openrouter/free"
}

SERVICE_NAME = "UnifiedPipApp"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                saved_key = keyring.get_password(SERVICE_NAME, "openrouter_api_key")
                if saved_key:
                    cfg["openrouter_key"] = saved_key
                else:
                    old_key = cfg.get("openrouter_key", "")
                    if old_key.strip():
                        keyring.set_password(SERVICE_NAME, "openrouter_api_key", old_key)
                return cfg
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        safe_cfg = config.copy()
        api_key = safe_cfg.pop("openrouter_key", None)
        with open(CONFIG_FILE, "w") as f:
            json.dump(safe_cfg, f, indent=2)
        if api_key:
            keyring.set_password(SERVICE_NAME, "openrouter_api_key", api_key)
    except Exception as e:
        print(f"Ошибка сохранения конфига: {e}")

# === Функция для безопасного извлечения JSON ===
def extract_json_safely(text: str):
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    potential = text[start:end+1]
    try:
        data = json.loads(potential)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    lines = text.splitlines()
    for i in range(len(lines)):
        for j in range(len(lines), i, -1):
            snippet = "\n".join(lines[i:j]).strip()
            if snippet.startswith("[") and snippet.endswith("]"):
                try:
                    data = json.loads(snippet)
                    if isinstance(data, list):
                        return data
                except:
                    continue
    return None

# ======================= ГЛАВНОЕ ПРИЛОЖЕНИЕ =======================
class UnifiedPipApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Менеджер пакетов + ИИ-Архитектор")
        self.geometry("1300x800")
        self.minsize(1000, 600)

        # === КРИТИЧНО: Сначала объявляем CONFIG_FILE глобальной ===
        global CONFIG_FILE

        # Спрашиваем, где хранить настройки
        use_custom_config = messagebox.askyesno(
            "Настройки", "Хотите выбрать место для сохранения настроек?"
        )
        if use_custom_config:
            path = filedialog.askdirectory(title="Выберите папку для настроек")
            if path:
                self.config_path = os.path.join(path, "pip_manager_config.json")
            else:
                self.config_path = "pip_manager_config.json"  # fallback
        else:
            self.config_path = "pip_manager_config.json"

        # === Теперь безопасно переопределяем глобальную переменную ===
        CONFIG_FILE = self.config_path

        # === Теперь можно загружать конфиг — CONFIG_FILE уже обновлён ===
        self.config = load_config()
        self.python_path = self.config["python_path"]

        self.installed_packages = {}
        self.outdated_packages = {}
        self.check_vars = {}
        self.tree = None

        self.provider_var = ctk.StringVar(value=self.config["provider"])
        self.ollama_url_var = ctk.StringVar(value=self.config["ollama_url"])
        self.ollama_model_var = ctk.StringVar(value=self.config["ollama_model"])
        self.openrouter_key_var = ctk.StringVar(value=self.config["openrouter_key"])
        self.openrouter_model_var = ctk.StringVar(value=self.config["openrouter_model"])

        self.create_widgets()
        self.refresh_packages_async()

    def create_widgets(self):
        top_frame = ctk.CTkFrame(self, height=50)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top_frame, text="Интерпретатор Python:", font=ctk.CTkFont(weight="bold"), text_color="white").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.python_path_label = ctk.CTkLabel(top_frame, text=self.python_path, anchor="w", fg_color="#2b2b2b", corner_radius=5, text_color="white")
        self.python_path_label.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(top_frame, text="Глобальный", width=90, command=self.select_global_env).grid(row=0, column=2, padx=5, pady=10)
        ctk.CTkButton(top_frame, text="Выбрать .venv", width=120, command=self.select_venv_env).grid(row=0, column=3, padx=10, pady=10)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tab_packages = self.tabview.add("📦 Библиотеки")
        self.tab_categories = self.tabview.add("📂 Категории")
        self.tab_llm = self.tabview.add("🤖 ИИ-Архитектор")

        self.setup_packages_tab()
        self.setup_categories_tab()
        self.setup_llm_tab()

    # ========== ВКЛАДКА "БИБЛИОТЕКИ" ==========
    def setup_packages_tab(self):
        columns = ("select", "package", "installed", "latest", "status")
        self.tree = ttk.Treeview(self.tab_packages, columns=columns, show="headings", selectmode="none")
        
        # Настройка заголовков
        for col in columns:
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, width=100)
        
        self.tree.column("select", width=60, anchor="center")
        self.tree.column("package", width=220)
        self.tree.column("installed", width=120)
        self.tree.column("latest", width=120)
        self.tree.column("status", width=100)

        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        # Скроллбар
        scroll = ctk.CTkScrollbar(self.tab_packages, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0), pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,5), pady=5)

        # Стиль для ttk.Treeview под тему CTk
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2a2d2e",
                        foreground="white",
                        rowheight=30,               # ↑ Высота строки
                        fieldbackground="#343638",
                        borderwidth=0,
                        relief="flat")
        style.map('Treeview', background=[('selected', '#1f6aa5')])

        # Добавим границу между строками
        style.layout("Treeview.Row", [
            ("Treeview.Row.border", {"sticky": "nswe", "children": [
                ("Treeview.Row.padding", {"sticky": "nswe", "children": [
                    ("Treeview.Cell", {"sticky": "nswe"})
                ]})
            ]})
        ])
        style.configure("Treeview.Row", padding=(0, 1))  # маленький отступ = визуальный разделитель
        style.configure("Treeview.Heading",
                        background="#565b5e",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[('active', '#3484A9')])

        btn_frame = ctk.CTkFrame(self.tab_packages, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=5, padx=5)
        ctk.CTkButton(btn_frame, text="Сканировать заново", command=self.refresh_packages_async).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="Обновить выбранные пакеты", fg_color="green", hover_color="darkgreen",
                      command=self.update_selected_packages).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="📥 Экспорт в requirements.txt", command=self.export_requirements).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="📥 Импорт requirements.txt", command=self.import_requirements).pack(side=tk.LEFT, padx=5)

        log_frame = ctk.CTkFrame(self.tab_packages)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ctk.CTkLabel(log_frame, text="Лог обновлений:", anchor="w").pack(fill=tk.X, padx=5, pady=(5,0))
        self.log_text = ctk.CTkTextbox(log_frame, height=150)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def export_requirements(self):
        file_path = filedialog.asksaveasfilename(
            title="Сохранить requirements.txt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for name, version in sorted(self.installed_packages.items()):
                    f.write(f"{name}=={version}\n")
            messagebox.showinfo("Успех", f"Файл сохранён:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1":  # Колонка "select"
                item = self.tree.identify_row(event.y)
                if item:
                    values = self.tree.item(item, "values")
                    if len(values) >= 2:
                        pkg_name = values[1]
                    if pkg_name in self.check_vars:
                        var = self.check_vars[pkg_name]
                        var.set(not var.get())
                        self.tree.set(item, column="select", value="✔" if var.get() else " ")

    def refresh_packages_async(self):
        self._set_refresh_button_state(False)
        threading.Thread(target=self._refresh_packages_worker, daemon=True).start()

    def _refresh_packages_worker(self):
        try:
            proc = subprocess.run(
                [self.python_path, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, check=True
            )
            all_pkgs = json.loads(proc.stdout)
            self.installed_packages = {pkg["name"]: pkg["version"] for pkg in all_pkgs}

            proc_out = subprocess.run(
                [self.python_path, "-m", "pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True
            )
            outdated = []
            if proc_out.returncode == 0 and proc_out.stdout.strip():
                outdated = json.loads(proc_out.stdout)
            self.outdated_packages = {pkg["name"]: pkg["latest_version"] for pkg in outdated}

            self.after(0, self._update_tree)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось получить список пакетов: {e}"))
        finally:
            self.after(0, lambda: self._set_refresh_button_state(True))

    def _update_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.check_vars.clear()

        # Настройка тегов для чередования цветов
        style = ttk.Style()
        style.map('Treeview', background=[('selected', '#1f6aa5')])

        # Устанавливаем цвет фона для чётных и нечётных строк
        self.tree.tag_configure("odd", background="#2e2e2e")
        self.tree.tag_configure("even", background="#2a2d2e")

        for idx, (name, version) in enumerate(sorted(self.installed_packages.items())):
            latest = self.outdated_packages.get(name, "")
            status = "Устарел" if latest else "Актуален"

            var = tk.BooleanVar(value=False)
            self.check_vars[name] = var

            tag = "odd" if idx % 2 == 0 else "even"
            item = self.tree.insert(
                "", tk.END, values=("", name, version, latest, status), tags=(tag,)
            )
            self.tree.set(item, column="select", value=" ")

    def _set_refresh_button_state(self, enabled):
        for child in self.tab_packages.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                for btn in child.winfo_children():
                    if isinstance(btn, ctk.CTkButton) and btn.cget("text") == "Сканировать заново":
                        btn.configure(state="normal" if enabled else "disabled")
                        btn.configure(text="Сканировать заново" if enabled else "Сканирование...")
                        break

    def update_selected_packages(self):
        selected = [name for name, var in self.check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("Нет выбора", "Не выбрано ни одного пакета для обновления.")
            return
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, f"=== Обновление выбранных пакетов ({', '.join(selected)}) ===\n")
        threading.Thread(target=self._update_worker, args=(selected,), daemon=True).start()

    def _update_worker(self, packages):
        for pkg in packages:
            self._append_log(f"\n--- Обновление {pkg} ---\n")
            proc = subprocess.Popen(
                [self.python_path, "-m", "pip", "install", "--upgrade", pkg],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                self._append_log(line)
            proc.wait()
            if proc.returncode == 0:
                self._append_log(f"✅ {pkg} обновлён успешно.\n")
            else:
                self._append_log(f"❌ Ошибка при обновлении {pkg} (код {proc.returncode})\n")
        self._append_log("\n=== Обновление завершено ===\n")
        self.after(500, self.refresh_packages_async)

    def _append_log(self, text):
        def _add():
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
        self.after(0, _add)

    # ========== ВКЛАДКА "КАТЕГОРИИ" ==========
    def setup_categories_tab(self):
        top_bar = ctk.CTkFrame(self.tab_categories)
        top_bar.pack(fill=tk.X, padx=5, pady=5)

        # Кнопки управления
        ctk.CTkButton(top_bar, text="➕ Добавить категорию", command=self.add_category).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(top_bar, text="✏️ Редактировать", command=self.edit_selected_category).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(top_bar, text="🗑 Удалить", command=self.delete_selected_category).pack(side=tk.LEFT, padx=5)
        
        # НОВАЯ КНОПКА: -категоризация через LLM
        self.auto_cat_btn = ctk.CTkButton(
            top_bar, text="🧠 Авто-категоризация (LLM)", 
            fg_color="purple", hover_color="darkviolet",
            command=self.auto_categorize_with_llm
        )
        self.auto_cat_btn.pack(side=tk.RIGHT, padx=5)

        columns = ("category", "libraries")
        self.tree_cat = ttk.Treeview(self.tab_categories, columns=columns, show="headings")
        self.tree_cat.heading("category", text="Категория")
        self.tree_cat.heading("libraries", text="Библиотеки")
        self.tree_cat.column("category", width=250)
        self.tree_cat.column("libraries", width=600)
        self.tree_cat.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Скроллбар
        scroll = ctk.CTkScrollbar(self.tab_categories, command=self.tree_cat.yview)
        self.tree_cat.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,5), pady=5)

        self.tree_cat.bind("<Double-1>", self.edit_selected_category)

        self.refresh_categories_view()

    def refresh_categories_view(self):
        for row in self.tree_cat.get_children():
            self.tree_cat.delete(row)
        for cat, libs in CATEGORIES.items():
            libs_str = ", ".join(libs)
            self.tree_cat.insert("", tk.END, values=(cat, libs_str))

    def add_category(self):
        self.open_category_editor("Добавить категорию", {}, is_new=True)

    def edit_selected_category(self, event=None):
        selected = self.tree_cat.focus()
        if not selected:
            messagebox.showwarning("Нет выбора", "Выберите категорию для редактирования.")
            return
        values = self.tree_cat.item(selected, "values")
        name = values[0]
        libs = values[1].split(", ") if values[1] else []
        self.open_category_editor("Редактировать категорию", {"name": name, "libs": libs})

    def delete_selected_category(self):
        selected = self.tree_cat.focus()
        if not selected:
            messagebox.showwarning("Нет выбора", "Выберите категорию для удаления.")
            return
        values = self.tree_cat.item(selected, "values")
        name = values[0]
        if messagebox.askyesno("Подтверждение", f"Удалить категорию '{name}'?"):
            del CATEGORIES[name]
            self.refresh_categories_view()

    def open_category_editor(self, title, data, is_new=False):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Название категории:").pack(pady=5)
        name_entry = ctk.CTkEntry(dialog, width=400)
        name_entry.insert(0, data.get("name", ""))
        name_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="Библиотеки (через запятую):").pack(pady=5)
        libs_text = ctk.CTkTextbox(dialog, height=150)
        libs_text.insert("1.0", ", ".join(data.get("libs", [])))
        libs_text.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

        def save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Ошибка", "Имя категории не может быть пустым.")
                return
            libs = [lib.strip() for lib in libs_text.get("1.0", tk.END).strip().split(",") if lib.strip()]
            if is_new and name in CATEGORIES:
                messagebox.showerror("Ошибка", "Категория с таким именем уже существует.")
                return
            if is_new:
                CATEGORIES[name] = libs
            else:
                old_name = data["name"]
                if old_name != name:
                    CATEGORIES[name] = CATEGORIES.pop(old_name)
                else:
                    CATEGORIES[name] = libs
            self.refresh_categories_view()
            dialog.destroy()

        ctk.CTkButton(dialog, text="Сохранить", command=save).pack(pady=10)

    # ========== ВКЛАДКА "ИИ-АРХИТЕКТОР" ==========
    def setup_llm_tab(self):
        left_frame = ctk.CTkScrollableFrame(self.tab_llm, width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        ctk.CTkLabel(left_frame, text="Провайдер LLM:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5, pady=(5,0))
        provider_menu = ctk.CTkOptionMenu(left_frame, values=["Ollama", "OpenRouter"],
                                          variable=self.provider_var, command=self.on_provider_change)
        provider_menu.pack(fill=tk.X, padx=5, pady=5)

        self.provider_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        self.provider_frame.pack(fill=tk.X, padx=5, pady=5)
        self.create_ollama_widgets()
        self.create_openrouter_widgets()
        self.on_provider_change(self.provider_var.get())

        ctk.CTkButton(left_frame, text="Сохранить настройки", command=self.save_llm_settings).pack(fill=tk.X, padx=5, pady=10)
        
        ctk.CTkButton(left_frame, text="📂 Загрузить конфиг", command=self.load_config_file).pack(fill=tk.X, padx=5, pady=5)
        
        ctk.CTkButton(left_frame, text="🗑 Выйти из аккаунта", fg_color="red", hover_color="darkred",
                      command=self.logout_openrouter).pack(fill=tk.X, padx=5, pady=5)
                      
        ctk.CTkButton(left_frame, text="✅ Проверить подключение", command=self.test_connection).pack(fill=tk.X, padx=5, pady=5)

        # Подсказка
        ctk.CTkLabel(
            left_frame, 
            text="⚠️ Перед анализом задачи проверьте подключение к LLM", 
            text_color="orange", 
            font=("Helvetica", 11, "italic")
        ).pack(fill=tk.X, padx=10, pady=(0,10))

        right_frame = ctk.CTkFrame(self.tab_llm)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        ctk.CTkLabel(right_frame, text="Опишите вашу задачу:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.prompt_text = ctk.CTkTextbox(right_frame, height=120)
        self.prompt_text.pack(fill=tk.X, padx=10, pady=5)
        self.prompt_text.insert("1.0", "Мне нужен конвейер: поиск в сети, парсинг сайтов, распознавание графиков на картинках и сохранение структуры в мультимодальный RAG.")

        self.analyze_btn = ctk.CTkButton(right_frame, text="🚀 Анализировать и подобрать стек", command=self.analyze_task_async)
        self.analyze_btn.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkLabel(right_frame, text="Рекомендованные варианты архитектуры:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10,0))
        self.variants_frame = ctk.CTkScrollableFrame(right_frame, height=250)
        self.variants_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.variant_buttons = []

        ctk.CTkLabel(right_frame, text="Итоговый промпт для кодинга (скопируйте):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10,0))
        self.final_prompt = ctk.CTkTextbox(right_frame, height=150)
        self.final_prompt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Привязка событий для работы с буфером обмена
        self.final_prompt.bind("<Control-c>", self.copy_text)
        self.final_prompt.bind("<Control-a>", self.select_all)
        self.final_prompt.bind("<Button-3>", self.show_context_menu_final)  # ПКМ

        copy_btn = ctk.CTkButton(right_frame, text="📋 Копировать промпт", command=self.copy_final_prompt)
        copy_btn.pack(pady=5, padx=10)

        # Контекстное меню для final_prompt
        self.final_context_menu = tk.Menu(self, tearoff=0)
        self.final_context_menu.add_command(label="Копировать", command=self.copy_final_prompt)
        self.final_context_menu.add_command(label="Выделить всё", command=lambda: self.select_all(None))

    def create_ollama_widgets(self):
        self.ollama_frame = ctk.CTkFrame(self.provider_frame, fg_color="transparent")
        ctk.CTkLabel(self.ollama_frame, text="Ollama URL:").pack(anchor="w", padx=5)
        self.ollama_url_entry = ctk.CTkEntry(self.ollama_frame, textvariable=self.ollama_url_var)
        self.ollama_url_entry.pack(fill=tk.X, padx=5, pady=2)
        ctk.CTkLabel(self.ollama_frame, text="Модель:").pack(anchor="w", padx=5)
        self.ollama_model_entry = ctk.CTkEntry(self.ollama_frame, textvariable=self.ollama_model_var)
        self.ollama_model_entry.pack(fill=tk.X, padx=5, pady=2)
        ctk.CTkButton(self.ollama_frame, text="Загрузить список моделей", command=self.load_ollama_models).pack(fill=tk.X, padx=5, pady=5)

    def create_openrouter_widgets(self):
        self.openrouter_frame = ctk.CTkFrame(self.provider_frame, fg_color="transparent")

        # Верхняя строка: метка + чекбокс
        key_top_frame = ctk.CTkFrame(self.openrouter_frame, fg_color="transparent")
        key_top_frame.pack(fill=tk.X, padx=5, pady=(0, 2))

        ctk.CTkLabel(key_top_frame, text="API ключ:").pack(side=tk.LEFT)

        self.show_key_var = ctk.BooleanVar(value=False)
        show_btn = ctk.CTkCheckBox(
            key_top_frame,
            text="Показать",
            variable=self.show_key_var,
            command=self.toggle_api_key_visibility
        )
        show_btn.pack(side=tk.RIGHT)

        # Поле ввода
        self.openrouter_key_entry = ctk.CTkEntry(
            self.openrouter_frame,
            textvariable=self.openrouter_key_var,
            show="*"
        )
        self.openrouter_key_entry.pack(fill=tk.X, padx=5, pady=2)

        # Привязка событий
        self.openrouter_key_entry.bind("<Control-v>", self.paste_from_clipboard)
        self.openrouter_key_entry.bind("<Button-3>", self.show_context_menu)  # ПКМ

        # Контекстное меню
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Вставить", command=self.paste_from_clipboard)

        # Модель (сохраняем из старого метода, так как в новом коде её нет, но она нужна)
        ctk.CTkLabel(self.openrouter_frame, text="Модель:").pack(anchor="w", padx=5)
        self.openrouter_model_entry = ctk.CTkEntry(self.openrouter_frame, textvariable=self.openrouter_model_var)
        self.openrouter_model_entry.pack(fill=tk.X, padx=5, pady=2)

    def toggle_api_key_visibility(self):
        """Переключает видимость API-ключа"""
        if self.show_key_var.get():
            self.openrouter_key_entry.configure(show="")
        else:
            self.openrouter_key_entry.configure(show="*")

    def paste_from_clipboard(self, event=None):
        """Вставляет текст из буфера обмена"""
        try:
            clipboard_text = self.clipboard_get()
            if clipboard_text.strip():
                # Вставляем в текущее положение курсора
                self.openrouter_key_entry.insert(tk.INSERT, clipboard_text)
        except Exception as e:
            messagebox.showwarning("Буфер обмена", f"Не удалось вставить: {e}")

    def show_context_menu(self, event):
        """Показывает контекстное меню (ПКМ)"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def on_provider_change(self, choice):
        self.ollama_frame.pack_forget()
        self.openrouter_frame.pack_forget()
        if choice == "Ollama":
            self.ollama_frame.pack(fill=tk.X, pady=2)
        else:
            self.openrouter_frame.pack(fill=tk.X, pady=2)

    def logout_openrouter(self):
        """Очищает сохранённый OpenRouter API-ключ."""
        try:
            keyring.delete_password(SERVICE_NAME, "openrouter_api_key")
            self.openrouter_key_var.set("")
            self.config["openrouter_key"] = ""
            messagebox.showinfo("Выход", "Вы вышли. API-ключ удалён из системы.")
        except keyring.errors.PasswordDeleteError:
            messagebox.showinfo("Выход", "Ключ уже был удалён или не найден.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить ключ: {e}")

    def load_config_file(self):
        """Ручная загрузка конфигурационного файла."""
        file_path = filedialog.askopenfilename(
            title="Выберите файл настроек",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Валидация
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            # Загружаем ключ
            saved_key = keyring.get_password(SERVICE_NAME, "openrouter_api_key")
            if saved_key:
                cfg["openrouter_key"] = saved_key

            self.config = cfg
            # Применяем
            self.provider_var.set(cfg["provider"])
            self.ollama_url_var.set(cfg["ollama_url"])
            self.ollama_model_var.set(cfg["ollama_model"])
            self.openrouter_key_var.set(cfg.get("openrouter_key", ""))
            self.openrouter_model_var.set(cfg["openrouter_model"])

            # Сохраняем путь
            global CONFIG_FILE
            CONFIG_FILE = file_path
            self.config_path = file_path

            messagebox.showinfo("Готово", "Конфиг загружен!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить конфиг:\n{e}")

    def save_llm_settings(self):
        self.config["provider"] = self.provider_var.get()
        self.config["ollama_url"] = self.ollama_url_var.get()
        self.config["ollama_model"] = self.ollama_model_var.get()
        self.config["openrouter_key"] = self.openrouter_key_var.get()
        self.config["openrouter_model"] = self.openrouter_model_var.get()
        save_config(self.config)
        messagebox.showinfo("Сохранено", "Настройки LLM сохранены.\nТеперь нажмите 'Проверить подключение'.")

    def test_connection(self):
        provider = self.provider_var.get()
        self.analyze_btn.configure(state="disabled", text="Проверка...")

        def worker():
            try:
                if provider == "Ollama":
                    url = self.ollama_url_var.get().strip().rstrip('/') + "/api/tags"
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        models_count = len(resp.json().get("models", []))
                        msg = f"✅ Подключено к Ollama\nНайдено моделей: {models_count}"
                    else:
                        msg = f"❌ Ошибка: {resp.status_code} {resp.reason}"
                else:  # OpenRouter
                    api_key = self.openrouter_key_var.get().strip()
                    if not api_key:
                        raise ValueError("Введите API-ключ")
                    headers = {"Authorization": f"Bearer {api_key}"}
                    resp = requests.get("https://openrouter.ai/api/v1/auth", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        user = resp.json().get("data", {}).get("email", "аноним")
                        msg = f"✅ Авторизован как {user}"
                    else:
                        msg = f"❌ Ошибка авторизации: {resp.status_code}"

                self.after(0, lambda: messagebox.showinfo("Подключение", msg))
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Ошибка подключения", str(e)))
            finally:
                self.after(0, lambda: self.analyze_btn.configure(state="normal", text="🚀 Анализировать и подобрать стек"))

        threading.Thread(target=worker, daemon=True).start()

    def load_ollama_models(self):
        """Загружает и показывает список доступных моделей из Ollama."""
        self.analyze_btn.configure(state="disabled", text="Загрузка моделей...")

        def worker():
            try:
                url = self.ollama_url_var.get().strip().rstrip('/') + "/api/tags"
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}: {resp.text}")

                data = resp.json()
                models = [model["name"] for model in data.get("models", [])]
                if not models:
                    msg = "Нет установленных моделей."
                else:
                    msg = "\n".join(f"• {model}" for model in models[:20])
                    if len(models) > 20:
                        msg += f"\n... и ещё {len(models) - 20}"

                self.after(0, lambda: messagebox.showinfo("Модели Ollama", msg))
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Ошибка загрузки моделей", str(e)))
            finally:
                self.after(0, lambda: self.analyze_btn.configure(state="normal", text="🚀 Анализировать и подобрать стек"))

        threading.Thread(target=worker, daemon=True).start()

    def analyze_task_async(self):
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("Пустой промт", "Введите описание задачи.")
            return

        for widget in self.variants_frame.winfo_children():
            widget.destroy()
        self.variant_buttons.clear()
        self.final_prompt.delete("1.0", tk.END)

        self.analyze_btn.configure(state="disabled", text="ИИ анализирует...")
        threading.Thread(target=self._llm_analysis_worker, args=(prompt,), daemon=True).start()

    def _llm_analysis_worker(self, user_prompt):
        provider = self.provider_var.get()
        system_msg = (
            "Ты — опытный ИИ-архитектор Python. Проанализируй задачу пользователя и предложи 2-3 варианта стека технологий.\n"
            "Каждый вариант должен содержать: название, список библиотек (имена как в PyPI), категории и краткое обоснование.\n"
            "Ответ верни строго в формате JSON: [{\"name\": \"Вариант 1\", \"libraries\": [\"lib1\",\"lib2\"], \"categories\": [\"cat1\",\"cat2\"], \"reason\": \"обоснование\"}, ...]\n"
            "Не добавляй лишний текст, только JSON."
        )
        try:
            if provider == "Ollama":
                url = self.ollama_url_var.get().strip().rstrip('/') + "/api/generate"
                model = self.ollama_model_var.get().strip()
                if not model:
                    raise ValueError("Не указана модель Ollama")
                payload = {
                    "model": model,
                    "prompt": f"{system_msg}\n\nЗадача: {user_prompt}",
                    "stream": False
                }
                resp = requests.post(url, json=payload, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("response", "")
            else:  # OpenRouter
                api_key = self.openrouter_key_var.get().strip()
                if not api_key:
                    raise ValueError("Введите API ключ OpenRouter")
                model = self.openrouter_model_var.get().strip()
                if not model:
                    model = "openrouter/free"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000",  # или ваш домен
                    "X-Title": "PipManager+Architect"  # имя вашего приложения
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_prompt}
                    ]
                }
                resp = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                answer = data["choices"][0]["message"]["content"]

            variants = extract_json_safely(answer)
            if not variants:
                raise ValueError(f"LLM не вернул корректный JSON. Ответ: {answer[:500]}")

            self.after(0, self._display_variants, variants, user_prompt)

        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Ошибка LLM", str(e)))
        finally:
            self.after(0, lambda: self.analyze_btn.configure(state="normal", text="🚀 Анализировать и подобрать стек"))

    def _display_variants(self, variants, original_prompt):
        for widget in self.variants_frame.winfo_children():
            widget.destroy()
        self.variant_buttons.clear()

        for idx, v in enumerate(variants):
            frame = ctk.CTkFrame(self.variants_frame)
            frame.pack(fill=tk.X, padx=5, pady=5)
            ctk.CTkLabel(frame, text=v.get("name", f"Вариант {idx+1}"), font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5)
            libs_str = ", ".join(v.get("libraries", []))
            ctk.CTkLabel(frame, text=f"📚 Библиотеки: {libs_str}", wraplength=400, justify="left").pack(anchor="w", padx=5)
            ctk.CTkLabel(frame, text=f"📂 Категории: {', '.join(v.get('categories', []))}", wraplength=400).pack(anchor="w", padx=5)
            ctk.CTkLabel(frame, text=f"💡 Обоснование: {v.get('reason', '')}", wraplength=400).pack(anchor="w", padx=5)
            btn = ctk.CTkButton(frame, text="Выбрать этот вариант", command=lambda var=v, orig=original_prompt: self.build_final_prompt(var, orig))
            btn.pack(pady=2, padx=5, anchor="e")
            self.variant_buttons.append(btn)

    def build_final_prompt(self, chosen_variant, original_prompt):
        libs = chosen_variant.get("libraries", [])
        categories = chosen_variant.get("categories", [])
        reason = chosen_variant.get("reason", "")

        installed_list = ", ".join(self.installed_packages.keys())

        final = f"""# Исходная задача:
{original_prompt}

# Рекомендованный стек технологий (ИИ-архитектор):
Библиотеки: {', '.join(libs)}
Категории: {', '.join(categories)}
Обоснование: {reason}

# Текущее окружение разработчика:
В системе уже установлены: {installed_list}
По возможности используй эти библиотеки для совместимости.

# Задание для кодогенерации:
Напиши готовый к запуску код на Python, решающий поставленную задачу с использованием рекомендованного стека. Код должен быть модульным, с обработкой ошибок, без заглушек."""
        self.final_prompt.delete("1.0", tk.END)
        self.final_prompt.insert(tk.END, final)
        self.tabview.set("🤖 ИИ-Архитектор")
        messagebox.showinfo("Промпт сформирован", "Итоговый промпт готов к копированию.")

    def copy_final_prompt(self):
        text = self.final_prompt.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Пусто", "Нечего копировать.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Скопировано", "Промпт скопирован в буфер обмена.")

    def auto_categorize_with_llm(self):
        """Запрашивает у LLM автоматическую группировку установленных пакетов по категориям."""
        if not self.installed_packages:
            messagebox.showwarning("Нет данных", "Сначала обновите список пакетов.")
            return

        libs_list = ", ".join(sorted(self.installed_packages.keys()))
        prompt = f"""
Проанализируй этот список Python-библиотек и сгруппируй их в логические категории (например: 'Веб', 'ML', 'Утилиты' и т.д.).

Список библиотек: {libs_list}

Верни строго JSON в формате:
[
  {{
    "category": "Название категории",
    "libraries": ["lib1", "lib2"]
  }},
  ...
]

Не добавляй комментарии.
"""

        self.auto_cat_btn.configure(state="disabled", text="🧠 Анализирую...")
        threading.Thread(target=self._auto_cat_worker, args=(prompt,), daemon=True).start()

    def _auto_cat_worker(self, prompt):
        try:
            url = self.config["ollama_url"].strip().rstrip("/") + "/api/generate"
            model = self.config["ollama_model"].strip()
            if not model:
                raise ValueError("Модель Ollama не указана")

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            resp = requests.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            answer = resp.json().get("response", "")

            data = extract_json_safely(answer)
            if not data:
                raise ValueError(f"LLM не вернул корректный JSON: {answer[:300]}")

            new_cats = {}
            for item in data:
                cat_name = item.get("category", "Без категории")
                libs = [lib.strip() for lib in item.get("libraries", []) if lib.strip()]
                if cat_name and libs:
                    new_cats[cat_name] = libs

            if not new_cats:
                raise ValueError("LLM вернул пустые категории.")

            # Сохраняем и обновляем
            global CATEGORIES
            CATEGORIES.update(new_cats)  # Можно заменить на = если хочешь перезаписать
            self.after(0, self.refresh_categories_view)
            messagebox.showinfo("Готово", f"Автоматически создано {len(new_cats)} новых категорий.")
        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Ошибка LLM", str(e)))
        finally:
            self.after(0, lambda: self.auto_cat_btn.configure(state="normal", text="🧠 Авто-категоризация (LLM)"))

    def select_global_env(self):
        self.python_path = sys.executable
        self.python_path_label.configure(text=self.python_path)
        self.config["python_path"] = self.python_path
        save_config(self.config)
        self.refresh_packages_async()

    def select_venv_env(self):
        file_path = filedialog.askopenfilename(
            title="Выберите исполняемый файл Python внутри .venv",
            filetypes=[("Python executable", "*.exe"), ("Python", "python"), ("Python3", "python3")]
        )
        if file_path:
            self.python_path = file_path
            self.python_path_label.configure(text=self.python_path)
            self.config["python_path"] = file_path
            save_config(self.config)
            self.refresh_packages_async()

    def import_requirements(self):
        """Загружает и анализирует файл requirements.txt"""
        file_path = filedialog.askopenfilename(
            title="Выберите requirements.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            parsed_packages = {}
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Поддержка: package==version, package>=version, package
                match = re.match(r"^([a-zA-Z0-9\-_]+)", line)
                if match:
                    name = match.group(1).strip()
                    # Нормализуем имя (например, requests-toolbelt → requests_toolbelt)
                    norm_name = name.replace("-", "_").lower()
                    parsed_packages[norm_name] = {
                        "display_name": name,
                        "required_version": line[len(match.group(1)):].strip(),
                        "current_version": "не установлена",
                        "latest_version": "проверяется...",
                        "status": "отсутствует"
                    }

            if not parsed_packages:
                messagebox.showinfo("Результат", "Файл пуст или не содержит пакетов.")
                return

            # Показать окно анализа
            self.show_requirements_analysis(parsed_packages)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")

    def show_requirements_analysis(self, reqs):
        """Показывает окно с анализом зависимостей"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Анализ requirements.txt")
        dialog.geometry("900x700")
        dialog.transient(self)
        dialog.grab_set()

        # Заголовок
        ctk.CTkLabel(dialog, text="Анализ зависимостей", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        # Таблица
        columns = ("package", "required", "installed", "latest", "status", "category")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col.capitalize())
        tree.column("package", width=180)
        tree.column("required", width=120)
        tree.column("installed", width=120)
        tree.column("latest", width=120)
        tree.column("status", width=100)
        tree.column("category", width=150)

        # Стиль
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2d2e", foreground="white", rowheight=28)
        style.map('Treeview', background=[('selected', '#1f6aa5')])
        style.configure("Treeview.Heading", background="#565b5e", foreground="white")

        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Прокрутка
        scroll = ctk.CTkScrollbar(dialog, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,10), pady=5)

        # Кнопки
        btn_frame = ctk.CTkFrame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        ctk.CTkButton(btn_frame, text="🔍 Проверить актуальность", command=lambda: self.check_versions_for_reqs(tree, reqs)).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="🤖 Проанализировать с ИИ", fg_color="purple", command=lambda: self.analyze_reqs_with_llm(reqs)).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="Закрыть", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # Заполняем начальные данные
        for norm_name, data in reqs.items():
            cat = get_category(data["display_name"])
            item = tree.insert("", tk.END, values=(
                data["display_name"],
                data["required_version"],
                data["current_version"],
                data["latest_version"],
                data["status"],
                cat
            ))
            reqs[norm_name]["tree_item"] = item  # сохраним для обновления

        # Сохраняем в атрибут
        self.current_reqs_analysis = {"tree": tree, "reqs": reqs}

    def check_versions_for_reqs(self, tree, reqs):
        """Проверяет, какие пакеты установлены и актуальны"""
        threading.Thread(target=self._check_versions_worker, args=(tree, reqs), daemon=True).start()

    def _check_versions_worker(self, tree, reqs):
        try:
            # Получаем список установленных
            proc = subprocess.run(
                [self.python_path, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, check=True
            )
            installed = {pkg["name"].lower().replace("-", "_"): pkg["version"]
                         for pkg in json.loads(proc.stdout)}

            # Получаем устаревшие
            proc_out = subprocess.run(
                [self.python_path, "-m", "pip", "list", "--outdated", "--format=json"],
                capture_output=True, text=True
            )
            outdated = {}
            if proc_out.returncode == 0 and proc_out.stdout.strip():
                for pkg in json.loads(proc_out.stdout):
                    name = pkg["name"].lower().replace("-", "_")
                    outdated[name] = pkg["latest_version"]

            # Обновляем дерево
            for norm_name, data in reqs.items():
                display_name = data["display_name"]
                norm_key = norm_name  # уже нормализовано

                current = installed.get(norm_key, "не установлена")
                latest = outdated.get(norm_key, current) if current != "не установлена" else "—"
                status = "Актуален"
                if current == "не установлена":
                    status = "Отсутствует"
                elif norm_key in outdated:
                    status = "Устарел"

                # Обновляем строку
                item = data["tree_item"]
                tree.set(item, "installed", current)
                tree.set(item, "latest", latest)
                tree.set(item, "status", status)

                # Цветовая подсветка
                if status == "Отсутствует":
                    tree.item(item, tags=("missing",))
                elif status == "Устарел":
                    tree.item(item, tags=("outdated",))

            # Теги
            tree.tag_configure("missing", background="#5c2424")
            tree.tag_configure("outdated", background="#4a3d1a")

        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Ошибка", f"Не удалось проверить версии: {e}"))

    def analyze_reqs_with_llm(self, reqs):
        """Отправляет список пакетов на анализ в LLM"""
        libs_info = []
        for data in reqs.values():
            libs_info.append(f"{data['display_name']} {data['required_version']}")

        prompt = f"""
Проанализируй этот стек Python-библиотек из requirements.txt:

{chr(10).join(libs_info)}

Определи:
1. Назначение проекта (веб, ML, парсинг и т.д.)
2. Возможные проблемы (устаревшие версии, конфликты, уязвимости)
3. Рекомендации по улучшению (обновления, замены, оптимизация)

Ответь кратко и по делу.
"""

        provider = self.provider_var.get()

        self.after(0, lambda: messagebox.showinfo("Анализ", "ИИ анализирует стек..."))

        threading.Thread(target=self._analyze_reqs_worker, args=(prompt,), daemon=True).start()

    def _analyze_reqs_worker(self, prompt):
        try:
            if self.config["provider"] == "Ollama":
                url = self.config["ollama_url"].strip().rstrip("/") + "/api/generate"
                payload = {
                    "model": self.config["ollama_model"],
                    "prompt": prompt,
                    "stream": False
                }
                resp = requests.post(url, json=payload, timeout=60)
                resp.raise_for_status()
                answer = resp.json().get("response", "")
            else:
                api_key = self.config["openrouter_key"].strip()
                if not api_key:
                    raise ValueError("API ключ не задан")
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "PipManager+Architect"
                }
                payload = {
                    "model": self.config["openrouter_model"],
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                resp = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=60)
                resp.raise_for_status()
                answer = resp.json()["choices"][0]["message"]["content"]

            self.after(0, lambda: messagebox.showinfo("Результат анализа", answer[:4000] + "..." if len(answer) > 4000 else answer))

        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("Ошибка LLM", str(e)))


    def copy_text(self, event=None):
        """Копирует выделенный текст в буфер"""
        try:
            selected_text = self.final_prompt.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(selected_text)
        except tk.TclError:
            # Ничего не выделено
            pass
        return "break"  # блокируем стандартное поведение

    def select_all(self, event=None):
        """Выделяет весь текст"""
        self.final_prompt.tag_add("sel", "1.0", "end")
        self.final_prompt.mark_set("insert", "1.0")
        self.final_prompt.see("insert")
        return "break"

    def show_context_menu_final(self, event):
        """Показывает контекстное меню при ПКМ"""
        try:
            self.final_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.final_context_menu.grab_release()

# ======================= ЗАПУСК ПРИЛОЖЕНИЯ =======================
if __name__ == "__main__":
    app = UnifiedPipApp()
    app.mainloop()