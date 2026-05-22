/// Audio Ducking Engine — lowers media application volume while Lightworks Pro speaks,
/// then restores it. Uses Windows WASAPI (IAudioSessionManager2) or macOS CoreAudio.
/// Exposed as a cdecl FFI library so Python ctypes can call `duck()` and `unduck()`.
///
/// IMPORTANT: This code only modifies per-session volumes of non-AT processes.
/// It never touches the master volume or any audio session belonging to screen readers.

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "macos")]
mod macos;

#[no_mangle]
pub extern "C" fn lw_audio_duck(target_volume: f32) -> i32 {
    #[cfg(target_os = "windows")]
    return windows::duck(target_volume);
    #[cfg(target_os = "macos")]
    return macos::duck(target_volume);
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    return 0;
}

#[no_mangle]
pub extern "C" fn lw_audio_unduck() -> i32 {
    #[cfg(target_os = "windows")]
    return windows::unduck();
    #[cfg(target_os = "macos")]
    return macos::unduck();
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    return 0;
}
