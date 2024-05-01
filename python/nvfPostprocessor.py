from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from threading import Thread

import requests
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget, QFileDialog,
                             QHBoxLayout, QLineEdit, QWIDGETSIZE_MAX)

import postprocessor


class modes:
    STAND_ALONE = "stand-alone"
    POST_PROCESSOR = "post-processor"


MODE = modes.STAND_ALONE

SETTINGS_PATH = os.path.dirname(__file__) + "/nvfsettings.json"
if getattr(sys, 'frozen', False):
    SETTINGS_PATH = os.path.dirname(sys.executable) + "/nvfsettings.json"

MAX_WIDTH = 800


class main_app(QMainWindow):
    def __init__(self, settings: dict[str, None]):
        super().__init__()

        # Init variables
        self.settings = settings
        self.adjustSize()
        self.setWindowTitle("Nozzle Filament Validator Post-Processor")
        self.setObjectName("Nozzle Filament Validator Post-Processor")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)

        self.json_data: dict = load_json_data()

        self.gcode_path = None

        try:
            self.octoprint_url = settings["octoprint_url"] if settings["octoprint_url"] is not None else None
        except KeyError:
            self.octoprint_url = None

        self.pick_path_button = QPushButton("Select Gcode file")
        self.save_button = QPushButton("Save data")
        self.file_path_layout = QLabel("Gcode file path: ")
        self.continue_print = QPushButton("Export")
        self.file_dialog = QFileDialog(self, "Select the data json file", filter="*.json")
        self.octoprint_url_label = QLabel("Octoprint url: ")
        self.octoprint_url_field = QLineEdit(self.octoprint_url)
        self.octoprint_url_button = QPushButton("Save octoprint url")
        self.load_current_spool_button = QPushButton("load current spools")
        self.num_of_extruders_label = QLabel("Number of extruders in gcode: ")
        self.octoprint_error = QLabel("")
        self.edit_gcode_button = QPushButton("Edit Gcode")

        # setup the elements
        self.setup_elements()

        # create layout elements
        self.layout = QVBoxLayout()
        self.widget = QVBoxLayout()
        self.data_box = QVBoxLayout()

        # setup the layout
        self.setup_layout()

        # refresh the display
        self.update_display_data(self.json_data)

        # create a container for the layout
        container = QWidget()
        container.setLayout(self.widget)

        # set the central widget
        self.setCentralWidget(container)

    def setup_elements(self) -> None:
        """
        Setup the elements of the window
        """
        self.octoprint_url_field.setPlaceholderText("Enter the octoprint url here")
        self.octoprint_url_field.setMaximumHeight(25)
        self.octoprint_url_field.setMaximumWidth(MAX_WIDTH)

        self.octoprint_error.setWordWrap(True)
        self.octoprint_error.setMaximumWidth(MAX_WIDTH)

        self.continue_print.clicked.connect(self.continue_print_click)
        self.octoprint_url_button.clicked.connect(self.save_octoprint_url)
        # only allow json files by default
        self.save_button.clicked.connect(self.save_button_click)
        self.pick_path_button.clicked.connect(self.pick_file_button_click)
        # self.file_dialog.fileSelected.connect(self.handle_file_selected)
        self.load_current_spool_button.clicked.connect(self.load_current_spools)
        self.edit_gcode_button.clicked.connect(self.edit_gcode)
        if MODE == modes.POST_PROCESSOR:
            self.num_of_extruders_label.setText(f"Number of extruders in gcode:"
                                                f" {get_num_extruders_from_gcode(sys.argv[1])}")
        if MODE == modes.STAND_ALONE:
            self.file_path_layout.setText(
                f"Gcode file path: {self.get_gcode_path() if self.get_gcode_path() else 'No file selected'}")
        else:
            self.file_path_layout.setText(f"Post-processing the slicer file")

    def setup_layout(self) -> None:
        """
        Setup the layout of the window
        """
        self.layout.setSpacing(10)
        set_global_stretch_factor(self.layout, 0)
        self.data_box.setSpacing(5)
        self.layout.addWidget(self.file_path_layout)
        if MODE == modes.STAND_ALONE:
            self.layout.addWidget(self.pick_path_button)
            self.layout.addWidget(self.edit_gcode_button)
        else:
            self.layout.addWidget(self.continue_print)

        self.layout.addWidget(self.octoprint_url_label)
        self.layout.addWidget(self.octoprint_url_field)
        self.layout.addWidget(self.octoprint_url_button)
        self.layout.addWidget(self.load_current_spool_button)
        self.layout.addWidget(self.octoprint_error)
        if MODE == modes.POST_PROCESSOR:
            self.layout.addWidget(self.num_of_extruders_label)

        data_boxes = QWidget()
        data_boxes.setLayout(self.layout)
        data_boxes.setFixedHeight(275)
        bottom_buttons = QVBoxLayout()
        self.widget.addWidget(data_boxes)
        self.widget.addLayout(self.data_box)
        self.widget.setSpacing(15)
        bottom_buttons.addWidget(self.save_button)
        self.widget.addLayout(bottom_buttons)

    def continue_print_click(self) -> None:
        """
        Save the data and close the window
        only used when in post-processor mode
        """
        if self.json_data is None:
            self.octoprint_error.setText("No data to export")
            return
        self.octoprint_error.setText("")
        self.save_data()
        postprocessor.main(sys.argv[1], json_data=postprocessor.parse_json_data(self.json_data))
        self.close()

    def edit_gcode(self) -> None:
        """
        Open the gcode file in the default text editor
        """
        self.save_data()
        if self.get_gcode_path() is not None:
            postprocessor.main(self.get_gcode_path(), json_data=postprocessor.parse_json_data(self.json_data))
            self.octoprint_error.setText("Gcode updated successfully")
            Thread(target=self.clear_error, args=(5,)).start()
        else:
            self.octoprint_error.setText("No Gcode file selected")
            Thread(target=self.clear_error, args=(5,)).start()

    def clear_error(self, delay: int) -> None:
        """
        Clear the error text after a specified delay.
        This function is meant to be run in a separate thread
        :param delay: the delay in seconds before clearing the text
        """
        time.sleep(delay)
        self.octoprint_error.setText("")

    def load_current_spools(self) -> None:
        """
        Load the current spools from octoprint and store them in the json_data dictionary
        """
        spools = get_loaded_spools(self.octoprint_url)
        if spools is None:
            self.octoprint_error.setText("Could not load the spools")
            return
        # if the spool is none add an empty string to the json_data
        for i, spool in enumerate(spools):
            self.json_data[str(i + 1)] = {"sm_name": spool}

        self.update_display_data(self.json_data)

    def get_gcode_path(self) -> str | None:
        """
        Get the path to the gcode file
        :return: the path to the gcode file or None if the file is not set
        """

        return self.gcode_path

    def save_octoprint_url(self) -> None:
        """
        Save the octoprint url to the settings
        """
        url = self.octoprint_url_field.text()
        if check_octoprint_settings(url) is not True:
            self.octoprint_error.setText(check_octoprint_settings(url))
        else:
            self.settings["octoprint_url"] = url
            save_settings(self.settings)
            self.octoprint_error.setText("Octoprint url saved successfully")
            self.octoprint_url = url

    def read_current_spools(self) -> None:
        """
        Read the spool names from the display and update the json_data dictionary
        """
        # Iterate over the widgets in the data_box layout
        for i in range(self.data_box.count()):
            widget = self.data_box.itemAt(i).widget()
            if widget:
                # Get the layout of the widget
                layout = widget.layout()
                if layout:
                    # Get the extruder number from the QLabel
                    extruder_number = layout.itemAt(0).widget().text().split()[1][:-1]
                    # Get the spool name from the QLineEdit
                    spool_name = layout.itemAt(1).widget().text()
                    # Update the json_data dictionary
                    self.json_data[extruder_number]['sm_name'] = spool_name

    def clear_extruder_data(self) -> None:
        """
        Clear the extruder data from the display
        """
        # remove current data while leaving buttons
        for i in reversed(range(self.data_box.count())):
            widget = self.data_box.itemAt(i).widget()
            if widget is not None:
                # Remove widget from data_box
                self.data_box.removeWidget(widget)
                # Delete widget
                widget.destroy()

    def update_display_data(self, json_data: dict[str, dict[str, str]] | dict[str, None]) -> None:
        """
        Update the display with the json data
        :param json_data: the json data to display
        """
        self.clear_extruder_data()
        for key, value in json_data.items():
            # Create a QHBoxLayout for each extruder
            extruder_layout = QHBoxLayout()
            # Create a QLabel for the extruder number and add it to the layout
            extruder_label = QLabel(f"Extruder {key}:")
            extruder_layout.addWidget(extruder_label)
            # Create a QLineEdit for the spool name and add it to the layout
            spool_name_field = QLineEdit(value['sm_name'])
            extruder_layout.addWidget(spool_name_field)
            # Create a QPushButton for removing the extruder and add it to the layout
            remove_button = QPushButton("Remove")
            remove_button.clicked.connect(lambda: self.remove_extruder(key))
            extruder_layout.addWidget(remove_button)
            # Create a QWidget to hold the layout and add a border to it
            extruder_widget = QWidget()
            extruder_widget.setLayout(extruder_layout)
            extruder_widget.setStyleSheet("border: 1px solid black;")
            # Add the QWidget to the data_box layout
            extruder_widget.setFixedHeight(54)
            self.data_box.addWidget(extruder_widget)
        # Create a QPushButton for adding a new extruder and add it to the layout
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_extruder)
        self.data_box.addWidget(add_button)
        self.setMinimumSize(MAX_WIDTH, 0)
        if self.centralWidget():
            self.centralWidget().update()
        self.adjustSize()
        if self.centralWidget():
            self.centralWidget().update()

        self.setFixedWidth(MAX_WIDTH)
        # Use a QTimer to delay the call to self.size()
        QTimer.singleShot(0, self.lock_size)

    def lock_size(self):
        """
        function to lock the size of the widget
        """
        self.setFixedSize(self.size())

    def remove_extruder(self, key: str) -> None:
        """
        remove button click event handler
        this function removes an extruder from the json data and updates the display
        :param key: the key of the extruder to remove
        """
        if not key or key not in self.json_data:
            return
        # Remove the extruder from json_data
        del self.json_data[key]
        self.update_display_data(self.json_data)

    def add_extruder(self) -> None:
        """
        add button click event handler
        this function adds a new extruder to the json data and updates the display
        """
        # Add a new extruder to json_data
        self.json_data[str(len(self.json_data) + 1)] = {"sm_name": ""}
        # Update the display
        self.widget.setSpacing(15)
        self.update_display_data(self.json_data)

    def save_data(self):
        self.read_current_spools()
        self.settings["spool_data"] = self.json_data

    def save_button_click(self) -> None:
        """
        save button click event handler
        this function saves the current json data to the json file
        :return:
        """
        self.read_current_spools()
        if self.json_data is None or self.json_data == {}:
            self.save_button.setText("No data to save")
            Thread(target=self.clear_save_button, args=(10,)).start()
            return
        else:
            self.save_data()
            save_settings(self.settings)
            self.save_button.setText("Data saved successfully")
            delay = 2

        Thread(target=self.clear_save_button, args=(delay,)).start()

    def clear_save_button(self, delay: int) -> None:
        """
        Clear the save button text after a specified delay.
        This function is meant to be run in a separate thread
        :param delay: the delay in seconds before clearing the text
        """
        time.sleep(delay)
        self.save_button.setText("Save Data")

    def pick_file_button_click(self) -> None:
        """
        Open a file dialog to select the json file
        """
        home_dir = os.path.expanduser('~')
        file_name, _ = QFileDialog.getOpenFileName(self, "Select the data json file", home_dir, "Gcode Files (*.gcode)")

        if file_name:
            _, ext = os.path.splitext(file_name)
            # If not, add .json
            if not ext:
                file_name += '.gcode'
            self.gcode_path = file_name
            self.file_path_layout.setText(
                f"Gcode file path: {self.get_gcode_path() if self.get_gcode_path() else 'No file selected'}")
            self.get_spools_from_gcode()

    def get_spools_from_gcode(self):
        """
        Get the spools from the gcode file and update the json data
        """
        spools = get_spools_from_gcode(self.get_gcode_path())
        if spools is None or spools == {}:
            self.octoprint_error.setText("Could not load the spools, file may not have been sliced correctly")
            Thread(target=self.clear_error, args=(5,)).start()
            self.gcode_path = None
            self.json_data = load_json_data()
            self.update_display_data(self.json_data)
            return
        self.file_path_layout.setText(f"Gcode file path: "
                                      f"{self.get_gcode_path() if self.get_gcode_path() else 'No file selected'}")
        self.json_data = {}
        for i, spool in spools.items():
            self.json_data[str(i)] = {"sm_name": spool}
        self.update_display_data(self.json_data)


