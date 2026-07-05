#include <QtCore/QFile>
#include <QtCore/QDir>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTimer>
#include <QtCore/QUrl>
#include <QtGui/QIcon>
#include <QtGui/QPixmap>
#include <QtWidgets/QApplication>
#include <QtWidgets/QFileDialog>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QMainWindow>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QScrollArea>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QWidget>
#include "icon_png.h"

extern "C" {
char *nvf_rust_get_spools_from_gcode(const char *path);
char *nvf_rust_process_gcode(const char *path, const char *spool_data_json);
char *nvf_rust_get_loaded_spools(const char *url, const char *api_key);
void nvf_rust_free_string(char *value);
}

static constexpr int MAX_WIDTH = 800;

struct RustResponse {
    bool ok = false;
    QString error;
    QJsonObject data;
};

static RustResponse callRust(char *raw) {
    RustResponse out;
    if (!raw) {
        out.error = "Rust call returned no data";
        return out;
    }
    QByteArray bytes(raw);
    nvf_rust_free_string(raw);
    QJsonParseError parseError;
    QJsonDocument doc = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        out.error = "Rust call returned invalid JSON";
        return out;
    }
    QJsonObject object = doc.object();
    out.ok = object.value("ok").toBool(false);
    if (!out.ok) {
        out.error = object.value("error").toString("Unknown error");
        return out;
    }
    out.data = object.value("data").toObject();
    return out;
}

static QString settingsPath(const QString &fileName) {
    return QApplication::applicationDirPath() + "/" + fileName;
}

static QString iconPath() {
    QString resourcesPath = QApplication::applicationDirPath() + "/../Resources/icon.png";
    if (QFile::exists(resourcesPath)) {
        return resourcesPath;
    }
    return QApplication::applicationDirPath() + "/icon.png";
}

static QIcon appIcon() {
    QPixmap pixmap;
    pixmap.loadFromData(NVF_ICON_PNG, NVF_ICON_PNG_LEN, "PNG");
    if (!pixmap.isNull()) {
        return QIcon(pixmap);
    }
    return QIcon(iconPath());
}

static QJsonObject loadSettings() {
    for (const QString &path : {settingsPath("nfvsettings.json"), settingsPath("nvfsettings.json")}) {
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) {
            continue;
        }
        QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
        if (doc.isObject()) {
            return doc.object();
        }
    }
    return {};
}

static void saveSettings(const QJsonObject &settings) {
    QJsonObject out = settings;
    out["settings version"] = 1;
    QFile file(settingsPath("nfvsettings.json"));
    if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        file.write(QJsonDocument(out).toJson(QJsonDocument::Compact));
    }
}

class MainWindow : public QMainWindow {
public:
    MainWindow(bool postProcessorMode, QString gcodePath)
        : modePostProcessor(postProcessorMode), gcodePath(std::move(gcodePath)), settings(loadSettings()) {
        setWindowTitle("Nozzle Filament Validator Post-Processor");
        setObjectName("Nozzle Filament Validator Post-Processor");
        setWindowFlag(Qt::WindowMaximizeButtonHint, false);
        setWindowIcon(appIcon());

        jsonData = settings.value("spool_data").toObject();
        octoprintUrl = settings.value("octoprint_url").toString();
        octoprintApiKey = settings.value("octoprint_api_key").toString();

        auto *central = new QWidget(this);
        widget = new QVBoxLayout();
        widget->setSpacing(15);
        central->setLayout(widget);
        setCentralWidget(central);

        setupTopBox();
        setupDataBox();
        updateDisplayData();

        setMinimumSize(MAX_WIDTH, 0);
        adjustSize();
        setFixedWidth(MAX_WIDTH);
        QTimer::singleShot(0, this, [this] { setFixedSize(size()); });
    }

    ~MainWindow() override {
        saveData();
        saveSettings(settings);
    }

private:
    bool modePostProcessor = false;
    QString gcodePath;
    QJsonObject settings;
    QJsonObject jsonData;
    QString octoprintUrl;
    QString octoprintApiKey;
    QVBoxLayout *widget = nullptr;
    QVBoxLayout *layout = nullptr;
    QVBoxLayout *dataBox = nullptr;
    QLabel *filePathLabel = nullptr;
    QLabel *octoprintError = nullptr;
    QLineEdit *octoprintUrlField = nullptr;
    QLineEdit *octoprintApiKeyField = nullptr;

