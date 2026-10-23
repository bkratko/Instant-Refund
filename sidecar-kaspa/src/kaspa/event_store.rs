use std::{
    fs::OpenOptions,
    io::Write,
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub struct EventStore {
    inner: Arc<Mutex<std::fs::File>>,
}

impl EventStore {
    pub fn open(path: &str) -> std::io::Result<Self> {
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)?;

        Ok(Self {
            inner: Arc::new(Mutex::new(file)),
        })
    }

    pub fn append_json_line(&self, line: &str) -> std::io::Result<()> {
        let mut f = self.inner.lock().expect("event store mutex poisoned");
        writeln!(&mut *f, "{line}")?;
        Ok(())
    }
}
