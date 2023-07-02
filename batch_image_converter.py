"""Batch image converter"""


import datetime
import json
import os.path
import random
import re
import sys
import traceback
# from multiprocessing import Process, Queue

from PIL import Image
from PySide6.QtWidgets import QLineEdit, QLabel, QSlider, QFileDialog, QErrorMessage, QCheckBox, QGroupBox, QMessageBox, \
    QTableView, QHeaderView, QStyleFactory, QDialog, QDialogButtonBox, QFrame, QProgressBar, QSplitter, QSizePolicy
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QObject
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton,
                               QHBoxLayout)

# TODO package refactor
from constants import (EXT_BMP, EXT_GIF, EXT_JPG, EXT_PNG, EXT_TIFF, EXT_WEBP, EXT_MATCHERS,
                       EXTENSIONS, ERR_IMAGE_OPEN, ERR_IMAGE_SAVE, STATUS_OK, ERR_FOLDER_INVALID,
                       ERR_FOLDER_DOES_NOT_EXIST, ERR_PATH_IS_NOT_FOLDER, ERRORS, OUTPUTS, TARGETS, CANCELED)


# Move this to models module
_TARGET_PATHS_MODEL = None
def get_target_paths_model():
    global _TARGET_PATHS_MODEL
    if _TARGET_PATHS_MODEL is None:
        _TARGET_PATHS_MODEL = TargetPathsModel()
    return _TARGET_PATHS_MODEL
_CONVERSION_MANAGER = None
def get_conversion_manager():
    global _CONVERSION_MANAGER
    if _CONVERSION_MANAGER is None:
        _CONVERSION_MANAGER = ConversionManager()
    return _CONVERSION_MANAGER


def new_file_metadata():
    return {ERRORS: [], OUTPUTS: []}


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

    def __init__(self, user_data=None):
        super().__init__()

        # Store the data we're representing
        if user_data is not None:
            self.model_data = user_data
        else:
            self.model_data = {}

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
    file_save_progress = Signal(str, int, int)
    ready_for_ui_events = Signal()
    source_path_updated = Signal(str)
    output_path_updated = Signal(str)
    source_extension_filter_updated = Signal()
    output_extension_filter_updated = Signal()
    modifier_scale_updated = Signal(int)

    def __init__(self):
        super().__init__()

        self.source_path = ''  # The folder to search for images
        self.source_extension_filter = {key: True for key in EXTENSIONS}
        self.target_paths = {}
        self.conv_timestamp = None
        self.cancel_folder_open_flag = False
        self.cancel_save_flag = False
        self.modifier_scale = 100

        self.output_path = ''  # The output/destination folder
        self.output_extension_filter = {key: False for key in EXTENSIONS}
        self.output_extension_filter[EXT_JPG] = True  # Default to JPG export

    def get_file_search_filters(self):
        """Return extensions to look for during file search stage"""
        return self.source_extension_filter

    def get_file_save_filters(self):
        """Return extensions to save-as when writing output files"""
        return self.output_extension_filter

    def set_scale_modifier(self, value):
        self.modifier_scale = value
        self.modifier_scale_updated.emit(value)

    def get_source_path(self):
        return self.source_path

    def request_cancel_save(self):
        self.cancel_save_flag = True

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
            self.source_path_updated.emit(source_path)
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
                        return {
                            TARGETS: target_paths,
                            ERRORS: [],
                            CANCELED: True,
                        }

            for fname in filenames:
                filepath = os.path.join(dirpath, fname)

                file_name, file_ext = os.path.splitext(filepath)
                extension_matched = None
                for ext_name, matcher in EXT_MATCHERS.items():
                    if matcher.fullmatch(file_ext.strip('.')):
                        extension_matched = matcher
                        break

                if extension_matched:  # TODO dict schema, refactor/move
                    target_paths[filepath] = new_file_metadata()  # Add a metadata dict for this file

        return {
            TARGETS: target_paths,
            ERRORS: [key for key, val in target_paths.items() if val[ERRORS]],
            CANCELED: self.cancel_folder_open_flag,
        }

    def clear_source_path(self):
        self.conv_timestamp = None
        self.source_path = ''
        self.target_paths = {}

    def get_target_paths(self):
        return self.target_paths

    def clear_output_path(self):
        self.output_path = ''

    def get_output_path(self):
        return self.output_path

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
            self.output_path_updated.emit(output_path)
            # self.output_path_picker_lbl.setText(os.path.basename(output_path))
            return STATUS_OK
        else:
            return ERR_FOLDER_INVALID

    def set_file_save_filter(self, ext_name, check_state):
        self.output_extension_filter[ext_name] = check_state
        self.output_extension_filter_updated.emit()

    def set_file_search_filter(self, ext_name, check_state):
        self.source_extension_filter[ext_name] = check_state
        self.source_extension_filter_updated.emit()

    def write_conversion_log(self):
        task_record_path = self.get_safe_output_path(os.path.join(self.output_path, 'image_conversion_log'), 'json')
        with open(task_record_path, 'w', encoding='utf8') as fhandle:
            json.dump(self.target_paths, fhandle, indent=4)

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

    def start_conversion(self):
        # For each image file, try to open the image, process, and save it
        self.cancel_save_flag = False
        source_files_handled = 0
        image_path = ''
        for image_path, metadata in self.target_paths.items():

            self.file_save_progress.emit(image_path, source_files_handled, len(self.target_paths))
            if self.cancel_save_flag:
                self.write_conversion_log()

                # Abort if needed
                return {
                    TARGETS: self.target_paths,
                    ERRORS: [],
                    CANCELED: True,
                }

            try:
                user_image = Image.open(image_path)
            except OSError as err:
                metadata[ERRORS].append({ERR_IMAGE_OPEN: True})  # TODO encapsulate this >>>>>
                traceback.print_exc()
                print(f'[py_img_batcher] Error opening {image_path}, skipping...')

                source_files_handled += 1  # TODO refactor
                continue

            # For each desired save file, write a file
            images_written = False
            for output_ext in [ext for ext, val in self.output_extension_filter.items() if val]:
                try:
                    output_path = self.get_safe_output_path(image_path, output_ext)
                    print(f'[py_img_batcher] Writing {output_path}')
                    if self.modifier_scale != 100:
                        new_size = (int(user_image.size[0] * self.modifier_scale / 100),
                                    int(user_image.size[1] * self.modifier_scale / 100))
                        print(f'[py_img_batcher] Resizing to {new_size}')
                        user_image = user_image.resize(new_size)
                    user_image.save(output_path)
                    metadata[OUTPUTS].append({output_path: True})  # TODO update UI
                    images_written = True
                except OSError:
                    metadata[ERRORS].append({ERR_IMAGE_SAVE: output_ext})
                    traceback.print_exc()
                    print(f'[py_img_batcher] Error saving {image_path}, skipping...')

                    continue
                # except ImageBatcherException as err:  # TODO handle this properly
                except Exception as err:
                    metadata[ERRORS].append({'unknown error': output_ext})
                    traceback.print_exc()
                    print(f'[py_img_batcher] Unknown error for {image_path} / {output_ext}, skipping...')

                    continue
            if images_written:
                source_files_handled += 1

        self.write_conversion_log()

        # TODO handle degenerate cases/0 files, no dest folder etc.
        self.file_save_progress.emit(image_path, source_files_handled, len(self.target_paths))  # TODO refactor
        return {
            TARGETS: self.target_paths,
            ERRORS: [key for key, val in self.target_paths.items() if val[ERRORS]],
            CANCELED: self.cancel_save_flag,
        }


