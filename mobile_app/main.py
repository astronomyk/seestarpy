import sys
import os

# Add parent src directory to path for local seestarpy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import AsyncImage
from kivy.core.window import Window
import inspect
import json
import socket
from typing import get_type_hints

# Import your seestarpy package
try:
    import seestarpy
    from seestarpy import connection
    # We'll dynamically import modules as needed
except ImportError:
    # Fallback for testing without the package
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

        # Main layout
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Logo
        logo = AsyncImage(
            source='https://raw.githubusercontent.com/astronomyk/seestarpy/master/docs/_static/seestar_py_logo_banner.png',
            size_hint_y=None,
            height=80,
            allow_stretch=True
        )
        main_layout.add_widget(logo)

        # IP Address input
        ip_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=44,
            spacing=10
        )
        ip_label = Label(
            text='Device IP:',
            size_hint_x=0.25,
            font_size='16sp'
        )
        self.ip_input = TextInput(
            text='192.168.4.1',
            multiline=False,
            size_hint_x=0.55,
            font_size='16sp'
        )
        self.set_ip_btn = Button(
            text='Set IP',
            size_hint_x=0.2,
            background_color=(0.8, 0.2, 0.2, 1)  # Red by default
        )
        self.set_ip_btn.bind(on_press=self.set_device_ip)
        ip_layout.add_widget(ip_label)
        ip_layout.add_widget(self.ip_input)
        ip_layout.add_widget(self.set_ip_btn)
        main_layout.add_widget(ip_layout)

        # Module and Function selectors with Execute button
        selector_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=98,  # Height for 2 rows of 44 each + spacing
            spacing=10
        )

        # Left side: Module and Function dropdowns stacked
        dropdown_container = BoxLayout(
            orientation='vertical',
            size_hint_x=0.75,
            spacing=10
        )

        # Module selector dropdown
        self.module_spinner = Spinner(
            text='Select Module',
            values=self.get_module_names(),
            size_hint_y=None,
            height=44
        )
        self.module_spinner.bind(text=self.on_module_selected)
        dropdown_container.add_widget(self.module_spinner)

        # Function selector
        self.function_spinner = Spinner(
            text='Select Function',
            values=[],
            size_hint_y=None,
            height=44
        )
        self.function_spinner.bind(text=self.on_function_selected)
        dropdown_container.add_widget(self.function_spinner)

        selector_layout.add_widget(dropdown_container)

        # Right side: Execute button (spans full height)
        self.submit_btn = Button(
            text='Execute',
            size_hint_x=0.25,
            background_color=(0.2, 0.6, 0.2, 1),
            disabled=True
        )
        self.submit_btn.bind(on_press=self.execute_function)
        selector_layout.add_widget(self.submit_btn)

        main_layout.add_widget(selector_layout)

        # Scrollable area for parameters
        scroll = ScrollView(size_hint=(1, 0.4))
        self.param_layout = GridLayout(
            cols=1,
            spacing=5,
            size_hint_y=None
        )
        self.param_layout.bind(
            minimum_height=self.param_layout.setter('height'))
        scroll.add_widget(self.param_layout)
        main_layout.add_widget(scroll)

        # Docstring display
        docstring_label = Label(
            text='Function Documentation:',
            size_hint_y=None,
            height=30,
            font_size='14sp',
            bold=True
        )
        main_layout.add_widget(docstring_label)

        self.docstring_text = TextInput(
            text='',
            readonly=True,
            size_hint_y=None,
            height=100,
            multiline=True
        )
        main_layout.add_widget(self.docstring_text)

        # Response display
        response_label = Label(
            text='Response:',
            size_hint_y=None,
            height=30,
            font_size='14sp',
            bold=True
        )
        main_layout.add_widget(response_label)

        self.response_text = TextInput(
            text='',
            readonly=True,
            size_hint_y=None,
            height=150,
            multiline=True
        )
        main_layout.add_widget(self.response_text)

        return main_layout

    def get_module_names(self):
        """Get all modules from seestarpy package."""
        if seestarpy is None:
            return ['Demo Mode - No Modules']

        modules = []
        for name in dir(seestarpy):
            if not name.startswith('_'):
                attr = getattr(seestarpy, name)
                # Check if it's a module
                if inspect.ismodule(attr) and hasattr(attr, '__file__'):
                    # Only include modules that are part of seestarpy
                    if attr.__name__.startswith('seestarpy.'):
                        module_short_name = attr.__name__.split('.')[-1]
                        modules.append(module_short_name)

        return sorted(modules)

    def on_module_selected(self, spinner, text):
        """Handle module selection and update function dropdown."""
        if text == 'Select Module' or seestarpy is None:
            self.function_spinner.values = []
            self.function_spinner.text = 'Select Function'
            self.submit_btn.disabled = True
            return

        # Import the selected module
        try:
            module_name = f'seestarpy.{text}'
            if module_name in seestarpy.__dict__:
                self.current_module = getattr(seestarpy, text)
            else:
                # Try dynamic import
                import importlib
                self.current_module = importlib.import_module(module_name)

            # Update function dropdown with functions from this module
            self.function_spinner.values = self.get_function_names()
            self.function_spinner.text = 'Select Function'

            # Clear previous parameters and disable submit
            self.param_layout.clear_widgets()
            self.param_inputs.clear()
            self.submit_btn.disabled = True
            self.docstring_text.text = ''

        except Exception as e:
            self.response_text.text = f'Error loading module: {str(e)}'
            self.function_spinner.values = []

    def get_function_names(self):
        """Get all callable functions from selected module."""
        if self.current_module is None:
            return []

        functions = []
        self.function_map.clear()
        for name in dir(self.current_module):
            if not name.startswith('_'):
                attr = getattr(self.current_module, name)
                if callable(attr):
                    functions.append(name)
                    self.function_map[name] = attr

        return sorted(functions)

    def set_device_ip(self, instance):
        """Set the DEFAULT_IP in seestarpy.connection module with connectivity check."""
        if connection is None:
            self.response_text.text = 'Error: seestarpy.connection not available'
            return

        ip_address = self.ip_input.text.strip()
        if not ip_address:
            self.response_text.text = 'Error: IP address cannot be empty'
            return

        # Check connectivity
        self.response_text.text = f'Checking connection to {ip_address}...'

        # Try to connect to common Seestar port (typically 4700 for the API)
        # or use a simple TCP ping on port 80
        is_reachable = False
        error_msg = ''

        # Try common ports
        ports_to_try = [4700, 80]

        for port in ports_to_try:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)  # 2 second timeout
                result = sock.connect_ex((ip_address, port))
                sock.close()

                if result == 0:
                    is_reachable = True
                    break
            except socket.gaierror:
                error_msg = 'Invalid IP address format'
                break
            except Exception as e:
                error_msg = str(e)

        if is_reachable:
            try:
                connection.DEFAULT_IP = ip_address
                self.set_ip_btn.background_color = (
                0.2, 0.7, 0.2, 1)  # Green on success
                self.response_text.text = f'✓ Device IP set to: {ip_address}\nConnection verified!'
            except Exception as e:
                self.response_text.text = f'Error setting IP: {str(e)}'
        else:
            self.set_ip_btn.background_color = (
            0.8, 0.2, 0.2, 1)  # Back to red on failure
            if error_msg:
                self.response_text.text = f'✗ Cannot reach {ip_address}\n{error_msg}\n\nIP not updated. Check device connection.'
            else:
                self.response_text.text = f'✗ Cannot reach {ip_address} on ports {ports_to_try}\n\nIP not updated. Is the device connected?'

    def on_function_selected(self, spinner, text):
        """Handle function selection and create input fields."""
        if text == 'Select Function' or text not in self.function_map:
            return

        # Clear previous parameters
        self.param_layout.clear_widgets()
        self.param_inputs.clear()

        # Get the selected function
        func = self.function_map[text]

        # Update docstring
        docstring = inspect.getdoc(func) or 'No documentation available.'
        self.docstring_text.text = docstring

        # Get function signature
        sig = inspect.signature(func)

        # Create input fields for each parameter
        for param_name, param in sig.parameters.items():
            # Skip 'self' parameter
            if param_name == 'self':
                continue

            # Create a row for this parameter
            param_row = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                height=40,
                spacing=5
            )

            # Parameter label (just the name)
            param_label = Label(
                text=f"{param_name}:",
                size_hint_x=None,
                width=150,  # Fixed width to accommodate long names
                halign='right',
                valign='middle',
                text_size=(150, None)
            )
            param_row.add_widget(param_label)

            # Parameter input with default value in the textbox
            default_value = ''
            if param.default != inspect.Parameter.empty:
                if param.default is not None:
                    default_value = str(param.default)

            param_input = TextInput(
                text=default_value,
                multiline=False,
                size_hint_x=1
            )
            self.param_inputs[param_name] = param_input
            param_row.add_widget(param_input)

            self.param_layout.add_widget(param_row)

        # Enable submit button
        self.submit_btn.disabled = False

    def execute_function(self, instance):
        """Execute the selected function with provided parameters."""
        selected_func = self.function_spinner.text

        if selected_func not in self.function_map:
            self.response_text.text = 'Error: No function selected'
            return

        func = self.function_map[selected_func]

        # Collect parameters
        kwargs = {}
        sig = inspect.signature(func)

        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            if param_name in self.param_inputs:
                value_str = self.param_inputs[param_name].text.strip()

                # If empty and has default, skip it
                if not value_str and param.default != inspect.Parameter.empty:
                    continue

                # Try to parse the value
                try:
                    # Try to evaluate as Python literal (handles int, float, bool, None, lists, dicts)
                    if value_str:
                        kwargs[param_name] = eval(value_str)
                    elif param.default == inspect.Parameter.empty:
                        # Required parameter with no value
                        self.response_text.text = f'Error: {param_name} is required'
                        return
                except:
                    # If eval fails, treat as string
                    kwargs[param_name] = value_str

        # Execute the function
        try:
            self.response_text.text = 'Executing...'
            result = func(**kwargs)

            # Format response
            if result is not None:
                if isinstance(result, (dict, list)):
                    response_str = json.dumps(result, indent=2)
                else:
                    response_str = str(result)
            else:
                response_str = 'Success (no return value)'

            self.response_text.text = response_str

        except Exception as e:
            self.response_text.text = f'Error: {str(e)}\n\nType: {type(e).__name__}'


if __name__ == '__main__':
    SeestarControllerApp().run()