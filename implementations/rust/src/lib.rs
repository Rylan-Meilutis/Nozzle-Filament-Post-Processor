use anyhow::{Context, Result, bail};
use regex::Regex;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use url::Url;

const TAIL_LINES: usize = 1000;
const CHUNK_SIZE: u64 = 8192;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Settings {
    #[serde(default)]
    pub octoprint_url: Option<String>,
    #[serde(default)]
    pub octoprint_api_key: Option<String>,
    #[serde(rename = "settings version", default = "settings_version")]
    pub settings_version: u8,
    #[serde(default)]
    pub spool_data: BTreeMap<String, SpoolData>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SpoolData {
    pub sm_name: String,
}

fn settings_version() -> u8 {
    1
}

pub fn settings_paths(exe_dir: &Path) -> (PathBuf, PathBuf) {
    (
        exe_dir.join("nfvsettings.json"),
        exe_dir.join("nvfsettings.json"),
    )
}

pub fn load_settings(exe_dir: &Path) -> Settings {
    let (settings_path, legacy_path) = settings_paths(exe_dir);
    for path in [settings_path, legacy_path] {
        if !path.is_file() {
            continue;
        }
        if let Ok(contents) = fs::read_to_string(path) {
            if let Ok(settings) = serde_json::from_str::<Settings>(&contents) {
                return settings;
            }
        }
    }
    Settings::default()
}

pub fn save_settings(exe_dir: &Path, settings: &Settings) -> Result<()> {
    let (settings_path, _) = settings_paths(exe_dir);
    let mut out = settings.clone();
    out.settings_version = 1;
    let contents = serde_json::to_string_pretty(&out)?;
    fs::write(settings_path, contents).context("failed to write settings")
}

pub fn parse_spool_names(value: &Value) -> Result<Vec<Option<String>>> {
    let object = value
        .as_object()
        .context("settings JSON must be an object keyed by extruder number")?;
    let mut out = vec![None; object.len()];
    for (key, value) in object {
        let index = key
            .parse::<usize>()
            .with_context(|| format!("invalid extruder key `{key}`"))?;
        if index == 0 {
            bail!("extruder keys must start at 1");
        }
        if index > out.len() {
            out.resize(index, None);
        }
        out[index - 1] = value
            .get("sm_name")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned);
    }
    Ok(out)
}

pub fn load_spool_names_from_file(path: &Path) -> Result<Vec<Option<String>>> {
    let contents =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    let value: Value = serde_json::from_str(&contents)
        .with_context(|| format!("failed to parse {}", path.display()))?;
    parse_spool_names(&value)
}

pub fn process_gcode_file(gcode_path: &Path, spool_names: &[Option<String>]) -> Result<()> {
    let tail = parse_gcode_tail(gcode_path)?;
    let new_tail = replace_names(&tail, spool_names)?;
    replace_gcode_tail(gcode_path, &new_tail)
}

pub fn parse_gcode_tail(gcode_path: &Path) -> Result<String> {
    let (tail, _) = read_gcode_tail(gcode_path, TAIL_LINES)?;
    Ok(String::from_utf8_lossy(&tail).into_owned())
}

pub fn read_gcode_tail(gcode_path: &Path, num_lines: usize) -> Result<(Vec<u8>, u64)> {
    let mut file = File::open(gcode_path)
        .with_context(|| format!("failed to open {}", gcode_path.display()))?;
    let mut pos = file.seek(SeekFrom::End(0))?;
    let mut chunks = Vec::new();
    let mut newline_count = 0usize;

    while pos > 0 && newline_count <= num_lines {
        let read_size = CHUNK_SIZE.min(pos);
        pos -= read_size;
        file.seek(SeekFrom::Start(pos))?;
        let mut chunk = vec![0; read_size as usize];
        file.read_exact(&mut chunk)?;
        newline_count += bytecount_newlines(&chunk);
        chunks.push(chunk);
    }

    chunks.reverse();
    let tail: Vec<u8> = chunks.into_iter().flatten().collect();
    let mut starts = Vec::new();
    starts.push(0usize);
    for (idx, byte) in tail.iter().enumerate() {
        if *byte == b'\n' && idx + 1 < tail.len() {
            starts.push(idx + 1);
        }
    }
    let start_index = starts
        .get(starts.len().saturating_sub(num_lines))
        .copied()
        .unwrap_or(0);
    let tail_bytes = tail[start_index..].to_vec();
    let tail_start = pos + start_index as u64;
    Ok((tail_bytes, tail_start))
}