def set_global_stretch_factor(layout: QVBoxLayout, stretch_factor: int) -> None:
    """
    Set the stretch factor for all widgets in the layout
    :param layout: the layout object
    :param stretch_factor: the stretch factor
    """
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget:
            layout.setStretchFactor(widget, stretch_factor)


def main() -> None:
    """
    Main function
    :return:
    """
    # show interface to edit the json data and add/remove extruders
    settings = load_settings()
    # the app
    window = main_app(settings)
    window.show()
    app.exec()
    save_settings(window.settings)


def load_json_data() -> dict[str, None]:
    """
    Load the data from the json file
    :param path: the path to the json file
    :return: the data or an empty dictionary if the file does not exist
    """
    path = SETTINGS_PATH

    if path is None:
        return {}
    if os.path.isdir(path):
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as file:
        try:
            data = json.load(file)["spool_data"]
            return data
        except json.JSONDecodeError:
            return {}
        except FileNotFoundError:
            return {}
        except KeyError:
            return {}


def save_settings(json_data: dict[str, None]) -> None:
    """
    Save the settings to the json file
    :param json_data: the json data
    """

    with open(SETTINGS_PATH, 'w') as file:
        json_data["settings version"] = 1

        json.dump(json_data, file)


def load_settings() -> dict[str, None]:
    """
    Load the settings from the json file
    :return: the json data or an empty dictionary if the file does not exist
    """
    try:
        return json.load(open(SETTINGS_PATH, 'r'))
    except FileNotFoundError:
        return {}


