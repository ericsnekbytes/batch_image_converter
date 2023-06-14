"""Batch image converter"""


import datetime
import os.path
import random
import re
import sys

from PySide6.QtWidgets import QLineEdit, QLabel, QSlider, QFileDialog, QErrorMessage, QCheckBox, QGroupBox, QMessageBox, \
    QTableView, QHeaderView, QStyleFactory
from PySide6.QtCore import Qt, Signal, QAbstractTableModel
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton,
                               QHBoxLayout)


EXT_BMP = 'bmp'
EXT_GIF = 'gif'
EXT_JPG = 'jpg'
EXT_PNG = 'png'
EXT_TIFF = 'tiff'
EXT_WEBP = 'webp'
EXT_MATCHERS = {
    EXT_BMP: re.compile(r'bmp', flags=re.IGNORECASE),
    EXT_GIF: re.compile(r'gif', flags=re.IGNORECASE),
    EXT_JPG: re.compile(r'(jpg|jpeg)', flags=re.IGNORECASE),
    EXT_PNG: re.compile(r'png', flags=re.IGNORECASE),
    EXT_TIFF: re.compile(r'(tif|tiff)', flags=re.IGNORECASE),
    EXT_WEBP: re.compile(r'webp', flags=re.IGNORECASE),
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


class TargetPathsModel(QAbstractTableModel):
    """Tells Qt how our data corresponds to different rows/columns/cells.

    From the Qt documentation (for display-only tables):
      When subclassing QAbstractTableModel, you must implement rowCount(),
      columnCount(), and data(). Default implementations of the index()
      and parent() functions are provided by QAbstractTableModel.
      Well behaved models will also implement headerData().
    """

    def __init__(self, user_data):
        super().__init__()

        # Store the data we're representing
        self.model_data = user_data

    def rowCount(self, parent):
        return len(self.model_data)

    def columnCount(self, parent):
        return 2

    def data(self, index, role):
        # So, data() does a lot of different things. This
        # function takes in a QModelIndex (which tells you
        # which cell/what data Qt needs info about), then
        # you respond by returning whatever KIND of information
        # Qt is looking for, determined by the role. Here are
        # the builtin roles Qt requests by default:
        #
        #   0) Qt::DisplayRole, 1) Qt::DecorationRole,
        #   2) Qt::EditRole 3) Qt::ToolTipRole, 4) Qt::StatusTipRole
        #   5) Qt::WhatsThisRole, 6) Qt::SizeHintRole
        #
        # Most of these you can probably ignore. Often, you
        # only need to provide data for the DisplayRole, which
        # will often just be some text representing your data...
        # but as you can see, for each cell, Qt also might want
        # to know how to size the data in that cell, or what
        # a good tooltip might be for the cell, etcetera. Make
        # SURE you specifically test for the roles that you care
        # about, and return None if the role isn't relevant to you.
        # Providing bad data/a nonsense return value for a role
        # you don't care about can make weird things happen.
        row = index.row()
        col = index.column()

        # Note that dicts are sorted in Py3.7+, so here
        # we just index an ordered list of our dict items
        if index.isValid():
            if role == Qt.DisplayRole:
                if col == 0:
                    return os.path.basename(list(self.model_data.items())[row][0])
                if col == 1:
                    return list(self.model_data.items())[row][0]
                return list(self.model_data.items())[row][col]

        return None

    def headerData(self, section, orientation, role):
        # This is where you can name your columns, or show
        # some other data for the column and row headers
        if role == Qt.DisplayRole:
            # Just return a row number for the vertical header
            if orientation == Qt.Vertical:
                return str(section)

            # Return some column names for the horizontal header
            if orientation == Qt.Horizontal:
                if section == 0:
                    return "Filename"
                if section == 1:
                    return "Path"

    def set_new_data(self, user_data):
        # A custom function that clears the underlying data
        # (and stores new data), then refreshes the model

        # Assign new underlying data
        self.model_data = user_data

        # This tells Qt to invalidate the model, which will cause
        # connected views to refresh/re-query any displayed data
        self.beginResetModel()
        self.endResetModel()


class HomeWindow(QWidget):
    """Batch image converter home widget"""

    def __init__(self):
        super().__init__()
        self.input_extension_filter = {key: True for key in EXTENSIONS}
        self.selected_path = ''  # The folder to convert
        self.path_select_time = None
        self.target_paths = {}
        self.cancel_folder_open = False
        self.output_extension_filter = {key: False for key in EXTENSIONS}
        self.output_extension_filter[EXT_JPG] = True  # Default to JPG export

        self.input_ext_picker_modal = ExtensionPicker(self.input_extension_filter)
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_updated)

        self.output_ext_picker_modal = ExtensionPicker(self.output_extension_filter)
        self.output_ext_picker_modal.request_extension_updated.connect(self.handle_output_extensions_updated)

        target_paths_model = TargetPathsModel(self.target_paths)
        self.target_paths_model = target_paths_model

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

        targets_table = QTableView()
        targets_table.setModel(target_paths_model)
        targets_table.setWordWrap(False)
        # Set header behaviors
        # ....................
        # Make the last column fit the parent layout width
        horiz_header = targets_table.horizontalHeader()
        horiz_header.setStretchLastSection(True)
        vert_header = targets_table.verticalHeader()
        vert_header.setSectionResizeMode(QHeaderView.Fixed)
        # ..........................
        layout.addWidget(targets_table)
        self.targets_table = targets_table

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
        input_filter_summary = QLabel()
        self.input_filter_summary = input_filter_summary
        filter_controls.addWidget(input_filter_summary)
        filter_controls.addStretch()
        self.update_input_ext_filter_summary()  # Shows users which extensions are selected
        input_ext_picker_area = QHBoxLayout()
        settings_area.addLayout(input_ext_picker_area)
        input_extension_picker_btn = QPushButton('Pick Filetypes')
        input_extension_picker_btn.clicked.connect(self.handle_input_ext_picker_clicked)
        input_ext_picker_area.addWidget(input_extension_picker_btn)
        input_ext_picker_area.addStretch()
        self.extension_picker_btn = input_extension_picker_btn
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

        output_settings_box = QGroupBox('File Save Settings:')
        output_settings_area = QVBoxLayout()
        output_ext_picker_header = QHBoxLayout()
        output_settings_area.addLayout(output_ext_picker_header)
        output_ext_picker_header.addWidget(QLabel('Output Filetype(s):'))
        output_filter_summary = QLabel()
        output_ext_picker_header.addWidget(output_filter_summary)
        output_ext_picker_header.addStretch()
        self.output_filter_summary = output_filter_summary
        self.update_output_ext_filter_summary()
        output_ext_picker_area = QHBoxLayout()
        output_ext_picker_btn = QPushButton('Pick Filetypes')
        output_ext_picker_btn.clicked.connect(self.handle_output_ext_picker_clicked)
        output_settings_area.addLayout(output_ext_picker_area)
        output_ext_picker_area.addWidget(output_ext_picker_btn)
        output_ext_picker_area.addStretch()
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
        self.resize(800, 600)  # Resize children (if needed) below this line
        targets_table.setColumnWidth(0, targets_table.width() / 2)
        targets_table.setColumnWidth(1, targets_table.width() / 2)
        # Make sure you show() the widget!
        self.show()

    def clear_selected_path(self):
        self.path_select_time = None
        self.selected_path = ''
        self.path_picker_lbl.setText('(No Folder Selected)')
        self.target_paths = {}
        self.cancel_folder_open = False
        self.target_paths_model.set_new_data(self.target_paths)

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

            self.target_paths_model.set_new_data(target_paths)
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

    def update_input_ext_filter_summary(self):
        self.input_filter_summary.setText(','.join(sorted([ext for ext, state in self.input_extension_filter.items() if state])))

    def update_output_ext_filter_summary(self):
        self.output_filter_summary.setText(','.join(sorted([ext for ext, state in self.output_extension_filter.items() if state])))

    def handle_input_extensions_updated(self, ext_name, check_state):
        self.input_extension_filter[ext_name] = check_state
        self.update_input_ext_filter_summary()

    def handle_output_extensions_updated(self, ext_name, check_state):
        self.output_extension_filter[ext_name] = check_state
        self.update_output_ext_filter_summary()

    def handle_input_ext_picker_clicked(self):
        self.input_ext_picker_modal.set_check_states(self.input_extension_filter)
        self.input_ext_picker_modal.show()

    def handle_output_ext_picker_clicked(self):
        self.output_ext_picker_modal.set_check_states(self.output_extension_filter)
        self.output_ext_picker_modal.show()

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
