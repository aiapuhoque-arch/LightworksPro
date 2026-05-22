/// Windows WASAPI audio ducking via IAudioSessionManager2.
/// Identifies all active audio sessions, skips screen reader processes
/// (JAWS, NVDA, ZoomText, Fusion), and lowers their ISimpleAudioVolume.

use std::sync::Mutex;
use std::collections::HashMap;

// Process names belonging to AT software — never touch these.
const AT_PROCESSES: &[&str] = &["jfw.exe", "nvda.exe", "zoomtext.exe", "fusion.exe"];

static SAVED_VOLUMES: Mutex<Option<HashMap<u32, f32>>> = Mutex::new(None);

pub fn duck(target_volume: f32) -> i32 {
    let target = target_volume.clamp(0.0, 1.0);
    let sessions = match enumerate_audio_sessions() {
        Ok(s) => s,
        Err(_) => return -1,
    };

    let mut saved = HashMap::new();
    for session in &sessions {
        if is_at_process(session.process_name.as_str()) {
            continue;
        }
        saved.insert(session.pid, session.volume);
        let _ = set_session_volume(session.pid, target);
    }

    *SAVED_VOLUMES.lock().unwrap() = Some(saved);
    0
}

pub fn unduck() -> i32 {
    let guard = SAVED_VOLUMES.lock().unwrap();
    if let Some(ref volumes) = *guard {
        for (&pid, &vol) in volumes {
            let _ = set_session_volume(pid, vol);
        }
    }
    drop(guard);
    *SAVED_VOLUMES.lock().unwrap() = None;
    0
}

struct AudioSession {
    pid: u32,
    process_name: String,
    volume: f32,
}

fn is_at_process(name: &str) -> bool {
    let lower = name.to_lowercase();
    AT_PROCESSES.iter().any(|&at| lower.contains(at))
}

fn enumerate_audio_sessions() -> Result<Vec<AudioSession>, ()> {
    // Real implementation uses windows-rs crate:
    //   IAudioSessionManager2::GetSessionEnumerator → IAudioSessionControl2
    //   ISimpleAudioVolume::GetMasterVolume
    // Stub returns empty — fill in with windows-rs bindings.
    Ok(vec![])
}

fn set_session_volume(pid: u32, volume: f32) -> Result<(), ()> {
    // Real implementation:
    //   Find session by PID via IAudioSessionControl2::GetProcessId
    //   ISimpleAudioVolume::SetMasterVolume(volume, null)
    let _ = (pid, volume);
    Ok(())
}
