from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import AsyncImage
from kivy.uix.checkbox import CheckBox
from kivy.core.window import Window
from kivy.clock import Clock
import inspect
import json
import socket
import threading
import traceback
import ast
from typing import get_type_hints, Literal, get_origin, get_args

try:
    import seestarpy
    from seestarpy import connection
except ImportError:
    seestarpy = None
    connection = None
    print("Warning: seestarpy not found. Running in demo mode.")


class SeestarControllerApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.function_map = {}
        self.param_inputs = {}
        self.param_layout = None
        self.current_module = None

    def build(self):
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Logo
        logo = AsyncImage(
            source='https://raw.githubusercontent.com/astronomyk/seestarpy/master/docs/_static/seestar_py_logo_banner.png',
            size_hint_y=None,
            height=80,
            allow_stretch=True
        )
        main_layout.add_widget(logo)

        # =========================
        # TOP SECTION (Left: IP + dropdowns, Right: buttons)
        # =========================
        # Heights: 44 (IP) + 10 (spacing) + 44 (Module) + 10 (spacing) + 44 (Function) = 152
        TOP_SECTION_HEIGHT = 152

        top_section = BoxLayout(orientation='horizontal', size_hint_y=None, height=TOP_SECTION_HEIGHT, spacing=10)

        # Left panel holds: Row 1 (IP controls), Row 2 (Module/Function dropdowns)
        left_panel = BoxLayout(orientation='vertical', size_hint_x=0.75, spacing=10)

        # --- Row 1: IP controls ---
        ip_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=44, spacing=10)
        # Replace label with Set IP button
        self.set_ip_btn = Button(text='Set IP', size_hint_x=None, width=120, background_color=(0.8, 0.2, 0.2, 1))
        self.set_ip_btn.bind(on_press=self.set_device_ip)
        ip_row.add_widget(self.set_ip_btn)
        # IP input should line up with the right edge of the dropdown menus
        self.ip_input = TextInput(text='192.168.4.1', multiline=False, size_hint_x=1, font_size='16sp')
        ip_row.add_widget(self.ip_input)
        left_panel.add_widget(ip_row)

        # --- Row 2: Module/function dropdowns stacked ---
        dropdowns = BoxLayout(orientation='vertical', size_hint_x=1, size_hint_y=None, height=98, spacing=10)
        self.module_spinner = Spinner(text='Select Module', values=self.get_module_names(), size_hint_y=None, height=44)
        self.module_spinner.bind(text=self.on_module_selected)
        dropdowns.add_widget(self.module_spinner)

        self.function_spinner = Spinner(text='Select Function', values=[], size_hint_y=None, height=44)
        self.function_spinner.bind(text=self.on_function_selected)
        dropdowns.add_widget(self.function_spinner)

        left_panel.add_widget(dropdowns)
        top_section.add_widget(left_panel)

        # Right panel: two stacked buttons
        # Top button spans two lines (IP + Module) => 44 + 10 + 44 = 98
        # Bottom button aligns with Function dropdown => 44
        right_panel = BoxLayout(orientation='vertical', size_hint_x=0.25, spacing=10)

        self.submit_btn = Button(
            text='Execute',
            size_hint_y=None,
            height=98,
            background_color=(0.2, 0.6, 0.2, 1),
            disabled=True,
        )
        self.submit_btn.bind(on_press=self.execute_function)
        right_panel.add_widget(self.submit_btn)

        self.show_docs_btn = Button(
            text='Show Docs',
            size_hint_y=None,
            height=44,
        )
        self.show_docs_btn.bind(on_press=self.show_docstring)
        right_panel.add_widget(self.show_docs_btn)

        top_section.add_widget(right_panel)
        main_layout.add_widget(top_section)

        # =========================
        # PARAMETERS + RESPONSE SECTION
        # =========================
        middle_section = BoxLayout(orientation='vertical', spacing=10, size_hint_y=1)

        # Parameters (dynamic)
        self.param_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.param_container.bind(minimum_height=self.param_container.setter('height'))
        self.param_layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.param_layout.bind(minimum_height=self.param_layout.setter('height'))
        self.param_container.add_widget(self.param_layout)
        param_scroll = ScrollView(size_hint=(1, None), size=(0, 0))
        param_scroll.add_widget(self.param_container)
        self.param_scroll = param_scroll
        middle_section.add_widget(param_scroll)

        # Response fills remaining area
        response_label = Label(text='Response:', size_hint_y=None, height=30, font_size='14sp', bold=True)
        middle_section.add_widget(response_label)

        self.response_text = TextInput(
            text='',
            readonly=True,
            size_hint_y=1,
            multiline=True,
        )
        self.response_text.bind(text=self._on_response_text_change)
        middle_section.add_widget(self.response_text)

        main_layout.add_widget(middle_section)
        return main_layout

    # ----------------------------
    # Auto-scroll logic
    # ----------------------------
    def _on_response_text_change(self, instance, value):
        Clock.schedule_once(lambda dt: self._scroll_response_to_bottom())

    def _scroll_response_to_bottom(self):
        try:
            end_index = len(self.response_text.text)
            self.response_text.cursor = (end_index, 0)
        except Exception:
            pass

    # ----------------------------
    # Show docstring of selected function
    # ----------------------------
    def show_docstring(self, instance):
        fn = self.function_spinner.text
        if fn not in self.function_map:
            self.response_text.text = 'No function selected.'
            return
        func = self.function_map[fn]
        doc = inspect.getdoc(func) or 'No documentation available.'
        # Pretty print with a header
        self.response_text.text = f"=== {fn} — Documentation ===\n\n{doc}"

    # ----------------------------
    # Module discovery
    # ----------------------------
    def get_module_names(self):
        if seestarpy is None:
            return ['Demo Mode - No Modules']
        modules = []
        for name in dir(seestarpy):
            if not name.startswith('_'):
                attr = getattr(seestarpy, name)
                if inspect.ismodule(attr) and hasattr(attr, '__file__') and attr.__name__.startswith('seestarpy.'):
                    modules.append(attr.__name__.split('.')[-1])
        return sorted(modules)

    def on_module_selected(self, spinner, text):
        if text == 'Select Module' or seestarpy is None:
            self.function_spinner.values = []
            self.function_spinner.text = 'Select Function'
            self.submit_btn.disabled = True
            return
        try:
            import importlib
            self.current_module = importlib.import_module(f'seestarpy.{text}')
            self.function_spinner.values = self.get_function_names()
            self.function_spinner.text = 'Select Function'
            self.param_layout.clear_widgets()
            self.param_inputs.clear()
            self.submit_btn.disabled = True
        except Exception as e:
            self.response_text.text = f'Error loading module: {e}'
            self.function_spinner.values = []

    def get_function_names(self):
        if self.current_module is None:
            return []
        functions = []
        self.function_map.clear()
        modname = self.current_module.__name__
        for name, attr in vars(self.current_module).items():
            if name.startswith('_'):
                continue
            if inspect.isfunction(attr) and getattr(attr, '__module__', '') == modname:
                functions.append(name)
                self.function_map[name] = attr
        return sorted(functions)

    # ----------------------------
    # Networking: set device IP (non-blocking)
    # ----------------------------
    def set_device_ip(self, instance):
        if connection is None:
            self.response_text.text = 'Error: seestarpy.connection not available'
            return
        ip = self.ip_input.text.strip()
        if not ip:
            self.response_text.text = 'Error: IP address cannot be empty'
            return
        self.response_text.text = f'Checking connection to {ip}...'
        self.set_ip_btn.background_color = (0.8, 0.5, 0.2, 1)

        def worker():
            ports = [4700, 80, 8080]
            reachable = False
            err = ''
            for p in ports:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    res = sock.connect_ex((ip, p))
                    sock.close()
                    if res == 0:
                        reachable = True
                        break
                except Exception as e:
                    err = str(e)
            def finish(dt):
                if reachable:
                    try:
                        connection.DEFAULT_IP = ip
                        self.set_ip_btn.background_color = (0.2, 0.7, 0.2, 1)
                        self.response_text.text = f'\u2713 Device IP set to: {ip}\nConnection verified!'
                    except Exception as e:
                        self.response_text.text = f'Error setting IP: {e}'
                else:
                    self.set_ip_btn.background_color = (0.8, 0.2, 0.2, 1)
                    self.response_text.text = f'\u2717 Cannot reach {ip}\n{err}\nIP not updated.'
            Clock.schedule_once(finish)
        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------
    # Execution helpers
    # ----------------------------
    def _set_response_safe(self, text):
        Clock.schedule_once(lambda dt: setattr(self.response_text, 'text', text))

    def _call_func_bg(self, func, kwargs):
        try:
            result = func(**kwargs)
            if isinstance(result, (dict, list)):
                result = json.dumps(result, indent=2)
            elif result is None:
                result = 'Success (no return value)'
            self._set_response_safe(str(result))
        except Exception as e:
            tb = traceback.format_exc(limit=5)
            self._set_response_safe(f'Error: {e}\nType: {type(e).__name__}\n{tb}')

    def _parse_by_hint(self, text, hint):
        if not text:
            return None
        try:
            return ast.literal_eval(text)
        except Exception:
            return text

    def _build_param_widget(self, name, param, hint):
        origin = get_origin(hint)
        args = get_args(hint)
        if hint is bool:
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=5)
            row.add_widget(Label(text=f'{name}:', size_hint_x=None, width=150))
            cb = CheckBox(active=bool(param.default) if param.default != inspect.Parameter.empty else False)
            row.add_widget(cb)
            self.param_inputs[name] = {'_kind': 'bool', 'checkbox': cb}
            return row
        if origin is Literal and args:
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=5)
            row.add_widget(Label(text=f'{name}:', size_hint_x=None, width=150))
            sp = Spinner(text=str(param.default) if param.default != inspect.Parameter.empty else str(args[0]), values=[str(a) for a in args])
            row.add_widget(sp)
            self.param_inputs[name] = {'_kind': 'literal', 'spinner': sp}
            return row
        row = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=5)
        row.add_widget(Label(text=f'{name}:', size_hint_x=None, width=150))
        ti = TextInput(text=str(param.default) if param.default != inspect.Parameter.empty else '', multiline=False)
        row.add_widget(ti)
        self.param_inputs[name] = ti
        return row

    def on_function_selected(self, spinner, text):
        if text == 'Select Function' or text not in self.function_map:
            return
        self.param_layout.clear_widgets()
        self.param_inputs.clear()
        func = self.function_map[text]
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        count = 0
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            count += 1
            self.param_layout.add_widget(self._build_param_widget(name, param, hints.get(name)))
        self.param_scroll.height = min(count * 45, 300) if count > 0 else 0
        self.submit_btn.disabled = False

    def execute_function(self, instance):
        fn = self.function_spinner.text
        if fn not in self.function_map:
            self.response_text.text = 'Error: No function selected'
            return
        func = self.function_map[fn]
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}
        kwargs = {}
        for n, p in sig.parameters.items():
            if n == 'self':
                continue
            w = self.param_inputs.get(n)
            if isinstance(w, dict):
                if w.get('_kind') == 'bool':
                    kwargs[n] = w['checkbox'].active
                    continue
                if w.get('_kind') == 'literal':
                    kwargs[n] = w['spinner'].text
                    continue
            val = w.text.strip() if isinstance(w, TextInput) else ''
            if not val and p.default == inspect.Parameter.empty:
                self.response_text.text = f'Error: {n} is required'
                return
            if val:
                kwargs[n] = self._parse_by_hint(val, hints.get(n))
        self.response_text.text = 'Executing...'
        threading.Thread(target=self._call_func_bg, args=(func, kwargs), daemon=True).start()


if __name__ == '__main__':
    SeestarControllerApp().run()
