use windows::Win32::UI::Input::KeyboardAndMouse::{
    RegisterHotKey, UnregisterHotKey, MOD_ALT, MOD_CONTROL,
};
use windows::Win32::UI::WindowsAndMessaging::{GetMessageW, MSG, WM_HOTKEY};
use windows::Win32::Foundation::HWND;

const HOTKEY_LISTEN: i32 = 1;    // Ctrl+Alt+L
const HOTKEY_INBOX: i32 = 2;     // Ctrl+Alt+I
const HOTKEY_MEETINGS: i32 = 3;  // Ctrl+Alt+M

const VK_L: u32 = 0x4C;
const VK_I: u32 = 0x49;
const VK_M: u32 = 0x4D;

pub fn run() {
    unsafe {
        let hwnd = HWND(0);  // thread message queue
        let modifiers = MOD_CONTROL | MOD_ALT;

        RegisterHotKey(hwnd, HOTKEY_LISTEN, modifiers, VK_L).ok();
        RegisterHotKey(hwnd, HOTKEY_INBOX, modifiers, VK_I).ok();
        RegisterHotKey(hwnd, HOTKEY_MEETINGS, modifiers, VK_M).ok();

        let mut msg = MSG::default();
        while GetMessageW(&mut msg, hwnd, 0, 0).as_bool() {
            if msg.message == WM_HOTKEY {
                let action = match msg.wParam.0 as i32 {
                    HOTKEY_LISTEN => "listen",
                    HOTKEY_INBOX => "inbox",
                    HOTKEY_MEETINGS => "meetings",
                    _ => "unknown",
                };
                super::emit_event(action);
            }
        }

        UnregisterHotKey(hwnd, HOTKEY_LISTEN).ok();
        UnregisterHotKey(hwnd, HOTKEY_INBOX).ok();
        UnregisterHotKey(hwnd, HOTKEY_MEETINGS).ok();
    }
}
