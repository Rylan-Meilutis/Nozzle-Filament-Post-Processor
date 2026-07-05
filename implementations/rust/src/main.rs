use anyhow::{Result, bail};
use nvf_postprocessor::{
    get_loaded_spools, get_spools_from_gcode, load_spool_names_from_file, parse_spool_names,
    process_gcode_file,
};
use serde_json::{Value, json};
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int};
use std::path::PathBuf;

unsafe extern "C" {
    fn run_qt_app(argc: c_int, argv: *mut *mut c_char) -> c_int;
}

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.first().map(String::as_str) == Some("--process") {
        if args.len() != 3 {
            bail!("usage: nvf_postprocessor --process <settings-json> <gcode-path>");
        }
        let settings_json = PathBuf::from(args.remove(1));
        let gcode_path = PathBuf::from(args.remove(1));
        let names = load_spool_names_from_file(&settings_json)?;
        process_gcode_file(&gcode_path, &names)?;
        return Ok(());
    }

    let c_args = std::env::args()
        .map(|arg| CString::new(arg).expect("argument contains nul byte"))
        .collect::<Vec<_>>();
    let mut raw_args = c_args
        .iter()
        .map(|arg| arg.as_ptr() as *mut c_char)
        .collect::<Vec<_>>();
    let code = unsafe { run_qt_app(raw_args.len() as c_int, raw_args.as_mut_ptr()) };
    if code == 0 {
        Ok(())
    } else {
        bail!("Qt application exited with code {code}")
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn nvf_rust_free_string(value: *mut c_char) {
    if !value.is_null() {
        unsafe {
            let _ = CString::from_raw(value);
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn nvf_rust_get_spools_from_gcode(path: *const c_char) -> *mut c_char {
    ffi_result(|| {
        let path = ffi_path(path)?;
        let spools = get_spools_from_gcode(&path)?;
        Ok(json!({ "spool_data": spools }))
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn nvf_rust_process_gcode(
    path: *const c_char,
    spool_data_json: *const c_char,
) -> *mut c_char {
    ffi_result(|| {
        let path = ffi_path(path)?;
        let spool_data_json = ffi_string(spool_data_json)?;
        let value: Value = serde_json::from_str(&spool_data_json)?;
        let names = parse_spool_names(&value)?;
        process_gcode_file(&path, &names)?;
        Ok(json!({}))
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn nvf_rust_get_loaded_spools(
    url: *const c_char,
    api_key: *const c_char,
) -> *mut c_char {
    ffi_result_string_error(|| {
        let url = ffi_string(url)?;
        let api_key = ffi_string(api_key).ok();
        let spools = get_loaded_spools(&url, api_key.as_deref()).map_err(anyhow::Error::msg)?;
        Ok(json!({ "spools": spools }))
    })
}

fn ffi_result<F>(operation: F) -> *mut c_char
where
    F: FnOnce() -> anyhow::Result<Value>,
{
    let value = match operation() {
        Ok(value) => json!({ "ok": true, "data": value }),
        Err(err) => json!({ "ok": false, "error": err.to_string() }),
    };
    CString::new(value.to_string()).unwrap().into_raw()
}

fn ffi_result_string_error<F>(operation: F) -> *mut c_char
where
    F: FnOnce() -> anyhow::Result<Value>,
{
    ffi_result(operation)
}

fn ffi_path(value: *const c_char) -> anyhow::Result<PathBuf> {
    Ok(PathBuf::from(ffi_string(value)?))
}

fn ffi_string(value: *const c_char) -> anyhow::Result<String> {
    if value.is_null() {
        bail!("null string pointer");
    }
    Ok(unsafe { CStr::from_ptr(value) }
        .to_string_lossy()
        .into_owned())
}
