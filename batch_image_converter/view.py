"""UI for the image converter"""


import os.path
import sys

from PySide6.QtWidgets import (QLabel, QSlider, QFileDialog, QCheckBox, QGroupBox,
                               QTableView, QHeaderView, QDialogButtonBox,
                               QProgressBar, QSplitter)
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                               QHBoxLayout)

from batch_image_converter.constants import (EXT_BMP, EXT_GIF, EXT_JPG, EXT_PNG, EXT_TIFF, EXT_WEBP, EXT_MATCHERS,
                                             EXTENSIONS, ERR_IMAGE_OPEN, ERR_IMAGE_SAVE, STATUS_OK, ERR_FOLDER_INVALID,
                                             ERR_FOLDER_DOES_NOT_EXIST, ERR_PATH_IS_NOT_FOLDER, ERRORS, OUTPUTS,
                                             TARGETS, CANCELED)

from batch_image_converter.model import (get_conversion_manager, get_target_paths_model)


class ImageBatcherException(Exception):

    def __init__(self, *args):
        super().__init__(*args)

        self.code = None


class ExtensionPickerPopup(QWidget):

    request_extension_updated = Signal(str, bool)

    def __init__(self, initial_values, parent=None):
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


class SourcePathPicker(QWidget):
    """Holds controls for selecting a source folder"""

    request_choose_src_folder = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        src_folder_box = QGroupBox('Search Folder:')
        src_folder_area = QVBoxLayout()
        src_folder_box.setLayout(src_folder_area)
        layout.addWidget(src_folder_box)
        self.src_folder_box = src_folder_box

        src_folder_controls = QHBoxLayout()
        src_folder_area.addLayout(src_folder_controls)

        pick_src_folder_btn = QPushButton('Pick Folder')
        pick_src_folder_btn.clicked.connect(self.handle_pick_folder_clicked)
        src_folder_controls.addWidget(pick_src_folder_btn)
        self.pick_src_folder_btn = pick_src_folder_btn

        src_folder_lbl = QLabel()
        src_folder_lbl.setMinimumWidth(1)
        src_folder_controls.addWidget(src_folder_lbl)
        src_folder_controls.addStretch()
        self.src_folder_lbl = src_folder_lbl

        self.clear_source_path_summary()

    def clear_source_path_summary(self):
        self.src_folder_lbl.setText('(Empty) Select a folder with some images')

    def handle_pick_folder_clicked(self):
        self.request_choose_src_folder.emit()

    def handle_source_folder_updated(self, path, targets):
        self.src_folder_lbl.setText(
            f'({len(targets):,} images) in '
            f'"{os.path.basename(path)}" ({path})'
        )


class OutputPathPicker(QWidget):
    """Holds controls for selecting an output folder"""

    request_choose_output_folder = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        output_folder_box = QGroupBox('Destination folder:')
        output_folder_area = QVBoxLayout()
        output_folder_box.setLayout(output_folder_area)
        layout.addWidget(output_folder_box)

        output_path_picker_controls = QHBoxLayout()
        output_folder_area.addLayout(output_path_picker_controls)

        output_path_picker_btn = QPushButton('Choose Folder')
        output_path_picker_btn.clicked.connect(self.handle_pick_folder_clicked)
        output_path_picker_controls.addWidget(output_path_picker_btn)
        self.output_path_picker_btn = output_path_picker_btn

        output_folder_lbl = QLabel()  # Shows the output folder
        output_path_picker_controls.addWidget(output_folder_lbl)
        output_path_picker_controls.addStretch()
        self.output_folder_lbl = output_folder_lbl

        self.clear_output_path_summary()  # TODO fix this

    def clear_output_path_summary(self):
        self.output_folder_lbl.setText('(Empty) Select a save folder')

    def handle_pick_folder_clicked(self):
        self.request_choose_output_folder.emit()

    def handle_output_folder_updated(self, path):
        self.output_folder_lbl.setText(
            f'"{os.path.basename(path)}" ({path})'
        )


class FileFormatsPicker(QWidget):
    """Controls for selecting image formats"""

    request_choose_formats = Signal()

    def __init__(self, box_title):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        formats_area = QVBoxLayout()
        settings_box = QGroupBox(box_title)  # TODO refactor box_title
        settings_box.setLayout(formats_area)
        layout.addWidget(settings_box)

        # Set up the extensions picker controls
        format_picker_controls = QHBoxLayout()
        formats_area.addLayout(format_picker_controls)
        formats_picker_btn = QPushButton('Pick Filetypes')
        formats_picker_btn.clicked.connect(self.handle_formats_picker_clicked)
        format_picker_controls.addWidget(formats_picker_btn)
        self.formats_picker_btn = formats_picker_btn

        formats_summary = QLabel()
        format_picker_controls.addWidget(formats_summary)
        format_picker_controls.addStretch()
        self.formats_summary = formats_summary

    def update_formats_summary(self, file_formats):
        self.formats_summary.setText(','.join(sorted([ext for ext, state in file_formats.items() if state])))

    def handle_formats_picker_clicked(self):
        self.request_choose_formats.emit()