class WizardPickFiles(QWidget):

    request_next_step = Signal()

    def __init__(self):
        super().__init__()

        # TODO refactor
        conversion_mgr = get_conversion_manager()
        conversion_mgr.source_extension_filter_updated.connect(self.update_input_ext_filter_summary)
        conversion_mgr.file_search_progress.connect(self.handle_file_search_progress)
        self.conversion_mgr = conversion_mgr

        self.error_modal = None
        self.file_search_progress_modal = None
        self.input_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_update_request)

        self.setWindowTitle('Batch Image Converter (Step 1/3)')
        layout = QVBoxLayout()
        self.setLayout(layout)

        step_nav_box = QGroupBox()
        step_navigation_area = QHBoxLayout()
        step_nav_box.setLayout(step_navigation_area)
        layout.addWidget(step_nav_box)

        # step_nav_divider = QFrame()
        # step_nav_divider.setFrameShadow(QFrame.Raised)
        # step_nav_divider.setFrameShape(QFrame.HLine)
        # step_nav_divider.setMidLineWidth(.5)
        # layout.addWidget(step_nav_divider)

        next_btn = QPushButton('Next')
        next_btn.clicked.connect(self.handle_next_clicked)
        self.next_btn = next_btn

        step_navigation_area.addSpacing(next_btn.sizeHint().width())
        step_navigation_area.addStretch()
        step_navigation_area.addWidget(QLabel('Step 1: Choose Folder'))
        step_navigation_area.addStretch()

        step_navigation_area.addWidget(next_btn)

        task_area = QVBoxLayout()
        layout.addLayout(task_area)
        self.task_area = task_area

        settings_container = QSplitter()
        task_area.addWidget(settings_container)

        # Add user controls for choosing a folder to convert
        src_folder_box = QGroupBox('Search Folder:')
        src_folder_area = QVBoxLayout()
        src_folder_box.setLayout(src_folder_area)
        settings_container.addWidget(src_folder_box)
        src_folder_header = QHBoxLayout()
        src_folder_area.addLayout(src_folder_header)
        # src_folder_header.addWidget(QLabel('Select a folder with some images'))
        src_folder_lbl = QLabel()
        src_folder_lbl.setMinimumWidth(1)
        src_folder_header.addStretch()
        self.src_folder_lbl = src_folder_lbl
        self.clear_source_path_summary()
        # self.clear_selected_path()  # TODO Fix/refactor
        # ....
        src_folder_controls = QHBoxLayout()
        src_folder_area.addLayout(src_folder_controls)
        # ....
        pick_src_folder_btn = QPushButton('Pick Folder')
        pick_src_folder_btn.clicked.connect(self.handle_choose_source_path)
        src_folder_controls.addWidget(pick_src_folder_btn)
        src_folder_controls.addWidget(src_folder_lbl)
        src_folder_controls.addStretch()
        self.pick_src_folder_btn = pick_src_folder_btn

        # Add a settings area
        settings_area = QVBoxLayout()
        settings_box = QGroupBox('File Search Settings:')
        settings_box.setLayout(settings_area)
        settings_container.addWidget(settings_box)
        # ....
        # Set up a source-filetypes summary and controls
        # src_formats_header = QHBoxLayout()
        # settings_area.addLayout(src_formats_header)
        # Set up the source-filetypes extension picker header
        # src_extensions_header = QHBoxLayout()  # TODO refactor and remove these
        # src_extensions_header.addWidget(QLabel('Selected Filetypes:'))
        # settings_area.addLayout(src_extensions_header)
        src_extensions_summary = QLabel()
        self.src_extensions_summary = src_extensions_summary
        self.update_input_ext_filter_summary()  # Shows a list of selected extensions
        # Set up the extensions picker controls
        src_ext_picker_controls = QHBoxLayout()
        settings_area.addLayout(src_ext_picker_controls)
        src_ext_picker_btn = QPushButton('Pick Filetypes')
        src_ext_picker_btn.clicked.connect(self.handle_input_ext_picker_clicked)
        src_ext_picker_controls.addWidget(src_ext_picker_btn)
        src_ext_picker_controls.addWidget(src_extensions_summary)
        src_ext_picker_controls.addStretch()
        self.extension_picker_btn = src_ext_picker_btn

        # TODO refactor
        self.target_paths_model = get_target_paths_model()

        # Set up the files table
        targets_view = QTableView()
        targets_view.setModel(get_target_paths_model())
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
        task_area.addWidget(targets_view)
        self.targets_view = targets_view

        # Size the widget after adding stuff to the layout
        self.resize(800, 600)  # Resize children (if needed) below this line
        targets_view.setColumnWidth(0, targets_view.width() / 2)
        targets_view.setColumnWidth(1, targets_view.width() / 2)
        # Auto show() the widget!
        self.show()

    def clear_source_path_summary(self):
        self.src_folder_lbl.setText('(Empty) Select a folder with some images')

    def handle_source_path_updated(self, path):
        self.src_folder_lbl.setText(path)

    def handle_next_clicked(self):
        self.hide()
        self.request_next_step.emit()

    def update_input_ext_filter_summary(self):
        self.src_extensions_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_search_filters().items() if state])))

    def handle_input_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_search_filter(ext_name, check_state)

    def handle_input_extensions_updated(self):
        self.update_input_ext_filter_summary()
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())

    def handle_input_ext_picker_clicked(self):
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.show()

    def show_error_message(self, message):
        # Show a message popup (has an okay button only)
        box = CustomModal('Error!', message, [QDialogButtonBox.Ok])

        # Ok button should close the modal
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(box.close)

        # Size and hold a reference to the window
        box.resize(300, box.minimumSizeHint().height())
        self.error_modal = box
        box.show()

    def show_conversion_task_stats(self):
        manager = self.conversion_mgr
        source_path = manager.get_source_path()

        self.src_folder_lbl.setText(
            f'({len(manager.get_target_paths()):,} images) in '
            f'"{os.path.basename(source_path)}" ({source_path})'
        )

    def set_folder_choose_cancel_flag(self):
        # Set the cancel flag on the widget
        self.file_search_progress_modal.disable_button(QDialogButtonBox.Cancel)
        self.conversion_mgr.request_cancel_folder_open()

    def handle_search_progress_popup_ok(self):
        self.file_search_progress_modal.hide()

    def handle_file_search_progress(self, match_count, search_count):
        """Handle intermittent file search progress updates, refresh the UI"""
        if self.isVisible():
            popup = self.file_search_progress_modal
            popup.set_message(f'({match_count:,}) matches\n({search_count:,}) searched...')
            QApplication.instance().processEvents()

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
        ok_btn.clicked.connect(self.handle_search_progress_popup_ok)
        box.disable_button(QDialogButtonBox.Ok)
        box.resize(400, box.minimumSizeHint().height())  # TODO: Fix this
        self.file_search_progress_modal = box
        box.show()
        # TODO handle popup close

        app.processEvents()

        # Start searching the disk for images at the specified location
        result = manager.start_file_search()
        if result[CANCELED]:
            box.set_message('Image search was canceled')
        else:
            box.set_message(
                f'Finished with {len(result[TARGETS])} images found, {len(result[ERRORS])} files with errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        # TODO restructure/simplify this
        self.target_paths_model.set_new_data(manager.get_target_paths())
        self.show_conversion_task_stats()


class WizardConversionSettings(QWidget):

    request_last_step = Signal()
    request_next_step = Signal()

    def __init__(self):
        super().__init__()

        conversion_mgr = get_conversion_manager()
        conversion_mgr.modifier_scale_updated.connect(self.handle_scale_updated)
        self.conversion_mgr = conversion_mgr

        self.setWindowTitle('Batch Image Converter (Step 3/3)')
        layout = QVBoxLayout()
        self.setLayout(layout)

        step_nav_box = QGroupBox()
        step_navigation_area = QHBoxLayout()
        step_nav_box.setLayout(step_navigation_area)
        layout.addWidget(step_nav_box)

        back_btn = QPushButton('Back')
        back_btn.clicked.connect(self.handle_back_clicked)
        step_navigation_area.addWidget(back_btn)
        self.back_btn = back_btn

        step_navigation_area.addStretch()
        step_navigation_area.addWidget(QLabel('Step 3: (Optional) Image Modifiers'))
        step_navigation_area.addStretch()

        next_btn = QPushButton('Next')
        next_btn.clicked.connect(self.handle_next_clicked)
        step_navigation_area.addWidget(next_btn)
        self.next_btn = next_btn

        task_area = QVBoxLayout()
        layout.addLayout(task_area)
        self.task_area = task_area

        # Set up scale factor controls
        percent_scale_box = QGroupBox('Percent Scaling')
        percent_scale_area = QVBoxLayout()
        percent_scale_box.setLayout(percent_scale_area)
        task_area.addWidget(percent_scale_box)
        scale_factor_header = QHBoxLayout()
        percent_scale_area.addLayout(scale_factor_header)
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
        scale_factor.valueChanged.connect(self.handle_scale_modifer_update_request)
        percent_scale_area.addWidget(scale_factor)
        self.scale_factor = scale_factor
        self.handle_scale_modifer_update_request(scale_factor.value())

        # Size the widget after adding stuff to the layout
        self.resize(800, self.sizeHint().height())  # Resize children (if needed) below this line

    def handle_back_clicked(self):
        self.hide()
        self.request_last_step.emit()

    def handle_next_clicked(self):
        self.hide()
        self.request_next_step.emit()

    def handle_scale_modifer_update_request(self, value):
        self.conversion_mgr.set_scale_modifier(value)

    def handle_scale_updated(self, value):
        self.scale_factor_summary.setText(f'({value})')
        if self.scale_factor.value() != value:
            self.scale_factor.setValue(value)


class WizardSaveSettings(QWidget):

    request_last_step = Signal()
    request_next_step = Signal()

    def __init__(self):
        super().__init__()

        # TODO refactor
        conversion_mgr = get_conversion_manager()
        conversion_mgr.output_path_updated.connect(self.handle_output_path_updated)
        conversion_mgr.output_extension_filter_updated.connect(self.update_output_ext_filter_summary)
        self.conversion_mgr = conversion_mgr

        self.output_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.request_extension_updated.connect(self.handle_output_extensions_update_request)

        self.setWindowTitle('Batch Image Converter (Step 2/3)')
        layout = QVBoxLayout()
        self.setLayout(layout)

        step_nav_box = QGroupBox()
        step_navigation_area = QHBoxLayout()
        step_nav_box.setLayout(step_navigation_area)
        layout.addWidget(step_nav_box)

        back_btn = QPushButton('Back')
        back_btn.clicked.connect(self.handle_back_clicked)
        step_navigation_area.addWidget(back_btn)
        self.back_btn = back_btn

        step_navigation_area.addStretch()
        step_navigation_area.addWidget(QLabel('Step 2: Save Settings'))
        step_navigation_area.addStretch()

        next_btn = QPushButton('Next')
        next_btn.clicked.connect(self.handle_next_clicked)
        step_navigation_area.addWidget(next_btn)
        self.next_btn = next_btn

        task_area = QVBoxLayout()
        layout.addLayout(task_area)
        self.task_area = task_area

        settings_container = QSplitter()
        task_area.addWidget(settings_container)

        # Add save-as/output folder picker controls
        output_folder_box = QGroupBox('Destination folder:')
        output_folder_area = QVBoxLayout()
        output_folder_box.setLayout(output_folder_area)
        settings_container.addWidget(output_folder_box)
        # output_folder_picker_header = QHBoxLayout()
        # output_folder_area.addLayout(output_folder_picker_header)
        # output_folder_picker_header.addWidget(QLabel('Destination Folder:'))
        # ....
        output_folder_picker_lbl = QLabel()  # Shows the output folder
        # output_folder_picker_header.addWidget(output_folder_picker_lbl)
        # output_folder_picker_header.addStretch()
        self.output_path_picker_lbl = output_folder_picker_lbl
        # self.clear_output_path()  # TODO fix this
        self.clear_output_path_summary()  # TODO fix this
        # ....
        output_path_picker_controls = QHBoxLayout()
        output_folder_area.addLayout(output_path_picker_controls)
        output_path_picker_btn = QPushButton('Choose Folder')
        output_path_picker_btn.clicked.connect(self.handle_choose_output_path)
        output_path_picker_controls.addWidget(output_path_picker_btn)
        output_path_picker_controls.addWidget(output_folder_picker_lbl)
        output_path_picker_controls.addStretch()
        self.output_path_picker_btn = output_path_picker_btn

        # Set up output/save-as controls
        output_settings_box = QGroupBox('Image Save Formats:')
        settings_container.addWidget(output_settings_box)
        output_settings_area = QVBoxLayout()
        output_settings_box.setLayout(output_settings_area)
        # ....
        # Set up save-as extensions picker header
        # output_ext_picker_header = QHBoxLayout()
        # output_settings_area.addLayout(output_ext_picker_header)
        # output_ext_picker_header.addWidget(QLabel('Output Filetype(s):'))
        output_filter_summary = QLabel()  # Shows a list of selected save-as/output extensions
        # output_ext_picker_header.addStretch()
        self.output_filter_summary = output_filter_summary
        self.update_output_ext_filter_summary()
        # Set up the save-as extension picker controls
        output_ext_picker_area = QHBoxLayout()
        output_settings_area.addLayout(output_ext_picker_area)
        output_ext_picker_btn = QPushButton('Pick Filetypes')
        output_ext_picker_btn.clicked.connect(self.handle_output_ext_picker_clicked)
        output_ext_picker_area.addWidget(output_ext_picker_btn)
        output_ext_picker_area.addWidget(output_filter_summary)
        output_ext_picker_area.addStretch()
        self.output_ext_picker_btn = output_ext_picker_btn

        # Size the widget after adding stuff to the layout
        self.resize(800, self.sizeHint().height())  # Resize children (if needed) below this line

    def clear_output_path_summary(self):
        self.output_path_picker_lbl.setText('(Empty) Select a save folder')

    # TODO move this down
    def handle_choose_output_path(self):
        manager = self.conversion_mgr

        folder_path = QFileDialog.getExistingDirectory(self)
        if folder_path:
            folder_path = os.path.abspath(folder_path)
        status = manager.set_output_path(folder_path)

        if status == STATUS_OK:
            return
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

    def handle_output_path_updated(self, path):
        self.output_path_picker_lbl.setText(os.path.basename(path))

    def handle_back_clicked(self):
        self.hide()
        self.request_last_step.emit()

    def handle_next_clicked(self):
        self.hide()
        self.request_next_step.emit()

    def handle_output_ext_picker_clicked(self):
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.show()

    def handle_output_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_save_filter(ext_name, check_state)

    def handle_output_extensions_updated(self):
        self.update_output_ext_filter_summary()
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())

    def update_output_ext_filter_summary(self):
        self.output_filter_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_save_filters().items() if state])))


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
        message.setMinimumWidth(1)
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