def check_octoprint_settings(url: str) -> bool | str:
    """
    Check the octoprint settings
    :param url: the base octoprint url
    :return: True if the settings are correct, the error message otherwise
    """
    try:
        path_1 = "/plugin/SpoolManager/loadSpoolsByQuery?selectedPageSize=100000&from=0&to=100000&sortColumn"
        path_2 = "=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all"
        response = requests.get(url=url + path_1 + path_2)
        if response.status_code != 200:
            return f"Could not connect to the octoprint server: \"{response.status_code}\""
    except requests.exceptions.ConnectionError as e:
        return f"Could not connect to the octoprint server: \"{e}\""

    return True


def get_loaded_spools(url: str) -> list[str] | None:
    """
    Get the loaded spools from octoprint
    :param url: the base octoprint url
    :return: a list of the loaded spools name or None if there was an error
    """
    # get the spools from the database
    # return the spools
    path_numbero_uno = "/plugin/SpoolManager/loadSpoolsByQuery?selectedPageSize=100000&from=0&to=100000&sortColumn"
    path_numbero_dos = "=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all"
    try:
        data = requests.get(url=url + path_numbero_uno + path_numbero_dos)
        if data.status_code != 200:
            return None
        json_data = data.json()
    except requests.exceptions.ConnectionError:
        return None
    except json.JSONDecodeError:
        return None
    except TypeError:
        return None
    # remove all except loaded spools
    json_data = json_data["selectedSpools"]
    # create a list where each element is the name of a spool, the spools are in order of the extruders in the json
    # response
    spool_data = []

    for spool in json_data:
        try:
            spool_data += [spool["displayName"]]
        except KeyError:
            spool_data += [""]
        except TypeError:
            spool_data += [""]
    # the app
    return spool_data