    void setupTopBox() {
        layout = new QVBoxLayout();
        layout->setSpacing(10);

        filePathLabel = new QLabel(this);
        if (modePostProcessor) {
            filePathLabel->setText("Post-processing the slicer file");
        } else {
            filePathLabel->setText("Gcode file path: " + (gcodePath.isEmpty() ? "No file selected" : gcodePath));
        }
        layout->addWidget(filePathLabel);

        if (modePostProcessor) {
            auto *exportButton = new QPushButton("Export", this);
            connect(exportButton, &QPushButton::clicked, this, [this] { continuePrintClick(); });
            layout->addWidget(exportButton);
        } else {
            auto *selectButton = new QPushButton("Select Gcode file", this);
            connect(selectButton, &QPushButton::clicked, this, [this] { pickFileButtonClick(); });
            layout->addWidget(selectButton);
            auto *editButton = new QPushButton("Edit Gcode", this);
            connect(editButton, &QPushButton::clicked, this, [this] { editGcode(); });
            layout->addWidget(editButton);
        }

        layout->addWidget(new QLabel("Octoprint url: ", this));
        octoprintUrlField = new QLineEdit(octoprintUrl, this);
        octoprintUrlField->setPlaceholderText("Enter the octoprint url here");
        octoprintUrlField->setMaximumHeight(25);
        octoprintUrlField->setMaximumWidth(MAX_WIDTH);
        layout->addWidget(octoprintUrlField);

        layout->addWidget(new QLabel("Octoprint API key: ", this));
        octoprintApiKeyField = new QLineEdit(octoprintApiKey, this);
        octoprintApiKeyField->setPlaceholderText("Enter the Octoprint API key here");
        octoprintApiKeyField->setMaximumHeight(25);
        octoprintApiKeyField->setMaximumWidth(MAX_WIDTH);
        octoprintApiKeyField->setEchoMode(QLineEdit::Password);
        layout->addWidget(octoprintApiKeyField);

        auto *saveOctoButton = new QPushButton("Save Octoprint settings", this);
        connect(saveOctoButton, &QPushButton::clicked, this, [this] { saveOctoprintUrl(); });
        layout->addWidget(saveOctoButton);

        auto *loadSpoolsButton = new QPushButton("load current spools", this);
        connect(loadSpoolsButton, &QPushButton::clicked, this, [this] { loadCurrentSpools(); });
        layout->addWidget(loadSpoolsButton);

        octoprintError = new QLabel("", this);
        octoprintError->setWordWrap(true);
        octoprintError->setMaximumWidth(MAX_WIDTH);
        layout->addWidget(octoprintError);

        if (modePostProcessor) {
            layout->addWidget(new QLabel(QString("Number of extruders in gcode: %1").arg(jsonData.size()), this));
        }

        auto *dataBoxes = new QWidget(this);
        dataBoxes->setLayout(layout);
        dataBoxes->setFixedHeight(375);
        widget->addWidget(dataBoxes);
    }

    void setupDataBox() {
        dataBox = new QVBoxLayout();
        dataBox->setSpacing(5);
        widget->addLayout(dataBox);
        auto *saveButton = new QPushButton("Save data", this);
        connect(saveButton, &QPushButton::clicked, this, [this, saveButton] {
            saveButtonClick(saveButton);
        });
        widget->addWidget(saveButton);
    }

    void updateDisplayData() {
        while (QLayoutItem *item = dataBox->takeAt(0)) {
            if (QWidget *w = item->widget()) {
                w->deleteLater();
            }
            delete item;
        }

        for (const QString &key : jsonData.keys()) {
            auto *rowLayout = new QHBoxLayout();
            rowLayout->addWidget(new QLabel("Extruder " + key + ":", this));
            auto *spoolField = new QLineEdit(jsonData.value(key).toObject().value("sm_name").toString(), this);
            rowLayout->addWidget(spoolField);
            auto *removeButton = new QPushButton("Remove", this);
            connect(removeButton, &QPushButton::clicked, this, [this, key] {
                jsonData.remove(key);
                updateDisplayData();
            });
            rowLayout->addWidget(removeButton);

            auto *row = new QWidget(this);
            row->setLayout(rowLayout);
            row->setStyleSheet("border: 1px solid black;");
            row->setFixedHeight(54);
            row->setProperty("extruderKey", key);
            dataBox->addWidget(row);
        }

        auto *addButton = new QPushButton("Add", this);
        connect(addButton, &QPushButton::clicked, this, [this] {
            jsonData[QString::number(jsonData.size() + 1)] = QJsonObject{{"sm_name", ""}};
            updateDisplayData();
        });
        dataBox->addWidget(addButton);
        adjustSize();
    }

