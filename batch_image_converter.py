"""Batch image converter"""


import datetime
import os.path
import random
import re
import sys

from PySide6.QtWidgets import QLineEdit, QLabel, QSlider, QFileDialog, QErrorMessage, QCheckBox, QGroupBox, QMessageBox
from PySide6.QtCore import Qt, Signal, QAbstractTableModel
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton,
                               QHBoxLayout)


EXT_MATCHERS = {
    'bmp': re.compile(r'bmp', flags=re.IGNORECASE),
    'gif': re.compile(r'gif', flags=re.IGNORECASE),
    'jpg': re.compile(r'(jpg|jpeg)', flags=re.IGNORECASE),
    'png': re.compile(r'png', flags=re.IGNORECASE),
    'tiff': re.compile(r'(tif|tiff)', flags=re.IGNORECASE),
    'webp': re.compile(r'webp', flags=re.IGNORECASE),
}
EXTENSIONS = set(EXT_MATCHERS)


class ExtensionPicker(QWidget):

    request_extension_updated = Signal(str, bool)

    def __init__(self, initial_values, parent=None):
        # initial_values format is {'png': False} format, for all keys in EXTENSIONS
        super().__init__()

        # Holds extension checkbox controls
        extension_controls = {
            # Example key/values:
            #   'png': QCheckbox()
            key: None for key in EXT_MATCHERS
        }
        self.extension_controls = extension_controls

        # Set some initial properties
        layout = QVBoxLayout()
        self.setWindowTitle('Extension Picker')
        self.setWindowModality(Qt.ApplicationModal)
        self.setLayout(layout)

        layout.addWidget(QLabel('Select Extensions:'), alignment=Qt.AlignHCenter)

        extension_selector_area = QVBoxLayout()
        layout.addLayout(extension_selector_area)

        for ext in EXT_MATCHERS.keys():
            # Add a label with the ext name and some spacing
            ext_layout = QHBoxLayout()
            ext_layout.addStretch()
            ext_layout.addWidget(QLabel(ext))
            extension_selector_area.addLayout(ext_layout)

            # Add a checkbox with the proper state
            ext_checker = QCheckBox()
            ext_checker.setCheckState(Qt.Checked if initial_values[ext] else Qt.Unchecked)
            ext_checker.stateChanged.connect(self.handle_extension_updated)
            ext_layout.addWidget(ext_checker)
            extension_controls[ext] = ext_checker

        self.resize(300, self.minimumSizeHint().height())

    def handle_extension_updated(self, state):
        extension_name = [key for key, value in self.extension_controls.items() if value is self.sender()]
        if extension_name:
            self.request_extension_updated.emit(extension_name[0], state)

    def set_check_states(self, ext_info):
        for ext, desired_state in ext_info.items():
            self.extension_controls[ext].setCheckState(Qt.Checked if desired_state else Qt.Unchecked)

    def close(self):
        self.hide()