class WizardPickFiles(QWidget):

    request_next_step = Signal()

    def __init__(self):
        super().__init__()

        # TODO refactor
        conversion_mgr = get_conversion_manager()
        conversion_mgr.file_search_progress.connect(self.handle_file_search_progress)
        self.conversion_mgr = conversion_mgr

        self.error_modal = None
        self.file_search_progress_modal = None
        self.input_ext_picker_modal = ExtensionPickerPopup(conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_update_request)

        self.setWindowTitle('Batch Image Converter (Step 1/3)')
        layout = QVBoxLayout()
        self.setLayout(layout)

        step_nav_box = QGroupBox()
        step_navigation_area = QHBoxLayout()
        step_nav_box.setLayout(step_navigation_area)
        layout.addWidget(step_nav_box)

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

        source_folder_picker = SourcePathPicker()
        source_folder_picker.request_choose_src_folder.connect(self.handle_choose_source_path)
        conversion_mgr.source_path_updated.connect(source_folder_picker.handle_source_folder_updated)
        settings_container.addWidget(source_folder_picker)
        self.source_folder_picker = source_folder_picker

        source_formats_picker = FileFormatsPicker('File Search Settings:')
        source_formats_picker.update_formats_summary(conversion_mgr.get_file_search_filters())
        conversion_mgr.source_extension_filter_updated.connect(source_formats_picker.update_formats_summary)
        source_formats_picker.request_choose_formats.connect(self.handle_choose_input_formats)
        settings_container.addWidget(source_formats_picker)

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

    def handle_next_clicked(self):
        self.hide()
        self.request_next_step.emit()

    def handle_input_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_search_filter(ext_name, check_state)

    def handle_choose_input_formats(self):
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

    def handle_file_search_progress(self, match_count, search_count):
        """Handle intermittent file search progress updates, refresh the UI"""
        if self.isVisible():
            popup = self.file_search_progress_modal
            popup.set_message(f'({match_count:,}) matches\n({search_count:,}) searched...')
            QApplication.instance().processEvents()

    def set_folder_choose_cancel_flag(self):
        # Set the cancel flag on the widget
        self.file_search_progress_modal.disable_button(QDialogButtonBox.Cancel)
        self.conversion_mgr.request_cancel_folder_open()

    def handle_search_progress_popup_ok(self):
        self.file_search_progress_modal.hide()

    def show_source_folder_stats(self):
        manager = self.conversion_mgr
        source_path = manager.get_source_path()

        self.source_folder_picker.handle_source_folder_updated(
            source_path,
            manager.get_target_paths()
        )

    def handle_choose_source_path(self):
        manager = self.conversion_mgr

        folder_path = QFileDialog.getExistingDirectory(self)
        if folder_path:
            folder_path = os.path.abspath(folder_path)
        status = manager.set_source_path(folder_path)

        if status != STATUS_OK:
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
                f'Finished with {len(result[TARGETS])} images found, {len(result[ERRORS])} errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        # TODO restructure/simplify this
        self.target_paths_model.set_new_data(manager.get_target_paths())
        self.show_source_folder_stats()


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
        # conversion_mgr.output_extension_filter_updated.connect(self.update_output_ext_filter_summary)
        self.conversion_mgr = conversion_mgr

        self.output_ext_picker_modal = ExtensionPickerPopup(conversion_mgr.get_file_save_filters())
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

        output_folder_picker = OutputPathPicker()
        output_folder_picker.request_choose_output_folder.connect(self.handle_choose_output_path)
        conversion_mgr.output_path_updated.connect(output_folder_picker.handle_output_folder_updated)
        settings_container.addWidget(output_folder_picker)
        self.output_folder_picker = output_folder_picker

        output_formats_picker = FileFormatsPicker('Image Save Formats:')
        output_formats_picker.update_formats_summary(conversion_mgr.get_file_save_filters())
        conversion_mgr.output_extension_filter_updated.connect(output_formats_picker.update_formats_summary)
        output_formats_picker.request_choose_formats.connect(self.handle_choose_output_formats)
        settings_container.addWidget(output_formats_picker)

        # Size the widget after adding stuff to the layout
        self.resize(800, self.sizeHint().height())  # Resize children (if needed) below this line

    def show_error_message(self, message):
        # TODO possibly deduplicate/mixin this
        # Show a message popup (has an okay button only)
        box = CustomModal('Error!', message, [QDialogButtonBox.Ok])

        # Ok button should close the modal
        ok_btn = box.button(QDialogButtonBox.Ok)
        ok_btn.clicked.connect(box.hide)

        # Size and hold a reference to the window
        box.resize(300, box.minimumSizeHint().height())
        self.error_modal = box
        box.show()

    def handle_back_clicked(self):
        self.hide()
        self.request_last_step.emit()

    def handle_next_clicked(self):
        self.hide()
        self.request_next_step.emit()

    def handle_choose_output_formats(self):
        self.output_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.show()

    def handle_output_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_save_filter(ext_name, check_state)

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
        # conversion_mgr.output_extension_filter_updated.connect(self.update_output_ext_filter_summary)
        conversion_mgr.file_search_progress.connect(self.handle_file_search_progress)
        conversion_mgr.file_save_progress.connect(self.handle_file_save_progress)
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
        self.input_ext_picker_modal = ExtensionPickerPopup(conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.request_extension_updated.connect(self.handle_input_extensions_update_request)
        self.output_ext_picker_modal = ExtensionPickerPopup(conversion_mgr.get_file_save_filters())
        self.output_ext_picker_modal.request_extension_updated.connect(self.handle_output_extensions_update_request)
        self.file_search_progress_modal = None
        self.file_save_progress_modal = None

        # Store the MVC model for the discovered files the users wants to convert
        target_paths_model = get_target_paths_model()  # TODO Fix/refactor/move/finish
        target_paths_model.set_new_data(conversion_mgr.get_target_paths())
        self.target_paths_model = target_paths_model

        # TODO refactor settings_container
        settings_container = QSplitter()
        layout.addWidget(settings_container)

        source_folder_picker = SourcePathPicker()
        source_folder_picker.request_choose_src_folder.connect(self.handle_choose_source_path)
        conversion_mgr.source_path_updated.connect(source_folder_picker.handle_source_folder_updated)
        settings_container.addWidget(source_folder_picker)
        self.source_folder_picker = source_folder_picker

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

        source_formats_picker = FileFormatsPicker('File Search Settings:')
        source_formats_picker.update_formats_summary(conversion_mgr.get_file_search_filters())
        conversion_mgr.source_extension_filter_updated.connect(source_formats_picker.update_formats_summary)
        source_formats_picker.request_choose_formats.connect(self.handle_choose_input_formats)
        settings_container.addWidget(source_formats_picker)

        image_mod_settings_box = QGroupBox('Image Modifiers:')
        image_mod_settings_area = QVBoxLayout()
        image_mod_settings_box.setLayout(image_mod_settings_area)
        layout.addWidget(image_mod_settings_box)
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

        output_folder_picker = OutputPathPicker()
        output_folder_picker.request_choose_output_folder.connect(self.handle_choose_output_path)
        conversion_mgr.output_path_updated.connect(output_folder_picker.handle_output_folder_updated)
        outputs_container.addWidget(output_folder_picker)
        self.output_folder_picker = output_folder_picker

        output_formats_picker = FileFormatsPicker('Image Save Formats:')
        output_formats_picker.update_formats_summary(conversion_mgr.get_file_save_filters())
        conversion_mgr.output_extension_filter_updated.connect(output_formats_picker.update_formats_summary)
        output_formats_picker.request_choose_formats.connect(self.handle_choose_output_formats)
        outputs_container.addWidget(output_formats_picker)

        # Size the widget after adding stuff to the layout
        self.resize(800, 600)  # Resize children (if needed) below this line
        targets_view.setColumnWidth(0, targets_view.width() / 2)
        targets_view.setColumnWidth(1, targets_view.width() / 2)

    def handle_back_clicked(self):
        self.hide()
        self.request_last_step.emit()

    def show_source_folder_stats(self):
        manager = self.conversion_mgr
        source_path = manager.get_source_path()

        self.source_folder_picker.handle_source_folder_updated(
            source_path,
            manager.get_target_paths()
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
            return  # TODO refactor
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
        # TODO: Deduplicate this with source folder picker wizard
        manager = self.conversion_mgr

        folder_path = QFileDialog.getExistingDirectory(self)
        if folder_path:
            folder_path = os.path.abspath(folder_path)
        status = manager.set_source_path(folder_path)

        if status != STATUS_OK:
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
                f'Finished with {len(result[TARGETS])} images found, {len(result[ERRORS])} errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        # TODO restructure/simplify this
        self.target_paths_model.set_new_data(manager.get_target_paths())
        self.show_source_folder_stats()

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
                f'Finished with {len(result[TARGETS])} input images processed, {len(result[ERRORS])} errors'
            )  # TODO add total filecount
        box.disable_button(QDialogButtonBox.Cancel)
        box.enable_button(QDialogButtonBox.Ok)

        print(f'Finished with {sum([len(val[ERRORS]) for item, val in manager.get_target_paths().items()])} errors')

    def set_save_cancel_flag(self):
        self.conversion_mgr.request_cancel_save()

    def handle_input_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_search_filter(ext_name, check_state)

    def handle_output_extensions_update_request(self, ext_name, check_state):
        self.conversion_mgr.set_file_save_filter(ext_name, check_state)

    def handle_choose_input_formats(self):
        self.input_ext_picker_modal.set_check_states(self.conversion_mgr.get_file_search_filters())
        self.input_ext_picker_modal.show()

    # TODO clean up manager access on these
    def handle_choose_output_formats(self):
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
