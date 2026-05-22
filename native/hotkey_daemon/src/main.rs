/// Non-intercepting global hotkey daemon.
/// On Windows: uses RegisterHotKey WinAPI — the OS delivers WM_HOTKEY to this process
/// without blocking the key from reaching screen readers or other applications.
/// Emits events to stdout (JSON lines) consumed by the Python service.

use std::io::{self, Write};

#[cfg(target_os = "windows")]
mod windows_impl;

fn main() {
    #[cfg(target_os = "windows")]
    windows_impl::run();

    #[cfg(not(target_os = "windows"))]
    eprintln!("hotkey_daemon: unsupported platform");
}

/// Writes a hotkey event as JSON to stdout for the Python host to consume.
pub fn emit_event(action: &str) {
    let line = format!("{{\"action\":\"{}\"}}\n", action);
    let stdout = io::stdout();
    let mut handle = stdout.lock();
    let _ = handle.write_all(line.as_bytes());
    let _ = handle.flush();
}
