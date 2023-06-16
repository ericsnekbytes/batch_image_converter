"""Batch image converter"""


import datetime
import os.path
import random
import re
import sys
import traceback

from PIL import Image
from PySide6.QtWidgets import QLineEdit, QLabel, QSlider, QFileDialog, QErrorMessage, QCheckBox, QGroupBox, QMessageBox, \
    QTableView, QHeaderView, QStyleFactory, QDialog, QDialogButtonBox
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QObject
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
ERR_IMAGE_OPEN = 'ERR_IMAGE_OPEN'
ERR_IMAGE_SAVE = 'ERR_IMAGE_SAVE'
STATUS_OK = 0
ERR_FOLDER_INVALID = 1
ERR_FOLDER_DOES_NOT_EXIST = 1 << 1
ERR_PATH_IS_NOT_FOLDER = 1 << 2


class ImageBatcherException(Exception):

    def __init__(self):
        super().__init__()

        self.code = None


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
        return 3

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
                if col == 2:
                    return str(list(self.model_data.items())[row][1])

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
                if section == 2:
                    return "Extra Info"

    def set_new_data(self, user_data):
        # A custom function that clears the underlying data
        # (and stores new data), then refreshes the model

        # Assign new underlying data
        self.model_data = user_data

        # This tells Qt to invalidate the model, which will cause
        # connected views to refresh/re-query any displayed data
        self.beginResetModel()
        self.endResetModel()


class ConversionManager(QObject):
    """Handles conversion data/procedures"""

    file_search_progress = Signal(int, int)
    ready_for_ui_events = Signal()

    def __init__(self):
        super().__init__()

        self.source_path = ''  # The folder to search for images
        self.source_extension_filter = {key: True for key in EXTENSIONS}
        self.target_paths = {}
        self.conv_timestamp = None
        self.cancel_folder_open_flag = False

        self.output_path = ''  # The output/destination folder
        self.output_extension_filter = {key: False for key in EXTENSIONS}
        self.output_extension_filter[EXT_JPG] = True  # Default to JPG export

    def get_file_search_filters(self):
        """Return extensions to look for during file search stage"""
        return self.source_extension_filter

    def get_file_save_filters(self):
        """Return extensions to save-as when writing output files"""
        return self.output_extension_filter

    def get_source_path(self):
        return self.source_path

    def request_cancel_folder_open(self):
        self.cancel_folder_open_flag = True

    def set_source_path(self, folder_path):
        if folder_path:
            # Don't proceed unless the path is valid
            source_path = os.path.abspath(folder_path)
            if not os.path.exists:
                # self.show_error_message('Error: Folder does not exist!')
                return ERR_FOLDER_DOES_NOT_EXIST
            if not os.path.isdir(folder_path):
                # self.show_error_message('Error: Path is not a folder!')
                return ERR_PATH_IS_NOT_FOLDER

            self.clear_source_path()
            self.source_path = source_path
            self.conv_timestamp = datetime.datetime.now()
            # self.source_path_picker_lbl.setText(os.path.basename(output_path))
            return STATUS_OK
        else:
            return ERR_FOLDER_INVALID

    def start_file_search(self):
        target_paths = self.target_paths

        # Gather file info
        files_searched = 0
        delta_timestamp = datetime.datetime.now()
        self.cancel_folder_open_flag = False
        for dirpath, dirnames, filenames in os.walk(self.source_path):
            files_searched += 1

            # Check intermittently for UI updates and for cancellation requests
            if files_searched % 100 == 0 or files_searched == 1:
                current_time = datetime.datetime.now()
                if (current_time - delta_timestamp).seconds > .2:
                    delta_timestamp = current_time

                    self.file_search_progress.emit(len(self.target_paths), files_searched)
                    if self.cancel_folder_open_flag:
                        # Abort if needed
                        self.clear_source_path()  # TODO be consistent when clearing
                        return

            for fname in filenames:
                filepath = os.path.join(dirpath, fname)

                file_name, file_ext = os.path.splitext(filepath)
                extension_matched = None
                for ext_name, matcher in EXT_MATCHERS.items():
                    if matcher.fullmatch(file_ext.strip('.')):
                        extension_matched = matcher
                        break

                if extension_matched:
                    target_paths[filepath] = {'errors': []}  # Add a metadata dict for this file

        return {
            'matches': target_paths,
            'errors': [key for key, val in target_paths.items() if val['errors']],
            'canceled': self.cancel_folder_open_flag,
        }

    def clear_source_path(self):
        self.conv_timestamp = None
        self.source_path = ''
        self.target_paths = {}

    def clear_output_path(self):
        self.output_path = ''

    def get_target_paths(self):
        return self.target_paths

    def set_output_path(self, folder_path):
        if folder_path:
            # Don't proceed unless the path is valid
            output_path = os.path.abspath(folder_path)
            if not os.path.exists:
                # self.show_error_message('Error: Folder does not exist!')
                return ERR_FOLDER_DOES_NOT_EXIST
            if not os.path.isdir(folder_path):
                # self.show_error_message('Error: Path is not a folder!')
                return ERR_PATH_IS_NOT_FOLDER

            self.output_path = output_path
            # self.output_path_picker_lbl.setText(os.path.basename(output_path))
            return STATUS_OK
        else:
            return ERR_FOLDER_INVALID