    void readCurrentSpools() {
        for (int i = 0; i < dataBox->count(); ++i) {
            QWidget *row = dataBox->itemAt(i)->widget();
            if (!row || !row->property("extruderKey").isValid()) {
                continue;
            }
            QString key = row->property("extruderKey").toString();
            auto fields = row->findChildren<QLineEdit *>();
            if (!fields.isEmpty()) {
                jsonData[key] = QJsonObject{{"sm_name", fields.first()->text()}};
            }
        }
    }

    void saveData() {
        readCurrentSpools();
        settings["octoprint_url"] = octoprintUrlField->text();
        settings["octoprint_api_key"] = octoprintApiKeyField->text();
        settings["spool_data"] = jsonData;
    }

    void saveButtonClick(QPushButton *button) {
        saveData();
        if (jsonData.isEmpty()) {
            button->setText("No data to save");
            QTimer::singleShot(10000, button, [button] { button->setText("Save Data"); });
            return;
        }
        saveSettings(settings);
        button->setText("Data saved successfully");
        QTimer::singleShot(2000, button, [button] { button->setText("Save Data"); });
    }

    void saveOctoprintUrl() {
        loadCurrentSpools();
        if (!octoprintError->text().isEmpty()) {
            return;
        }
        settings["octoprint_url"] = octoprintUrlField->text();
        settings["octoprint_api_key"] = octoprintApiKeyField->text();
        saveSettings(settings);
        octoprintError->setText("Octoprint settings saved successfully");
    }

    void loadCurrentSpools() {
        QByteArray url = octoprintUrlField->text().toUtf8();
        QByteArray key = octoprintApiKeyField->text().toUtf8();
        RustResponse response = callRust(nvf_rust_get_loaded_spools(url.constData(), key.constData()));
        if (!response.ok) {
            octoprintError->setText(response.error);
            return;
        }
        QJsonArray spools = response.data.value("spools").toArray();
        jsonData = {};
        for (int i = 0; i < spools.size(); ++i) {
            jsonData[QString::number(i + 1)] = QJsonObject{{"sm_name", spools.at(i).toString()}};
        }
        octoprintError->setText("");
        updateDisplayData();
    }

    void pickFileButtonClick() {
        QString fileName = QFileDialog::getOpenFileName(this, "Select the data json file", QDir::homePath(),
                                                        "Gcode Files (*.gcode)");
        if (fileName.isEmpty()) {
            return;
        }
        QByteArray path = fileName.toUtf8();
        RustResponse response = callRust(nvf_rust_get_spools_from_gcode(path.constData()));
        if (!response.ok || response.data.value("spool_data").toObject().isEmpty()) {
            octoprintError->setText("Could not load the spools, file may not have been sliced correctly");
            QTimer::singleShot(5000, octoprintError, [this] { octoprintError->setText(""); });
            return;
        }
        gcodePath = fileName;
        filePathLabel->setText("Gcode file path: " + gcodePath);
        jsonData = response.data.value("spool_data").toObject();
        updateDisplayData();
    }

    void editGcode() {
        saveData();
        if (gcodePath.isEmpty()) {
            octoprintError->setText("No Gcode file selected");
            QTimer::singleShot(5000, octoprintError, [this] { octoprintError->setText(""); });
            return;
        }
        processGcode();
    }

    void continuePrintClick() {
        saveData();
        processGcode();
        if (octoprintError->text() == "Gcode updated successfully") {
            close();
        }
    }

    void processGcode() {
        QByteArray path = gcodePath.toUtf8();
        QByteArray data = QJsonDocument(jsonData).toJson(QJsonDocument::Compact);
        RustResponse response = callRust(nvf_rust_process_gcode(path.constData(), data.constData()));
        octoprintError->setText(response.ok ? "Gcode updated successfully" : response.error);
        QTimer::singleShot(5000, octoprintError, [this] { octoprintError->setText(""); });
    }
};

extern "C" int run_qt_app(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setStyleSheet(R"(
        QMainWindow { background-color: #333233; }
        QPushButton {
            background-color: #01274f;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
        }
        QPushButton:hover { background-color: #01172e; }
        QLineEdit {
            background-color: #333233;
            border: 1px solid #FFFFFF;
            border-radius: 5px;
            color: #FFF;
            padding: 5px;
        }
        QLabel { color: #FFF; }
    )");
    app.setWindowIcon(appIcon());
    QApplication::setApplicationName("Nozzle Filament Validator Post-Processor");
    QApplication::setApplicationDisplayName("Nozzle Filament Validator Post-Processor");

    QStringList args = app.arguments();
    bool postProcessorMode = args.size() > 1;
    MainWindow window(postProcessorMode, postProcessorMode ? args.at(1) : QString());
    window.show();
    return app.exec();
}