class WizardSummaryScreen(QWidget):  # TODO renaming/step4
    """Batch image converter home widget"""

    request_last_step = Signal()

    def __init__(self):
        super().__init__()

        # Set up a conversion data/handling object
        conversion_mgr = get_conversion_manager()
        conversion_mgr.source_extension_filter_updated.connect(self.update_input_ext_filter_summary)
        conversion_mgr.output_extension_filter_updated.connect(self.update_output_ext_filter_summary)
        conversion_mgr.file_search_progress.connect(self.handle_file_search_progress)
        conversion_mgr.file_save_progress.connect(self.handle_file_save_progress)
        conversion_mgr.source_path_updated.connect(self.handle_source_path_updated)
        conversion_mgr.output_path_updated.connect(self.handle_output_path_updated)
        conversion_mgr.modifier_scale_updated.connect(self.handle_scale_updated)
        self.conversion_mgr = conversion_mgr

        # Set some initial widget properties
        layout = QVBoxLayout()
        self.setWindowTitle('Batch image converter: Summary/Launch')
        self.setLayout(layout)

        step_nav_box = QGroupBox()
        step_navigation_area = QHBoxLayout()
        step_nav_box.setLayout(step_navigation_area)
        layout.addWidget(step_nav_box)

        back_btn = QPushButton('Back')
        back_btn.clicked.connect(self.handle_back_clicked)
        step_navigation_area.addWidget(back_btn)
        self.back_btn = back_btn

        step_navigation_area.addStretch()
        step_navigation_area.addWidget(QLabel('Summary/Launch Screen'))
        step_navigation_area.addStretch()

        launch_btn = QPushButton('Start Conversion!')
        launch_btn.clicked.connect(self.handle_convert)
        step_navigation_area.addWidget(launch_btn)

        # Hold child modal widgets here
        self.error_modal = None
        self.input_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_update_request)
        self.output_ext_picker_modal = ExtensionPicker(conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.request_extension_updated.connect(self.handle_output_extensions_update_request)
        self.file_search_progress_modal = None
        self.file_save_progress_modal = None

        # Store the MVC model for the discovered files the users wants to convert
        target_paths_model = get_target_paths_model()  # TODO Fix/refactor/move/finish
        target_paths_model.set_new_data(conversion_mgr.get_target_paths())
        self.target_paths_model = target_paths_model

        settings_container = QSplitter()
        layout.addWidget(settings_container)

        # Add user controls for choosing a folder to convert
        src_folder_box = QGroupBox('Search Folder:')
        src_folder_area = QVBoxLayout()
        src_folder_box.setLayout(src_folder_area)
        settings_container.addWidget(src_folder_box)
        # src_folder_header = QHBoxLayout()
        # layout.addLayout(src_folder_header)
        # src_folder_header.addWidget(QLabel('Selected Folder:'))  # TODO remove
        src_folder_lbl = QLabel()
        # src_folder_header.addWidget(src_folder_lbl)
        # src_folder_header.addStretch()
        self.src_folder_lbl = src_folder_lbl
        self.clear_source_path_summary()
        # ....
        src_folder_controls = QHBoxLayout()
        src_folder_area.addLayout(src_folder_controls)
        # ....
        pick_src_folder_btn = QPushButton('Choose Folder')
        pick_src_folder_btn.clicked.connect(self.handle_choose_source_path)
        src_folder_controls.addWidget(pick_src_folder_btn)
        src_folder_controls.addWidget(src_folder_lbl)
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
        self.targets_table = targets_view  # TODO renaming

        # Set up a source-filetypes summary and controls
        source_ext_box = QGroupBox('File Search Settings:')
        source_ext_area = QVBoxLayout()
        source_ext_box.setLayout(source_ext_area)
        settings_container.addWidget(source_ext_box)
        # src_formats_header = QHBoxLayout()
        # source_ext_area.addLayout(src_formats_header)
        # Set up the source-filetypes extension picker header
        # src_extensions_header = QHBoxLayout()
        # src_extensions_header.addWidget(QLabel('File Search Settings:'))
        # source_ext_area.addLayout(src_extensions_header)
        src_extensions_summary = QLabel()
        # src_extensions_header.addWidget(src_extensions_summary)
        # src_extensions_header.addStretch()
        self.src_extensions_summary = src_extensions_summary
        self.update_input_ext_filter_summary()  # Shows a list of selected extensions
        # Set up the extensions picker controls
        src_ext_picker_controls = QHBoxLayout()
        source_ext_area.addLayout(src_ext_picker_controls)
        src_ext_picker_btn = QPushButton('Pick Filetypes')
        src_ext_picker_btn.clicked.connect(self.handle_input_ext_picker_clicked)
        src_ext_picker_controls.addWidget(src_ext_picker_btn)
        src_ext_picker_controls.addWidget(src_extensions_summary)
        src_ext_picker_controls.addStretch()
        self.extension_picker_btn = src_ext_picker_btn

        image_mod_settings_box = QGroupBox('Image Modifiers:')
        image_mod_settings_area = QVBoxLayout()
        image_mod_settings_box.setLayout(image_mod_settings_area)
        layout.addWidget(image_mod_settings_box)
        # ....
        # ....
        # Set up scale factor controls
        scale_factor_header = QHBoxLayout()
        image_mod_settings_area.addLayout(scale_factor_header)
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
        scale_factor.valueChanged.connect(self.handle_scale_modifer_update_request)
        image_mod_settings_area.addWidget(scale_factor)
        self.scale_factor = scale_factor
        self.handle_scale_modifer_update_request(scale_factor.value())

        outputs_container = QSplitter()
        layout.addWidget(outputs_container)

        # Set up output/save-as controls
        output_settings_box = QGroupBox('Image Save Formats:')
        output_settings_area = QVBoxLayout()
        output_settings_box.setLayout(output_settings_area)
        # ....
        # Set up save-as extensions picker header
        # output_ext_picker_header = QHBoxLayout()
        # output_settings_area.addLayout(output_ext_picker_header)
        # output_ext_picker_header.addWidget(QLabel('Output Filetype(s):'))
        output_filter_summary = QLabel()  # Shows a list of selected save-as/output extensions
        # output_ext_picker_header.addWidget(output_filter_summary)
        # output_ext_picker_header.addStretch()
        self.output_filter_summary = output_filter_summary
        self.update_output_ext_filter_summary()
        # Set up the save-as extension picker controls
        output_ext_picker_area = QHBoxLayout()
        output_settings_area.addLayout(output_ext_picker_area)
        output_ext_picker_btn = QPushButton('Pick Filetypes')
        output_ext_picker_btn.clicked.connect(self.handle_output_ext_picker_clicked)
        output_ext_picker_area.addWidget(output_ext_picker_btn)
        output_ext_picker_area.addWidget(output_filter_summary)
        output_ext_picker_area.addStretch()
        self.output_ext_picker_btn = output_ext_picker_btn

        # Add save-as/output folder picker controls
        output_folder_box = QGroupBox('Destination folder:')
        output_folder_area = QVBoxLayout()
        output_folder_box.setLayout(output_folder_area)
        outputs_container.addWidget(output_folder_box)
        outputs_container.addWidget(output_settings_box)
        # output_folder_picker_header = QHBoxLayout()
        # output_folder_area.addLayout(output_folder_picker_header)
        # output_folder_picker_header.addWidget(QLabel('Destination Folder:'))
        # ....
        output_folder_picker_lbl = QLabel()  # Shows the output folder
        # output_folder_picker_header.addWidget(output_folder_picker_lbl)
        # output_folder_picker_header.addStretch()
        self.output_path_picker_lbl = output_folder_picker_lbl
        self.clear_output_path_summary()
        # ....
        output_path_picker_controls = QHBoxLayout()
        output_folder_area.addLayout(output_path_picker_controls)
        output_path_picker_btn = QPushButton('Choose Folder')
        output_path_picker_btn.clicked.connect(self.handle_choose_output_path)
        output_path_picker_controls.addWidget(output_path_picker_btn)
        output_path_picker_controls.addWidget(output_folder_picker_lbl)
        output_path_picker_controls.addStretch()
        self.output_path_picker_btn = output_path_picker_btn

        # TODO remove this, it's now in the step controls
        # # Add conversion launch controls
        # convert_controls = QHBoxLayout()
        # convert_controls.addStretch()
        # layout.addLayout(convert_controls)
        # convert_btn = QPushButton('Convert')
        # convert_btn.clicked.connect(self.handle_convert)
        # convert_controls.addWidget(convert_btn)
        # self.convert_btn = convert_btn

        # Size the widget after adding stuff to the layout
        self.resize(800, 600)  # Resize children (if needed) below this line
        targets_view.setColumnWidth(0, targets_view.width() / 2)
        targets_view.setColumnWidth(1, targets_view.width() / 2)
        # # Auto show() the widget!
        # self.show()

    def handle_back_clicked(self):
        self.hide()
        self.request_last_step.emit()

    def handle_source_path_updated(self, path):
        self.src_folder_lbl.setText(path)

    def clear_source_path_summary(self):
        self.src_folder_lbl.setText('(Empty) Select a folder with some images')

    def user_clear_selected_path(self):
        # Clear data
        manager = self.conversion_mgr
        manager.clear_source_path()

    def clear_output_path_summary(self):
        self.output_path_picker_lbl.setText('(Empty) Select a save folder')

    def show_conversion_task_stats(self):
        manager = self.conversion_mgr
        source_path = manager.get_source_path()

        self.src_folder_lbl.setText(
            f'({len(manager.get_target_paths()):,} images) in '
            f'"{os.path.basename(source_path)}" ({source_path})'
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
            return
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

    def handle_output_path_updated(self, path):
        self.output_path_picker_lbl.setText(os.path.basename(path))

    def handle_file_search_progress(self, match_count, search_count):
        """Handle intermittent file search progress updates, refresh the UI"""
        if self.isVisible():
            popup = self.file_search_progress_modal
            popup.set_message(f'({match_count:,}) matches\n({search_count:,}) searched...')
            QApplication.instance().processEvents()

    def handle_search_progress_popup_ok(self):
        self.file_search_progress_modal.hide()

    def handle_save_progress_popup_ok(self):
        self.file_save_progress_modal.hide()

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
        ok_btn.clicked.connect(self.handle_search_progress_popup_ok)
        box.disable_button(QDialogButtonBox.Ok)
        box.resize(400, box.minimumSizeHint().height())  # TODO: Fix this
        self.file_search_progress_modal = box
        box.show()
        # TODO handle popup close

        app.processEvents()

        # Start searching the disk for images at the specified location
        result = manager.start_file_search()
        if result[CANCELED]:
            box.set_message('Image search was canceled')
        else:
            box.set_message(
                f'Finished with {len(result[TARGETS])} images found, {len(result[ERRORS])} files with errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        # TODO restructure/simplify this
        self.target_paths_model.set_new_data(manager.get_target_paths())
        self.show_conversion_task_stats()

    def show_error_message(self, message):
        # Show a message popup (has an okay button only)
        box = CustomModal('Error!', message, [QDialogButtonBox.Ok])

        # Ok button should close the modal
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(box.hide)

        # Size and hold a reference to the window
        box.resize(300, box.minimumSizeHint().height())
        self.error_modal = box
        box.show()

    def get_extension_matcher(self, extension):
        if extension.lower() in {}:
            return

    def handle_file_save_progress(self, upcoming_filename, source_files_handled, total_count):
        """Handle intermittent file search progress updates, refresh the UI"""
        if self.isVisible():  # TODO, check this for all common GUI elements
            popup = self.file_save_progress_modal
            popup.set_message(f'Processing {os.path.basename(upcoming_filename)} ({upcoming_filename})\nFinished ({source_files_handled})/({total_count})')
            popup.progress_bar.setValue(source_files_handled)
            QApplication.instance().processEvents()

    def handle_convert(self):
        manager = self.conversion_mgr

        if len(manager.get_target_paths()) == 0:
            self.show_error_message('No input images! (Did you check for the right file types?)')
            return
        if not manager.get_source_path():
            self.show_error_message('No source folder selected!')
            return
        if not manager.get_output_path():
            self.show_error_message('No output folder selected!')
            return

        # Obtain the app, to perform manual UI updates
        app = QApplication.instance()

        # Show a progress popup
        box = CustomModal('Processing...', f'Finished ()/()')
        box.set_buttons([QDialogButtonBox.Cancel, QDialogButtonBox.Ok])
        # ....
        cancel_btn = box.button(QDialogButtonBox.Cancel)
        cancel_btn.clicked.connect(self.set_save_cancel_flag)
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(self.handle_save_progress_popup_ok)
        box.disable_button(QDialogButtonBox.Ok)
        # TODO Fix, this is broken for multiple-output-image scenarios
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(len(manager.get_target_paths()))
        box.progress_bar = progress_bar
        box.layout().insertWidget(1, progress_bar)
        box.resize(400, box.minimumSizeHint().height())
        self.file_save_progress_modal = box
        box.show()
        # TODO handle popup close

        app.processEvents()

        # Start converting/saving output images
        result = manager.start_conversion()
        if result[CANCELED]:
            box.set_message('Image conversion was canceled')
        else:
            box.set_message(
                f'Finished with {len(result["targets"])} input images processed, {len(result[ERRORS])} files with errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        print(f'Finished with {sum([len(val[ERRORS]) for item, val in manager.get_target_paths().items()])} errors')

    def set_save_cancel_flag(self):
        self.conversion_mgr.request_cancel_save()

    def update_input_ext_filter_summary(self):
        self.src_extensions_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_search_filters().items() if state])))

    def update_output_ext_filter_summary(self):
        self.output_filter_summary.setText(','.join(sorted([ext for ext, state in self.conversion_mgr.get_file_save_filters().items() if state])))

    def handle_input_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_search_filter(ext_name, check_state)

    def handle_input_extensions_updated(self):
        self.update_input_ext_filter_summary()
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())

    def handle_output_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_save_filter(ext_name, check_state)

    def handle_output_extensions_updated(self):
        self.update_output_ext_filter_summary()
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())

    def handle_input_ext_picker_clicked(self):
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.show()

    # TODO clean up manager access on these
    def handle_output_ext_picker_clicked(self):
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.show()

    def handle_scale_modifer_update_request(self, value):
        self.conversion_mgr.set_scale_modifier(value)

    def handle_scale_updated(self, value):
        self.scale_factor_summary.setText(f'({value})')
        if self.scale_factor.value() != value:
            self.scale_factor.setValue(value)


def run_gui():
    """Function scoped main app entrypoint"""
    # Initialize the QApplication!
    app = QApplication(sys.argv)

    # This widget shows itself (the main GUI entrypoint)
    # my_widget = HomeWindow()
    wizard_step1 = WizardPickFiles()
    wizard_step2 = WizardSaveSettings()
    wizard_step2.move(wizard_step1.pos())
    wizard_step3 = WizardConversionSettings()
    wizard_step3.move(wizard_step1.pos())
    wizard_summary = WizardSummaryScreen()
    wizard_summary.move(wizard_step1.pos())

    wizard_step1.request_next_step.connect(wizard_step2.show)

    wizard_step2.request_last_step.connect(wizard_step1.show)
    wizard_step2.request_next_step.connect(wizard_step3.show)

    wizard_step3.request_last_step.connect(wizard_step2.show)
    wizard_step3.request_next_step.connect(wizard_summary.show)

    wizard_summary.request_last_step.connect(wizard_step3.show)

    # Run the program/start the event loop with exec()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
