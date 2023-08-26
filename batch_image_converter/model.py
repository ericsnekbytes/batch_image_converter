"""Models for the image converter"""


import datetime
import json
import os
import traceback

from PIL import Image
from PySide6.QtCore import QAbstractTableModel, QObject, Signal
from PySide6.QtGui import Qt

from batch_image_converter.constants import (EXT_BMP, EXT_GIF, EXT_JPG, EXT_PNG, EXT_TIFF, EXT_WEBP, EXT_MATCHERS,
                                             EXTENSIONS, ERR_IMAGE_OPEN, ERR_IMAGE_SAVE, STATUS_OK, ERR_FOLDER_INVALID,
                                             ERR_FOLDER_DOES_NOT_EXIST, ERR_PATH_IS_NOT_FOLDER, ERRORS, OUTPUTS,
                                             TARGETS, CANCELED)


_TARGET_PATHS_MODEL = None  # Holds shared target paths model at runtime
_CONVERSION_MANAGER = None  # Holds shared conversion manager at runtime


def new_file_metadata():
    return {ERRORS: [], OUTPUTS: []}


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
    source_path_updated = Signal(str, object)
    output_path_updated = Signal(str)
    source_extension_filter_updated = Signal(object)
    output_extension_filter_updated = Signal(object)
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
            self.source_path_updated.emit(source_path, self.get_target_paths())
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
        self.output_extension_filter_updated.emit(self.get_file_save_filters())

    def set_file_search_filter(self, ext_name, check_state):
        self.source_extension_filter[ext_name] = check_state
        self.source_extension_filter_updated.emit(self.get_file_search_filters())

    def write_conversion_log(self):
        print(f'[py_img_batcher] Preparing conversion log...')
        task_record_path = self.get_safe_output_path(os.path.join(self.output_path, 'image_conversion_log'), 'json')
        print(f'[py_img_batcher] Writing log {task_record_path}')
        with open(task_record_path, 'w', encoding='utf8') as fhandle:
            json.dump(self.target_paths, fhandle, indent=4)

    def get_safe_output_path(self, src_path, extension):
        base_name = os.path.basename(os.path.splitext(src_path)[0])

        name_attempt_counter = -1
        current_name = os.path.join(self.output_path, f'{base_name}.{extension}')

        if os.path.exists(current_name):
            print(f'[py_img_batcher] File name conflict, name exists (attempting new name):')
        while os.path.exists(current_name):
            print(f'[py_img_batcher]   {current_name}')
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
            print(f'[py_img_batcher] Converting {image_path}')

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


def get_target_paths_model():
    global _TARGET_PATHS_MODEL
    if _TARGET_PATHS_MODEL is None:
        _TARGET_PATHS_MODEL = TargetPathsModel()
    return _TARGET_PATHS_MODEL


def get_conversion_manager():
    global _CONVERSION_MANAGER
    if _CONVERSION_MANAGER is None:
        _CONVERSION_MANAGER = ConversionManager()
    return _CONVERSION_MANAGER