class WizardPickFiles(QWidget):

    def __init__(self):
        super().__init__()


class CustomModal(QWidget):

    def __init__(self, user_title='', user_message='', user_buttons=None):
        super().__init__()

        button_objects = {}
        self.button_objects = button_objects

        layout = QVBoxLayout()
        self.setLayout(layout)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowTitle(user_title)

        message = QLabel()
        message.setText(user_message)
        layout.addWidget(message)
        self.message = message

        button_box = QDialogButtonBox()
        layout.addWidget(button_box)
        self.button_box = button_box

        if user_buttons is not None:
            self.set_buttons(user_buttons)

    def set_message(self, user_message):
        self.message.setText(user_message)

    def set_title(self, title):
        self.setWindowTitle(title)

    def set_buttons(self, std_buttons):
        button_objects = self.button_objects
        for btn in std_buttons:
            button_obj = self.button_box.addButton(btn)
            button_objects[btn] = button_obj

        return button_objects

    def button(self, std_button):
        return self.button_box.button(std_button)

    def enable_button(self, std_button):
        # TODO: cleanup/combine to set state
        btn = self.button_box.button(std_button)
        btn.setEnabled(True)

    def disable_button(self, std_button):
        btn = self.button_box.button(std_button)
        btn.setEnabled(False)


