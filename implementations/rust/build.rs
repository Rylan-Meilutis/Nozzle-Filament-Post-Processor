use image::imageops::FilterType;
use image::{ImageBuffer, Rgba, RgbaImage};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let source = PathBuf::from("../python/icon.png");
    println!("cargo:rerun-if-changed={}", source.display());

    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR must be set"));
    let image = make_app_icon(&source, 256);
    fs::write(out_dir.join("icon.rgba"), image.as_raw()).expect("failed to write icon.rgba");
    fs::write(
        out_dir.join("icon_meta.rs"),
        "const ICON_WIDTH: u32 = 256;\nconst ICON_HEIGHT: u32 = 256;\n",
    )
    .expect("failed to write icon metadata");
    write_cpp_icon_header(&source, out_dir.join("icon_png.h"));

    build_qt_frontend(&out_dir);
}

fn write_cpp_icon_header(source: &PathBuf, output: PathBuf) {
    let icon = make_app_icon(source, 512);
    let mut cursor = std::io::Cursor::new(Vec::new());
    icon.write_to(&mut cursor, image::ImageFormat::Png)
        .expect("failed to encode embedded icon png");
    let bytes = cursor.into_inner();
    let mut header = String::from("#pragma once\nstatic const unsigned char NVF_ICON_PNG[] = {\n");
    for chunk in bytes.chunks(12) {
        header.push_str("    ");
        for byte in chunk {
            header.push_str(&format!("0x{byte:02x}, "));
        }
        header.push('\n');
    }
    header.push_str("};\nstatic const unsigned int NVF_ICON_PNG_LEN = sizeof(NVF_ICON_PNG);\n");
    fs::write(output, header).expect("failed to write icon_png.h");
}

fn make_app_icon(source: &PathBuf, size: u32) -> RgbaImage {
    let source = image::open(source)
        .expect("failed to read icon.png")
        .resize_to_fill(size, size, FilterType::Lanczos3)
        .into_rgba8();
    let radius = size as f32 * 0.225;
    let mut out: RgbaImage = ImageBuffer::from_pixel(size, size, Rgba([0, 0, 0, 0]));

    for y in 0..size {
        for x in 0..size {
            if rounded_rect_alpha(x, y, size, radius) > 0 {
                out.put_pixel(x, y, *source.get_pixel(x, y));
            }
        }
    }
    out
}

fn rounded_rect_alpha(x: u32, y: u32, size: u32, radius: f32) -> u8 {
    let max = size as f32 - 1.0;
    let xf = x as f32;
    let yf = y as f32;
    let cx = if xf < radius {
        radius
    } else if xf > max - radius {
        max - radius
    } else {
        xf
    };
    let cy = if yf < radius {
        radius
    } else if yf > max - radius {
        max - radius
    } else {
        yf
    };
    let dx = xf - cx;
    let dy = yf - cy;
    if dx * dx + dy * dy <= radius * radius {
        255
    } else {
        0
    }
}

fn build_qt_frontend(out_dir: &PathBuf) {
    println!("cargo:rerun-if-changed=src/qt_frontend.cpp");

    let cflags = pkg_config_words("--cflags");
    let libs = pkg_config_words("--libs");
    let mut build = cc::Build::new();
    build
        .cpp(true)
        .file("src/qt_frontend.cpp")
        .include(out_dir)
        .flag("-std=c++17");

    for flag in cflags {
        if let Some(include) = flag.strip_prefix("-I") {
            build.include(include);
        } else {
            build.flag(&flag);
        }
    }
    build.compile("qt_frontend");

    let mut pending_framework = false;
    for lib in libs {
        if let Some(path) = lib.strip_prefix("-F") {
            println!("cargo:rustc-link-search=framework={path}");
        } else if let Some(path) = lib.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={path}");
        } else if let Some(name) = lib.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={name}");
        } else if lib == "-framework" {
            pending_framework = true;
        } else if pending_framework {
            println!("cargo:rustc-link-lib=framework={lib}");
            pending_framework = false;
        }
    }
}

fn pkg_config_words(arg: &str) -> Vec<String> {
    let output = Command::new("pkg-config")
        .args([arg, "Qt6Widgets", "Qt6Gui", "Qt6Core"])
        .output()
        .expect("failed to run pkg-config for Qt6");
    if !output.status.success() {
        panic!(
            "pkg-config could not find Qt6 Widgets: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    String::from_utf8(output.stdout)
        .expect("pkg-config output must be utf-8")
        .split_whitespace()
        .map(ToOwned::to_owned)
        .collect()
}