def get_num_extruders_from_gcode(gcode_path) -> int:
    """
    Get the number of extruders from the gcode file
    :param gcode_path: the path to the gcode file
    :return: the number of extruders
    """
    count = 0
    gcode = postprocessor.parse_gcode(gcode_path)
    filament_notes_pattern = re.compile(r'; filament_notes = (.+)')
    filament_notes_match = filament_notes_pattern.search(gcode)
    filament_notes = None
    if filament_notes_match:
        filament_notes = filament_notes_match.group(1).strip().split(';')
    if filament_notes is None:
        return 0

    # loop through the json data
    for i in range(len(filament_notes)):
        if re.search(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]", filament_notes[i]):
            count += 1
    return count


def get_spools_from_gcode(gcode_path) -> dict[int, str]:
    """
    Get the number of extruders from the gcode file
    :param gcode_path: the path to the gcode file
    :return: the number of extruders
    """
    spools = {}
    gcode = postprocessor.parse_gcode(gcode_path)
    filament_notes_pattern = re.compile(r'; filament_notes = (.+)')
    filament_notes_match = filament_notes_pattern.search(gcode)
    filament_notes = None
    if filament_notes_match:
        filament_notes = filament_notes_match.group(1).strip().split(';')
    if filament_notes is None:
        return {}
    if filament_notes == ['""'] or filament_notes == ['']:
        return {}
    # loop through the json data
    for i in range(len(filament_notes)):
        if re.search(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]", filament_notes[i]):
            spools[i + 1] = (re.search(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]", filament_notes[i]).group(1))
        else:
            spools[i + 1] = ""
    return spools


if __name__ == "__main__":
    if len(sys.argv) > 1:
        MODE = modes.POST_PROCESSOR
    app = QApplication([])
    app.setStyleSheet("""
        QMainWindow {
            background-color: #333233;
        }
        QPushButton {
            background-color: #01274f;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: #01172e;
        }
        QLineEdit {
            background-color: #333233;
            border: 1px solid #FFFFFF;
            border-radius: 5px;
            color: #FFF;
            padding: 5px;
        }
        QLabel {
            color: #FFF;
        }
        """)
    app.setWindowIcon(QIcon(os.path.dirname(__file__) + "/icon.png"))
    QApplication.setApplicationName("Nozzle Filament Validator Post-Processor")
    QApplication.setApplicationDisplayName("Nozzle Filament Validator Post-Processor")
    main()
