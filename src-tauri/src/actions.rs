use serde::{Deserialize, Serialize};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Action {
    pub action_id: String,
    pub task_id: String,
    pub frame_id: String,
    pub kind: String,
    pub x: f64,
    pub y: f64,
    #[serde(default)]
    pub label: String,
}
impl Action {
    pub fn validate(&self, task: &str, frame: &str) -> Result<(), String> {
        if self.action_id.is_empty()
            || self.action_id.len() > 100
            || self.task_id != task
            || self.frame_id != frame
        {
            return Err("Action belongs to an old task or screen frame. Session stopped.".into());
        }
        if !matches!(self.kind.as_str(), "move" | "click")
            || !self.x.is_finite()
            || !self.y.is_finite()
            || !(0.0..=1.0).contains(&self.x)
            || !(0.0..=1.0).contains(&self.y)
            || self.label.len() > 200
        {
            return Err("Invalid pointer action. Session stopped.".into());
        }
        Ok(())
    }
}
#[derive(Clone, Serialize)]
pub struct Pointer {
    pub x: f64,
    pub y: f64,
    pub kind: String,
    pub label: String,
    pub mode: String,
}
#[cfg(test)]
mod tests {
    use super::*;
    fn action() -> Action {
        Action {
            action_id: "one".into(),
            task_id: "task".into(),
            frame_id: "frame".into(),
            kind: "click".into(),
            x: 0.5,
            y: 0.5,
            label: "Click here".into(),
        }
    }
    #[test]
    fn accepts_normalized_targets() {
        assert!(action().validate("task", "frame").is_ok());
    }
    #[test]
    fn rejects_stale_outside_and_nonfinite() {
        let mut a = action();
        assert!(a.validate("old", "frame").is_err());
        assert!(a.validate("task", "old").is_err());
        a.x = 1.1;
        assert!(a.validate("task", "frame").is_err());
        a.x = f64::NAN;
        assert!(a.validate("task", "frame").is_err());
        a.x = 0.5;
        a.kind = "shell".into();
        assert!(a.validate("task", "frame").is_err());
    }
}
