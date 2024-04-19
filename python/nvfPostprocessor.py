from __future__ import annotations

import json
import os
import re
import sys
import time
from threading import Thread

import requests
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget, QFileDialog,
                             QHBoxLayout, QLineEdit)

import postprocessor


# the following code is an example of how the app's structure could look like, feel free to change it as you see fit


class modes:
    STAND_ALONE = "stand-alone"
    POST_PROCESSOR = "post-processor"


MODE = modes.STAND_ALONE

SETTINGS_PATH = os.path.dirname(__file__) + "/nvfsettings.json"
if getattr(sys, 'frozen', False):
    SETTINGS_PATH = os.path.dirname(sys.executable) + "/nvfsettings.json"

MAX_HEIGHT = 200
MAX_WIDTH = 800


class stand_alone_window(QMainWindow):
    def __init__(self, settings: dict[str, None]):
        super().__init__()

        # Init variables
        self.settings = settings
        self.setMaximumSize(MAX_WIDTH, MAX_HEIGHT)
        self.adjustSize()
        self.setWindowTitle("Nozzle Filament Validator Post-Processor")
        self.setObjectName("Nozzle Filament Validator Post-Processor")

        try:
            self.json_path = settings["data_path"] if settings["data_path"] is not None else None
        except KeyError:
            self.json_path = None

        self.json_data = load_json_data(self.json_path)

        try:
            self.octoprint_url = settings["octoprint_url"] if settings["octoprint_url"] is not None else None
        except KeyError:
            self.octoprint_url = None

        self.pick_path_button = QPushButton("Select data file")
        self.save_button = QPushButton("Save data")
        self.file_path_layout = QLabel("File path: ")
        self.continue_print = QPushButton("Save and Export")
        self.file_dialog = QFileDialog(self, "Select the data json file", filter="*.json")
        self.octoprint_url_label = QLabel("Octoprint url: ")
        self.octoprint_url_field = QLineEdit(self.octoprint_url)
        self.octoprint_url_button = QPushButton("Save octoprint url")
        self.load_current_spool_button = QPushButton("load current spools")
        self.num_of_extruders_label = QLabel("Number of extruders in gcode: ")
        self.octoprint_error = QLabel("")

        # setup the elements
        self.setup_elements()

        # create layout elements
        self.layout = QVBoxLayout()
        self.data_box = QVBoxLayout()

        # setup the layout
        self.setup_layout()

        # refresh the display
        self.update_display_data(self.json_data)

        # create a container for the layout
        container = QWidget()
        container.setLayout(self.layout)

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
        if MODE == modes.POST_PROCESSOR:
            self.num_of_extruders_label.setText(f"Number of extruders in gcode:"
                                                f" {get_num_extruders_from_gcode(sys.argv[1])}")
            self.layout.addWidget(self.num_of_extruders_label)
        if self.get_json_path() is not None:
            self.file_path_layout.setText(f"File path: {self.get_json_path()}")

    def setup_layout(self) -> None:
        """
        Setup the layout of the window
        """
        self.layout.setSpacing(10)
        set_global_stretch_factor(self.layout, 0)
        self.data_box.setSpacing(5)
        self.layout.addWidget(self.file_path_layout)
        self.layout.addWidget(self.pick_path_button)

        if MODE == modes.POST_PROCESSOR:
            self.layout.addWidget(self.continue_print)
        else:
            self.layout.addWidget(self.save_button)

        self.layout.addWidget(self.octoprint_url_label)
        self.layout.addWidget(self.octoprint_url_field)
        self.layout.addWidget(self.octoprint_url_button)
        self.layout.addWidget(self.load_current_spool_button)
        self.layout.addWidget(self.octoprint_error)
        self.layout.addLayout(self.data_box)

    def continue_print_click(self) -> None:
        """
        Save the data and close the window
        only used when in post-processor mode
        """
        if self.json_path is None:
            self.octoprint_error.setText("No file selected")
            return
        if self.json_data is None:
            self.octoprint_error.setText("No data to save")
            return
        if not save_data_file(self.json_path, self.json_data):
            self.octoprint_error.setText(
                "Could not save the data")
            return
        self.octoprint_error.setText("")
        save_settings(self.settings)
        postprocessor.main(sys.argv[1], json_data=postprocessor.parse_json_data(self.json_data))
        self.close()

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
                widget.deleteLater()

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
            self.data_box.addWidget(extruder_widget)
        # Create a QPushButton for adding a new extruder and add it to the layout
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_extruder)
        self.data_box.addWidget(add_button)
        self.adjustSize()
        self.setFixedWidth(MAX_WIDTH)

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
        # Create a new dictionary to hold the updated json_data
        new_json_data = {}
        # Iterate over the original json_data
        for old_key, value in self.json_data.items():
            # If the old key is less than the key to be removed, keep it the same
            if int(old_key) < int(key):
                new_json_data[old_key] = value
            # If the old key is greater than or equal to the key to be removed, decrement it by 1
            else:
                new_json_data[str(int(old_key) - 1)] = value
        # Replace the old json_data with the new one
        self.json_data = new_json_data
        # Update the display
        self.update_display_data(self.json_data)

    def add_extruder(self) -> None:
        """
        add button click event handler
        this function adds a new extruder to the json data and updates the display
        """
        # Add a new extruder to json_data
        self.json_data[str(len(self.json_data) + 1)] = {"sm_name": ""}
        # Update the display
        self.update_display_data(self.json_data)

    def save_button_click(self) -> None:
        """
        save button click event handler
        this function saves the current json data to the json file
        :return:
        """
        self.read_current_spools()
        if self.get_json_path() is None:
            self.save_button.setText("No file selected")
            Thread(target=self.clear_save_button, args=(10,)).start()
            return
        if self.json_data is None:
            self.save_button.setText("No data to save")
            Thread(target=self.clear_save_button, args=(10,)).start()
            return
        if not save_data_file(self.get_json_path(), self.json_data):
            self.save_button.setText("Could not save the data, invalid file (is the file the settings file?)\nPick a "
                                     "different file and try again")
            delay = 5
        else:
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
        file_name, _ = QFileDialog.getSaveFileName(self, "Select the data json file", "", "JSON Files (*.json)")

        if file_name:
            _, ext = os.path.splitext(file_name)
            # If not, add .json
            if not ext:
                file_name += '.json'
            self.json_path = file_name
            self.save_json_data()
            self.file_path_layout.setText(f"File path: {self.get_json_path()}")
            self.json_data = load_json_data(self.get_json_path())
            self.update_display_data(self.json_data)

    def get_json_path(self) -> str | None:
        """
        Get the path to the json file
        :return: the path to the json file or None if the file is not set
        """

        return self.json_path

    def save_json_data(self) -> None:
        """
        Save the json data to the json file
        """
        self.settings["data_path"] = self.json_path
        save_settings(self.settings)


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
    window = stand_alone_window(settings)
    window.show()
    app.exec()
    if window.json_path is not None:
        # save the file and return the data
        save_data_file(window.json_path, window.json_data)