fn bytecount_newlines(bytes: &[u8]) -> usize {
    bytes.iter().filter(|byte| **byte == b'\n').count()
}

pub fn replace_gcode_tail(gcode_path: &Path, new_tail: &str) -> Result<()> {
    let (_, tail_start) = read_gcode_tail(gcode_path, TAIL_LINES)?;
    let directory = gcode_path.parent().unwrap_or_else(|| Path::new("."));
    let mut source = File::open(gcode_path)?;
    let mut first_line = Vec::new();
    for byte in std::io::Read::by_ref(&mut source).bytes() {
        let byte = byte?;
        first_line.push(byte);
        if byte == b'\n' {
            break;
        }
    }
    let has_header = first_line.starts_with(b"; Edited with NVF Postprocessor");
    source.seek(SeekFrom::Start(0))?;

    let mut temp = tempfile::NamedTempFile::new_in(directory)?;
    if !has_header {
        temp.write_all(b"; Edited with NVF Postprocessor\n")?;
    }

    let mut remaining = tail_start;
    let mut buffer = vec![0; CHUNK_SIZE as usize];
    while remaining > 0 {
        let read_size = (buffer.len() as u64).min(remaining) as usize;
        let bytes_read = source.read(&mut buffer[..read_size])?;
        if bytes_read == 0 {
            break;
        }
        temp.write_all(&buffer[..bytes_read])?;
        remaining -= bytes_read as u64;
    }
    temp.write_all(new_tail.as_bytes())?;
    temp.persist(gcode_path)
        .map_err(|err| anyhow::anyhow!(err.error))
        .context("failed to replace G-code file")?;
    Ok(())
}

pub fn replace_names(gcode: &str, spool_names: &[Option<String>]) -> Result<String> {
    let filament_notes_re = Regex::new(r"; filament_notes = (.+)")?;
    let filament_type_re = Regex::new(r"; filament_type = (.+)")?;
    let filament_used_re = Regex::new(r"; filament used \[mm] = (.+)")?;
    let sm_name_re = Regex::new(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]")?;

    let Some(notes_match) = filament_notes_re.find(gcode) else {
        return Ok(gcode.to_owned());
    };
    let Some(notes_capture) = filament_notes_re.captures(gcode) else {
        return Ok(gcode.to_owned());
    };
    let Some(notes_value) = notes_capture.get(1) else {
        return Ok(gcode.to_owned());
    };
    let filament_notes: Vec<&str> = notes_value.as_str().trim().split(';').collect();

    let num_filaments = filament_type_re
        .captures(gcode)
        .and_then(|captures| {
            captures
                .get(1)
                .map(|value| value.as_str().trim().split(';').count())
        })
        .unwrap_or(0);

    let mut out = gcode.to_owned();
    if let Some(used_capture) = filament_used_re.captures(gcode) {
        if let Some(used_value) = used_capture.get(1) {
            let mut filament_used: Vec<String> = used_value
                .as_str()
                .trim()
                .split(',')
                .map(|value| value.trim().to_owned())
                .collect();
            if filament_used.len() < num_filaments {
                filament_used.resize(num_filaments, "0".to_owned());
                out = filament_used_re
                    .replace(
                        &out,
                        format!("; filament used [mm] = {}", filament_used.join(", ")),
                    )
                    .into_owned();
            }
        }
    }

    let original_line = notes_match.as_str();
    let mut new_parts: Vec<String> = original_line[1..]
        .split(';')
        .map(ToOwned::to_owned)
        .collect();

    for (idx, note) in filament_notes.iter().enumerate() {
        let Some(Some(spool_name)) = spool_names.get(idx) else {
            continue;
        };
        if sm_name_re.is_match(note) {
            let replacement = sm_name_re
                .replace(note, format!("[sm_name = {spool_name}]"))
                .into_owned();
            new_parts[idx] = new_parts[idx].replace(note, &replacement);
        }
    }

    let new_line = format!(";{}", new_parts.join("; "));
    Ok(out.replace(original_line, &new_line))
}

