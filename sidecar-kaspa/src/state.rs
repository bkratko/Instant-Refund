use std::sync::{Arc, RwLock};

#[derive(Clone, Debug)]
pub struct RuntimeState {
    inner: Arc<RwLock<RuntimeStateInner>>,
}

#[derive(Debug)]
struct RuntimeStateInner {
    pub started_at: std::time::Instant,
    pub from_address: Option<String>,
    pub wallet_bound: bool,
    pub startup_error: Option<String>,
}

impl RuntimeState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(RuntimeStateInner {
                started_at: std::time::Instant::now(),
                from_address: None,
                wallet_bound: false,
                startup_error: None,
            })),
        }
    }

    pub fn set_wallet_ok(&self, from: String) {
        let mut g = self.inner.write().unwrap();
        g.from_address = Some(from);
        g.wallet_bound = true;
        g.startup_error = None;
    }

    pub fn set_wallet_error(&self, err: String) {
        let mut g = self.inner.write().unwrap();
        g.startup_error = Some(err);
        g.wallet_bound = false;
    }

    pub fn wallet_snapshot(&self) -> (Option<String>, bool, Option<String>) {
        let g = self.inner.read().unwrap();
        (g.from_address.clone(), g.wallet_bound, g.startup_error.clone())
    }
}