class HomeWindow(QWidget):
    """Batch image converter home widget"""

    def __init__(self):
        super().__init__()
        self.filter_extensions = {key: True for key in EXTENSIONS}
        self.selected_path = ''  # The folder to convert
        self.path_select_time = None
        self.target_paths = {}
        self.cancel_folder_open = False

        self.ext_picker_modal = ExtensionPicker(self.filter_extensions)
        self.ext_picker_modal.request_extension_updated.connect(self.handle_extension_selection_updated)

        # Set some initial properties
        layout = QVBoxLayout()
        self.setWindowTitle('Batch image converter')
        self.setLayout(layout)

        # Add user controls for choosing a folder to convert
        path_picker_header = QHBoxLayout()
        layout.addLayout(path_picker_header)
        path_picker_header.addWidget(QLabel('Selected Folder:'))
        # ....
        path_picker_lbl = QLabel()
        path_picker_header.addWidget(path_picker_lbl)
        path_picker_header.addStretch()
        self.path_picker_lbl = path_picker_lbl
        self.clear_selected_path()
        # ....
        path_picker_controls = QHBoxLayout()
        layout.addLayout(path_picker_controls)
        path_picker_btn = QPushButton('Choose Folder')
        path_picker_btn.clicked.connect(self.handle_choose_path)
        path_picker_controls.addWidget(path_picker_btn)
        path_picker_controls.addStretch()
        self.path_picker_btn = path_picker_btn

        # Add a settings area
        settings_area = QVBoxLayout()
        settings_box = QGroupBox('Conversion Settings:')
        settings_box.setLayout(settings_area)
        layout.addWidget(settings_box)
        # ....
        settings_header = QHBoxLayout()
        settings_area.addLayout(settings_header)
        # settings_header.addWidget(QLabel('Conversion Settings:'))
        # ....
        # Add a file filter, users can specify which file types to convert
        filter_controls = QHBoxLayout()
        filter_controls.addWidget(QLabel('Selected Filetypes:'))
        settings_area.addLayout(filter_controls)
        filter_summary = QLabel()
        self.filter_summary = filter_summary
        filter_controls.addWidget(filter_summary)
        filter_controls.addStretch()
        self.update_filter_summary()  # Shows users which extensions are selected
        ext_picker_area = QHBoxLayout()
        settings_area.addLayout(ext_picker_area)
        extension_picker_btn = QPushButton('Pick Filetypes')
        extension_picker_btn.clicked.connect(self.handle_ext_picker_clicked)
        ext_picker_area.addWidget(extension_picker_btn)
        ext_picker_area.addStretch()
        self.extension_picker_btn = extension_picker_btn
        # ....
        scale_factor_controls = QHBoxLayout()
        settings_area.addLayout(scale_factor_controls)
        # ....
        scale_factor_controls.addWidget(QLabel('Scale Factor:'))
        scale_factor_summary = QLabel('')
        scale_factor_controls.addWidget(scale_factor_summary)
        scale_factor_controls.addStretch()
        self.scale_factor_summary = scale_factor_summary
        scale_factor = QSlider(Qt.Horizontal)
        scale_factor.setMinimum(1)
        scale_factor.setMaximum(100)
        scale_factor.setValue(100)
        self.handle_scale_slider_changed(scale_factor.value())
        scale_factor.valueChanged.connect(self.handle_scale_slider_changed)
        settings_area.addWidget(scale_factor)
        self.scale_factor = scale_factor

        output_settings_box = QGroupBox('Output Settings:')
        output_settings_area = QVBoxLayout()
        output_settings_area.addWidget(QLabel('TODO'))
        output_settings_box.setLayout(output_settings_area)
        output_controls = QHBoxLayout()
        output_settings_area.addLayout(output_controls)
        layout.addWidget(output_settings_box)
        output_format_field = QLineEdit()
        output_format_field.setPlaceholderText('Enter a format, ex: png, jpg')
        self.output_format_field = output_format_field

        convert_controls = QHBoxLayout()
        convert_controls.addStretch()
        layout.addLayout(convert_controls)

        convert_btn = QPushButton('Convert')
        convert_btn.clicked.connect(self.handle_convert)
        convert_controls.addWidget(convert_btn)
        self.convert_btn = convert_btn

        # Size the widget after adding stuff to the layout
        self.resize(600, self.minimumSizeHint().height())  # Resize children (if needed) below this line
        # Make sure you show() the widget!
        self.show()

    def clear_selected_path(self):
        self.path_select_time = None
        self.selected_path = ''
        self.path_picker_lbl.setText('(No Folder Selected)')
        self.target_paths = {}
        self.cancel_folder_open = False

    def show_conversion_task_stats(self):
        self.path_picker_lbl.setText(
            f'({len(self.target_paths):,}) images @ '
            f'folder "{os.path.basename(self.selected_path)}"'
        )

    def set_folder_choose_cancel_flag(self):
        # Set the cancel flag on the widget
        self.cancel_folder_open = True

    def handle_choose_path(self):
        folder_path = QFileDialog.getExistingDirectory(self)

        # Validate path
        if folder_path:
            # Don't proceed unless the path is valid
            selected_path = os.path.abspath(folder_path)
            if not os.path.exists:
                self.show_error_message('Error: Folder does not exist!')
                return
            if not os.path.isdir(folder_path):
                self.show_error_message('Error: Path is not a folder!')
                return

            # Clear current selection before proceeding with new path
            self.clear_selected_path()
            target_paths = self.target_paths
            app = QApplication.instance()
            self.cancel_folder_open = False

            box = QMessageBox()
            box.setStandardButtons(QMessageBox.Cancel)
            box.setWindowTitle('Finding files...')
            box.setText(f'(0) matches\n(0) searched...')
            cancel_btn = box.button(QMessageBox.Cancel)
            cancel_btn.clicked.connect(self.set_folder_choose_cancel_flag)
            # box.resize(600, box.minimumSizeHint().height())  # TODO: Fix this
            box.show()

            # Conversion task info is populated here
            self.path_select_time = datetime.datetime.now()
            self.selected_path = selected_path

            # Gather file info
            files_searched = 0
            for dirpath, dirnames, filenames in os.walk(selected_path):
                files_searched += 1
                if files_searched % 1000 == 0:
                    box.setText(f'({len(target_paths):,}) matches\n({files_searched:,}) searched...')
                    if self.cancel_folder_open:
                        # Abort if needed
                        self.clear_selected_path()
                        return
                    app.processEvents()

                for fname in filenames:
                    filepath = os.path.join(dirpath, fname)

                    file_name, file_ext = os.path.splitext(filepath)
                    extension_matched = None
                    for ext_name, matcher in EXT_MATCHERS.items():
                        if matcher.fullmatch(file_ext.strip('.')):
                            extension_matched = matcher
                            break

                    if extension_matched:
                        target_paths[filepath] = {}

            self.show_conversion_task_stats()

    def show_error_message(self, message):
        QMessageBox.information(
            self,
            'Error!',
            'message'
        )

    def get_extension_matcher(self, extension):
        if extension.lower() in {}:
            return

    def handle_convert(self):
        user_folder = self.path_picker_field.text()
        if not os.path.isdir(user_folder):
            self.path_picker_field.clear()
            self.show_error_message('Error: Folder does not exist!')

            return

        # user_extensions = [ext.strip() for ext in self.file_filter_field.text().split(',')]
        # actual_extensions = [self.get_extension_matcher(user_ext) for user_ext in user_extensions]

    def update_filter_summary(self):
        self.filter_summary.setText(','.join(sorted([ext for ext, state in self.filter_extensions.items() if state])))

    def handle_extension_selection_updated(self, ext_name, check_state):
        self.filter_extensions[ext_name] = check_state
        self.update_filter_summary()

    def handle_ext_picker_clicked(self):
        self.ext_picker_modal.set_check_states(self.filter_extensions)
        self.ext_picker_modal.show()

    def handle_scale_slider_changed(self, value):
        self.scale_factor_summary.setText(f'({value})')


def run_gui():
    """Function scoped main app entrypoint"""
    # Initialize the QApplication!
    app = QApplication(sys.argv)

    # This widget shows itself (the main GUI entrypoint)
    my_widget = HomeWindow()

    # Run the program/start the event loop with exec()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
