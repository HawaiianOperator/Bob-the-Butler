//! Bounded browser/keyboard tools. The model never supplies an executable or shell command.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub tool: String,
    pub args: Value,
}
impl Plan {
    pub fn validate(&self) -> Result<(), String> {
        let key = match self.tool.as_str() {
            "launch_chrome" => Some("url"),
            "hotkey" => Some("keys"),
            "type_text" => Some("text"),
            "press_key" => Some("key"),
            "done" => Some("message"),
            "ask" => Some("question"),
            "observe" => None,
            _ => return Err("Unknown planner tool.".into()),
        };
        let args = self.args.as_object().ok_or("Invalid planner arguments.")?;
        if args.len() != usize::from(key.is_some()) {
            return Err("Unexpected planner arguments.".into());
        }
        if let Some(key) = key {
            let value = args
                .get(key)
                .and_then(Value::as_str)
                .ok_or("Invalid planner argument.")?;
            if value.is_empty()
                || value.chars().count() > 256
                || value.chars().any(char::is_control)
            {
                return Err("Invalid planner argument length or characters.".into());
            }
            match self.tool.as_str() {
                "hotkey" if !matches!(value, "ctrl+l" | "ctrl+t" | "ctrl+a") => {
                    return Err("Unsupported shortcut.".into())
                }
                "press_key"
                    if !matches!(
                        value,
                        "enter" | "tab" | "esc" | "backspace" | "up" | "down" | "left" | "right"
                    ) =>
                {
                    return Err("Unsupported key.".into())
                }
                "type_text" if !value.bytes().all(|b| (32..127).contains(&b)) => {
                    return Err("Only printable ASCII text is supported.".into())
                }
                "launch_chrome" => {
                    let url = tauri::Url::parse(value).map_err(|_| "Invalid browser URL.")?;
                    if !matches!(url.scheme(), "http" | "https")
                        || url.host_str().is_none()
                        || !url.username().is_empty()
                        || url.password().is_some()
                    {
                        return Err("Only normal HTTP(S) browser URLs are allowed.".into());
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }
    pub fn instruction(&self) -> String {
        match self.tool.as_str() {
            "launch_chrome" => {
                format!("Open Chrome at {}", self.args["url"].as_str().unwrap_or(""))
            }
            "hotkey" => format!("Press {}", self.args["keys"].as_str().unwrap_or("")),
            "type_text" => format!("Type: {}", self.args["text"].as_str().unwrap_or("")),
            "press_key" => format!("Press {}", self.args["key"].as_str().unwrap_or("")),
            "done" => self.args["message"].as_str().unwrap_or("").into(),
            "ask" => self.args["question"].as_str().unwrap_or("").into(),
            _ => "Checking Chrome…".into(),
        }
    }
}

#[derive(Default)]
pub struct BrowserState {
    pub focused: bool,
    pub text: Option<String>,
    pub submitted: bool,
    pub before_submit: String,
    pub search_requested: bool,
}
impl BrowserState {
    pub fn for_goal(goal: &str) -> Self {
        let goal = goal.to_lowercase();
        Self {
            search_requested: ["search", "serch", "stock", "price", "look up", "find"]
                .iter()
                .any(|word| goal.contains(word)),
            ..Self::default()
        }
    }
    pub fn search_result_verified(&self, title: &str) -> bool {
        if !self.search_requested {
            return !title.trim().is_empty() && !self.focused;
        }
        self.submitted
            && !self.focused
            && self.text.as_ref().is_some_and(|query| {
                !query.trim().is_empty()
                    && title.to_lowercase().contains(&query.to_lowercase())
                    && title != self.before_submit.as_str()
            })
    }
    pub fn observation(&self) -> Value {
        let (available, foreground, title) = browser_window();
        if !available {
            return json!({"chrome":"unavailable","active_window":"other"});
        }
        if !foreground {
            return json!({"chrome":"closed"});
        }
        let mut obs = json!({"chrome":"ready","active_window":"Chrome"});
        if self.submitted {
            let loading = title.is_empty() || title == self.before_submit;
            obs["page_loading"] = json!(loading);
            if !loading {
                obs["page_title"] = json!(title.strip_suffix(" - Google Chrome").unwrap_or(&title));
            }
        } else {
            obs["address_bar_focused"] = json!(self.focused);
        }
        if foreground && self.focused {
            if let Some(text) = &self.text {
                obs["address_bar_text"] = json!(text);
            }
        }
        obs
    }
    pub fn record(&mut self, plan: &Plan, ok: bool) {
        if !ok {
            self.focused = false;
            self.text = None;
            return;
        }
        match plan.tool.as_str() {
            "launch_chrome" => {
                self.focused = false;
                self.text = None;
                self.submitted = false;
            }
            "hotkey" if matches!(plan.args["keys"].as_str(), Some("ctrl+l" | "ctrl+t")) => {
                self.focused = true;
                self.text = None;
                self.submitted = false;
            }
            "type_text" => self.text = plan.args["text"].as_str().map(str::to_string),
            "press_key" => {
                if plan.args["key"] == "enter" && self.focused {
                    self.submitted = true;
                }
                self.focused = false;
            }
            _ => {}
        }
    }
}

#[cfg(windows)]
fn chrome_path() -> Option<std::path::PathBuf> {
    ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]
        .iter()
        .filter_map(std::env::var_os)
        .map(|p| std::path::PathBuf::from(p).join("Google/Chrome/Application/chrome.exe"))
        .find(|p| p.is_file())
}
#[cfg(windows)]
pub fn browser_window() -> (bool, bool, String) {
    use windows_sys::Win32::{System::Threading::*, UI::WindowsAndMessaging::*};
    unsafe {
        let window = GetForegroundWindow();
        let mut pid = 0;
        GetWindowThreadProcessId(window, &mut pid);
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        let mut path = [0u16; 1024];
        let mut size = path.len() as u32;
        let chrome = !process.is_null()
            && QueryFullProcessImageNameW(process, 0, path.as_mut_ptr(), &mut size) != 0
            && String::from_utf16_lossy(&path[..size as usize])
                .to_ascii_lowercase()
                .ends_with("\\chrome.exe");
        if !process.is_null() {
            windows_sys::Win32::Foundation::CloseHandle(process);
        }
        let mut title = [0u16; 512];
        let n = if chrome {
            GetWindowTextW(window, title.as_mut_ptr(), 512).max(0) as usize
        } else {
            0
        };
        (
            chrome_path().is_some(),
            chrome,
            String::from_utf16_lossy(&title[..n]),
        )
    }
}
#[cfg(not(windows))]
pub fn browser_window() -> (bool, bool, String) {
    (false, false, String::new())
}

pub fn execute(plan: &Plan, allowed: impl Fn() -> bool) -> Result<(), String> {
    plan.validate()?;
    if !allowed() {
        return Err("Planner action cancelled.".into());
    }
    #[cfg(windows)]
    if plan.tool == "launch_chrome" {
        std::process::Command::new(chrome_path().ok_or("Chrome is not installed.")?)
            .args(["--new-window", plan.args["url"].as_str().unwrap()])
            .spawn()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    if !browser_window().1 {
        return Err("Chrome must be the foreground application. Session stopped.".into());
    }
    crate::input::keyboard(&plan.tool, &plan.args, || allowed() && browser_window().1)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn google_homepage_is_not_a_completed_search() {
        let mut browser = BrowserState::for_goal("search for NVIDIA stock");
        assert!(!browser.search_result_verified("Google - Google Chrome"));
        browser.text = Some("Nvidia stock".into());
        browser.submitted = true;
        browser.before_submit = "Google - Google Chrome".into();
        assert!(!browser.search_result_verified("Google - Google Chrome"));
        assert!(!browser.search_result_verified("Intel stock - Google Search"));
        assert!(browser.search_result_verified("NVIDIA stock - Google Search - Google Chrome"));
        assert!(
            BrowserState::for_goal("open Chrome").search_result_verified("Google - Google Chrome")
        );
    }
    #[test]
    fn rejects_arbitrary_commands_and_extra_arguments() {
        for (tool, args) in [
            ("shell", json!({"text":"dir"})),
            ("hotkey", json!({"keys":"alt+f4"})),
            ("launch_chrome", json!({"url":"file:///C:/test"})),
            ("type_text", json!({"text":"a", "extra":true})),
        ] {
            assert!(Plan {
                tool: tool.into(),
                args
            }
            .validate()
            .is_err());
        }
        assert!(Plan {
            tool: "type_text".into(),
            args: json!({"text":"NVIDIA stock"})
        }
        .validate()
        .is_ok());
    }
}