def load_json_data(path: str | None) -> dict[str, None]:
    """
    Load the data from the json file
    :param path: the path to the json file
    :return: the data or an empty dictionary if the file does not exist
    """
    if path is None:
        return {}
    if os.path.isdir(path):
        return {}
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as file:
        try:
            data = json.load(file)
            try:
                if data["settings version"] is not None:
                    return {}
            except KeyError:
                pass
            return data
        except json.JSONDecodeError:
            return {}
        except FileNotFoundError:
            return {}


def save_data_file(path: str, data: dict[str, None]) -> bool:
    """
    Save the data to the json file
    :param path: the path to the json file
    :param data: the data to save
    :return: true if the data was saved, false otherwise
    """

    if path is None:
        return False
    elif os.path.isdir(path):
        return False
    if data is None:
        return False
    try:
        with open(path, 'r') as file:
            current_data = json.load(file)
        if current_data["settings version"] is not None:
            return False
    except FileNotFoundError:
        pass
    except KeyError:
        pass
    except json.JSONDecodeError:
        pass
    with open(path, 'w') as file:
        json.dump(data, file)
    return True


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
        api_path = ("/plugin/SpoolManager/loadSpoolsByQuery?selectedPageSize=100000&from=0&to=100000&sortColumn"
                    "=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all")
        response = requests.get(url=url + api_path)
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
    api_path = ("/plugin/SpoolManager/loadSpoolsByQuery?selectedPageSize=100000&from=0&to=100000&sortColumn"
                "=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all")
    try:
        data = requests.get(url=url + api_path)
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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        MODE = modes.POST_PROCESSOR
    app = QApplication([])
    app.setWindowIcon(QIcon(os.path.dirname(__file__) + "/icon.png"))
    QApplication.setApplicationName("Nozzle Filament Validator Post-Processor")
    QApplication.setApplicationDisplayName("Nozzle Filament Validator Post-Processor")
    main()