pub fn get_spools_from_gcode(gcode_path: &Path) -> Result<BTreeMap<String, SpoolData>> {
    let gcode = parse_gcode_tail(gcode_path)?;
    let notes_re = Regex::new(r"; filament_notes = (.+)")?;
    let sm_name_re = Regex::new(r"\[\s*sm_name\s*=\s*([^]]*\S)?\s*]")?;
    let Some(captures) = notes_re.captures(&gcode) else {
        return Ok(BTreeMap::new());
    };
    let notes = captures
        .get(1)
        .map(|value| value.as_str().trim())
        .unwrap_or_default();
    if notes == "\"\"" || notes.is_empty() {
        return Ok(BTreeMap::new());
    }
    let mut spools = BTreeMap::new();
    for (idx, note) in notes.split(';').enumerate() {
        let name = sm_name_re
            .captures(note)
            .and_then(|captures| captures.get(1).map(|value| value.as_str().to_owned()))
            .unwrap_or_default();
        spools.insert((idx + 1).to_string(), SpoolData { sm_name: name });
    }
    Ok(spools)
}

pub fn count_editable_extruders(gcode_path: &Path) -> Result<usize> {
    let spools = get_spools_from_gcode(gcode_path)?;
    Ok(spools.len())
}

pub fn settings_to_spool_names(settings: &Settings) -> Vec<Option<String>> {
    let mut value = Map::new();
    for (key, spool) in &settings.spool_data {
        value.insert(key.clone(), json!({ "sm_name": spool.sm_name }));
    }
    parse_spool_names(&Value::Object(value)).unwrap_or_default()
}

pub fn get_loaded_spools(url: &str, api_key: Option<&str>) -> Result<Vec<String>, String> {
    if url.trim().is_empty() {
        return Err("No OctoPrint URL saved".to_owned());
    }
    let base = Url::parse(&(url.trim_end_matches('/').to_owned() + "/"))
        .map_err(|err| format!("Invalid OctoPrint URL: {err}"))?;
    let request_url = base
        .join("plugin/SpoolManager/loadSpoolsByQuery")
        .map_err(|err| format!("Invalid OctoPrint URL: {err}"))?;
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|err| format!("Could not create HTTP client: {err}"))?;
    let mut request = client.get(request_url).query(&[
        ("selectedPageSize", "100000"),
        ("from", "0"),
        ("to", "100000"),
        ("sortColumn", "displayName"),
        ("sortOrder", "desc"),
        ("filterName", ""),
        ("materialFilter", "all"),
        ("vendorFilter", "all"),
        ("colorFilter", "all"),
    ]);
    if let Some(api_key) = api_key.filter(|value| !value.trim().is_empty()) {
        request = request.header("X-Api-Key", api_key.trim());
    }
    let response = request
        .send()
        .map_err(|err| format!("Could not connect to OctoPrint: {err}"))?;
    let status = response.status();
    if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
        return Err(format!(
            "Could not load the spools from OctoPrint: HTTP {status}. Check the OctoPrint API key."
        ));
    }
    if !status.is_success() {
        return Err(format!(
            "Could not load the spools from OctoPrint: HTTP {status}"
        ));
    }
    let value: Value = response.json().map_err(|_| {
        "Could not load the spools from OctoPrint: response was not valid JSON".to_owned()
    })?;
    let selected = value
        .get("selectedSpools")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            let keys = value
                .as_object()
                .map(|object| object.keys().cloned().collect::<Vec<_>>().join(", "))
                .unwrap_or_default();
            format!("Could not load the spools from OctoPrint: missing selectedSpools in response ({keys})")
        })?;
    Ok(selected
        .iter()
        .map(|spool| {
            spool
                .get("displayName")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned()
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn replaces_sm_names_and_pads_filament_used() {
        let gcode = "; filament_type = PLA;PETG;ABS\n; filament used [mm] = 10, 20\n; filament_notes = [sm_name=Old]; [sm_name = ]; [sm_name=Third]\n";
        let names = vec![
            Some("Purple PLA".to_owned()),
            Some("Blue PETG".to_owned()),
            Some("Black ABS".to_owned()),
        ];

        let output = replace_names(gcode, &names).unwrap();

        assert!(output.contains("; filament used [mm] = 10, 20, 0"));
        assert!(output.contains("; filament_notes = [sm_name = Purple PLA];  [sm_name = Blue PETG];  [sm_name = Black ABS]"));
    }

    #[test]
    fn rewrites_tail_without_loading_full_file_contract() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("sample.gcode");
        fs::write(
            &path,
            "G1 X0\n; filament_type = PLA\n; filament used [mm] = 12\n; filament_notes = [sm_name=Old]\n",
        )
        .unwrap();

        process_gcode_file(&path, &[Some("New".to_owned())]).unwrap();
        let output = fs::read_to_string(path).unwrap();

        assert!(output.starts_with("; Edited with NVF Postprocessor\n"));
        assert!(output.contains("; filament_notes = [sm_name = New]"));
    }
}