class HomeWindow(QWidget):
    """Batch image converter home widget"""

    def __init__(self):
        super().__init__()

        # Set up a conversion data/handling object
        conversion_mgr = ConversionManager()
        conversion_mgr.file_search_progress.connect(self.handle_file_search_progress)
        self.conversion_mgr = conversion_mgr

        # Set some initial widget properties
        layout = QVBoxLayout()
        self.setWindowTitle('Batch image converter')
        self.setLayout(layout)

        # Hold child modal widgets here
        self.input_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_updated)
        self.output_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.request_extension_updated.connect(self.handle_output_extensions_updated)
        self.file_search_progress_modal = None

        # Store the MVC model for the discovered files the users wants to convert
        target_paths_model = TargetPathsModel(conversion_mgr.get_target_paths())
        self.target_paths_model = target_paths_model

        # Add user controls for choosing a folder to convert
        src_folder_header = QHBoxLayout()
        layout.addLayout(src_folder_header)
        src_folder_header.addWidget(QLabel('Selected Folder:'))
        src_folder_lbl = QLabel()
        src_folder_header.addWidget(src_folder_lbl)
        self.src_folder_lbl = src_folder_lbl
        self.clear_selected_path()
        # ....
        src_folder_controls = QHBoxLayout()
        layout.addLayout(src_folder_controls)
        # ....
        pick_src_folder_btn = QPushButton('Choose Folder')
        pick_src_folder_btn.clicked.connect(self.handle_choose_source_path)
        src_folder_controls.addWidget(pick_src_folder_btn)
        src_folder_controls.addStretch()
        self.pick_src_folder_btn = pick_src_folder_btn

        # Set up the files table
        targets_view = QTableView()
        targets_view.setModel(target_paths_model)
        targets_view.setWordWrap(False)
        # Set header behaviors
        # ....
        # Make the last column fit the parent layout width
        horiz_header = targets_view.horizontalHeader()
        horiz_header.setStretchLastSection(True)
        # Make the rows fixed-height
        vert_header = targets_view.verticalHeader()
        vert_header.setSectionResizeMode(QHeaderView.Fixed)
        # ....
        layout.addWidget(targets_view)
        self.targets_table = targets_view

        # Add a settings area
        conversion_settings_area = QVBoxLayout()
        conv_settings_box = QGroupBox('Conversion Settings:')
        conv_settings_box.setLayout(conversion_settings_area)
        layout.addWidget(conv_settings_box)
        # ....
        # Set up a source-filetypes summary and controls
        src_formats_header = QHBoxLayout()
        conversion_settings_area.addLayout(src_formats_header)
        # Set up the source-filetypes extension picker header
        src_extensions_header = QHBoxLayout()
        src_extensions_header.addWidget(QLabel('Selected Filetypes:'))
        conversion_settings_area.addLayout(src_extensions_header)
        src_extensions_summary = QLabel()
        src_extensions_header.addWidget(src_extensions_summary)
        src_extensions_header.addStretch()
        self.src_extensions_summary = src_extensions_summary
        self.update_input_ext_filter_summary()  # Shows a list of selected extensions
        # Set up the extensions picker controls
        src_ext_picker_controls = QHBoxLayout()
        conversion_settings_area.addLayout(src_ext_picker_controls)
        src_ext_picker_btn = QPushButton('Pick Filetypes')
        src_ext_picker_btn.clicked.connect(self.handle_input_ext_picker_clicked)
        src_ext_picker_controls.addWidget(src_ext_picker_btn)
        src_ext_picker_controls.addStretch()
        self.extension_picker_btn = src_ext_picker_btn
        # ....
        # Set up scale factor controls
        scale_factor_header = QHBoxLayout()
        conversion_settings_area.addLayout(scale_factor_header)
        scale_factor_header.addWidget(QLabel('Scale Factor:'))
        scale_factor_summary = QLabel('')  # Shows the current scale factor
        scale_factor_header.addWidget(scale_factor_summary)
        scale_factor_header.addStretch()
        self.scale_factor_summary = scale_factor_summary
        # Configure/add the scale factor slider
        scale_factor = QSlider(Qt.Horizontal)
        scale_factor.setMinimum(1)
        scale_factor.setMaximum(100)
        scale_factor.setValue(100)
        self.handle_scale_slider_changed(scale_factor.value())
        scale_factor.valueChanged.connect(self.handle_scale_slider_changed)
        conversion_settings_area.addWidget(scale_factor)
        self.scale_factor = scale_factor

        # Set up output/save-as controls
        output_settings_box = QGroupBox('File Save Settings:')
        layout.addWidget(output_settings_box)
        output_settings_area = QVBoxLayout()
        output_settings_box.setLayout(output_settings_area)
        # ....
        # Set up save-as extensions picker header
        output_ext_picker_header = QHBoxLayout()
        output_settings_area.addLayout(output_ext_picker_header)
        output_ext_picker_header.addWidget(QLabel('Output Filetype(s):'))
        output_filter_summary = QLabel()  # Shows a list of selected save-as/output extensions
        output_ext_picker_header.addWidget(output_filter_summary)
        output_ext_picker_header.addStretch()
        self.output_filter_summary = output_filter_summary
        self.update_output_ext_summary()
        # Set up the save-as extension picker controls
        output_ext_picker_area = QHBoxLayout()
        output_settings_area.addLayout(output_ext_picker_area)
        output_ext_picker_btn = QPushButton('Pick Filetypes')
        output_ext_picker_btn.clicked.connect(self.handle_output_ext_picker_clicked)
        output_ext_picker_area.addWidget(output_ext_picker_btn)
        output_ext_picker_area.addStretch()
        self.output_ext_picker_btn = output_ext_picker_btn

        # Add save-as/output folder picker controls
        output_folder_picker_header = QHBoxLayout()
        layout.addLayout(output_folder_picker_header)
        output_folder_picker_header.addWidget(QLabel('Destination Folder:'))
        # ....
        output_folder_picker_lbl = QLabel()  # Shows the output folder
        output_folder_picker_header.addWidget(output_folder_picker_lbl)
        output_folder_picker_header.addStretch()
        self.output_path_picker_lbl = output_folder_picker_lbl
        self.clear_output_path()
        # ....
        output_path_picker_controls = QHBoxLayout()
        layout.addLayout(output_path_picker_controls)
        output_path_picker_btn = QPushButton('Choose Folder')
        output_path_picker_btn.clicked.connect(self.handle_choose_output_path)
        output_path_picker_controls.addWidget(output_path_picker_btn)
        output_path_picker_controls.addStretch()
        self.output_path_picker_btn = output_path_picker_btn

        # Add conversion launch controls
        convert_controls = QHBoxLayout()
        convert_controls.addStretch()
        layout.addLayout(convert_controls)
        convert_btn = QPushButton('Convert')
        convert_btn.clicked.connect(self.handle_convert)
        convert_controls.addWidget(convert_btn)
        self.convert_btn = convert_btn

        # Size the widget after adding stuff to the layout
        self.resize(800, 600)  # Resize children (if needed) below this line
        targets_view.setColumnWidth(0, targets_view.width() / 2)
        targets_view.setColumnWidth(1, targets_view.width() / 2)
        # Auto show() the widget!
        self.show()

    def clear_selected_path(self):
        # Clear data
        manager = self.conversion_mgr
        manager.clear_source_path()

        # Reset the UI
        self.src_folder_lbl.setText('(No Folder Selected)')
        self.target_paths_model.set_new_data(manager.get_target_paths())

    def clear_output_path(self):
        # Clear data
        manager = self.conversion_mgr
        manager.clear_output_path()

        # Reset the UI
        self.output_path_picker_lbl.setText('(No Folder Selected)')

    def show_conversion_task_stats(self):
        manager = self.conversion_mgr

        self.src_folder_lbl.setText(
            f'({len(manager.get_target_paths()):,}) images in '
            f'folder "{os.path.basename(manager.get_source_path())}"'
        )

    def set_folder_choose_cancel_flag(self):
        # Set the cancel flag on the widget
        self.file_search_progress_modal.disable_button(QDialogButtonBox.Cancel)
        self.conversion_mgr.request_cancel_folder_open()

    # TODO move this down
    def handle_choose_output_path(self):
        manager = self.conversion_mgr

        folder_path = QFileDialog.getExistingDirectory(self)
        if folder_path:
            folder_path = os.path.abspath(folder_path)
        status = manager.set_output_path(folder_path)

        if status == STATUS_OK:
            self.output_path_picker_lbl.setText(os.path.basename(folder_path))
        else:
            output_path = os.path.abspath(folder_path)
            if status == ERR_FOLDER_DOES_NOT_EXIST:
                self.show_error_message('Error: Folder does not exist!')
                return
            if status == ERR_PATH_IS_NOT_FOLDER:
                self.show_error_message('Error: Path is not a folder!')
                return
            if status == ERR_FOLDER_INVALID:
                self.show_error_message('Error: Path is invalid!')
                return

    def handle_file_search_progress(self, match_count, search_count):
        """Handle intermittent file search progress updates, refresh the UI"""
        popup = self.file_search_progress_modal
        popup.set_message(f'({match_count:,}) matches\n({search_count:,}) searched...')
        QApplication.instance().processEvents()

    def handle_progress_popup_ok(self):
        self.file_search_progress_modal.close()

    def handle_choose_source_path(self):
        manager = self.conversion_mgr

        folder_path = QFileDialog.getExistingDirectory(self)
        if folder_path:
            folder_path = os.path.abspath(folder_path)
        status = manager.set_source_path(folder_path)

        if status == STATUS_OK:
            self.src_folder_lbl.setText(os.path.basename(folder_path))
        else:
            if status == ERR_FOLDER_DOES_NOT_EXIST:
                self.show_error_message('Error: Folder does not exist!')
                return
            if status == ERR_PATH_IS_NOT_FOLDER:
                self.show_error_message('Error: Path is not a folder!')
                return
            if status == ERR_FOLDER_INVALID:
                self.show_error_message('Error: Path is invalid!')
                return

        # Obtain the app, to perform manual UI updates
        app = QApplication.instance()

        # Show a progress popup
        box = CustomModal('Finding files...', f'(0) matches\n(0) searched...')
        box.set_buttons([QDialogButtonBox.Cancel, QDialogButtonBox.Ok])
        # ....
        cancel_btn = box.button(QDialogButtonBox.Cancel)
        cancel_btn.clicked.connect(self.set_folder_choose_cancel_flag)
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(self.handle_progress_popup_ok)
        box.disable_button(QDialogButtonBox.Ok)
        box.resize(400, box.minimumSizeHint().height())  # TODO: Fix this
        self.file_search_progress_modal = box
        box.show()

        app.processEvents()

        # Start searching the disk for images at the specified location
        result = manager.start_file_search()
        # print(f'[batch_img_converter] {len(result["matches"])} matched, {len(result["errors"])} files with errors')  # TODO add total filecount
        if result['canceled']:
            box.set_message('Image search was canceled')
        else:
            box.set_message(
                f'Finished with {len(result["matches"])} images found, {len(result["errors"])} files with errors'
            )  # TODO add total filecount
            box.disable_button(QDialogButtonBox.Cancel)
            box.enable_button(QDialogButtonBox.Ok)

        # TODO restructure/simplify this
        self.target_paths_model.set_new_data(manager.get_target_paths())
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
        manager = self.conversion_mgr
        user_folder = manager.get_source_path()

        # For each image file, try to open the image, process, and save it
        for image_path, metadata in manager.get_target_paths().items():
            try:
                user_image = Image.open(image_path)
            except OSError as err:
                metadata['errors'].append({ERR_IMAGE_OPEN: True})  # TODO encapsulate this >>>>>
                traceback.print_exc()
                print(f'[py_img_batcher] Error opening {image_path}, skipping...')

                continue

            # For each desired save file, write a file
            for output_ext in [ext for ext, val in manager.get_file_save_filters().items() if val]:
                try:
                    output_path = self.get_safe_output_path(image_path, output_ext)
                    print('OUTPUT')
                    print(output_path)
                    user_image.save(output_path)
                except OSError:
                    metadata['errors'].append({ERR_IMAGE_SAVE: output_ext})
                    traceback.print_exc()
                    print(f'[py_img_batcher] Error saving {image_path}, skipping...')

                    continue
                # except ImageBatcherException as err:  # TODO handle this properly
                except Exception as err:
                    metadata['errors'].append({'unknown error': output_ext})
                    traceback.print_exc()
                    print(f'[py_img_batcher] Unknown error for {image_path} / {output_ext}, skipping...')

                    continue

        print(f'Finished with {sum([len(val["errors"]) for item, val in self.target_paths.items()])} errors')

    def get_safe_output_path(self, src_path, extension):
        base_name = os.path.basename(os.path.splitext(src_path)[0])

        name_attempt_counter = -1
        current_name = os.path.join(self.output_path, f'{base_name}.{extension}')

        while os.path.exists(current_name):
            print(f'File {current_name} already exists, attempting new name...')
            name_attempt_counter += 1
            current_name = os.path.join(self.output_path, f'{base_name}.{name_attempt_counter:0>4}.{extension}')

            if name_attempt_counter == 10000:
                raise Exception('Error obtaining non-duplicate name')

        return current_name

    def update_input_ext_filter_summary(self):
        self.src_extensions_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_search_filters().items() if state])))

    def update_output_ext_summary(self):
        self.output_filter_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_save_filters().items() if state])))

    def handle_input_extensions_updated(self, ext_name, check_state):
        self.conversion_mgr.get_file_search_filters()[ext_name] = check_state
        self.update_input_ext_filter_summary()

    def handle_output_extensions_updated(self, ext_name, check_state):
        self.conversion_mgr.get_file_save_filters()[ext_name] = check_state
        self.update_output_ext_summary()

    def handle_input_ext_picker_clicked(self):
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.show()

    # TODO clean up manager access on these
    def handle_output_ext_picker_clicked(self):
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())
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
