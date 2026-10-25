use serde::Serialize;
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    time::Duration,
};

pub trait Transport: Read + Write + Send {}
impl<T: Read + Write + Send> Transport for T {}

#[derive(Serialize)]
pub struct Port {
    pub name: String,
    pub label: String,
    pub usb: bool,
}

fn adb_socket() -> Result<TcpStream, String> {
    let address: SocketAddr = "127.0.0.1:5037".parse().unwrap();
    let stream = TcpStream::connect_timeout(&address, Duration::from_millis(300))
        .map_err(|_| "USB ADB is unavailable. Open Arduino App Lab or start the Android platform-tools ADB server.".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|e| e.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_millis(500)))
        .map_err(|e| e.to_string())?;
    Ok(stream)
}

fn adb_request(stream: &mut TcpStream, command: &str) -> Result<(), String> {
    stream
        .write_all(format!("{:04x}{}", command.len(), command).as_bytes())
        .map_err(|e| e.to_string())?;
    let mut status = [0; 4];
    stream.read_exact(&mut status).map_err(|e| e.to_string())?;
    if &status != b"OKAY" {
        return Err("UNO Q USB service is unavailable or not authorized. Complete the board's initial setup in Arduino App Lab.".into());
    }
    Ok(())
}

fn adb_query(command: &str) -> Result<String, String> {
    let mut stream = adb_socket()?;
    adb_request(&mut stream, command)?;
    let mut size = [0; 4];
    stream.read_exact(&mut size).map_err(|e| e.to_string())?;
    let len = usize::from_str_radix(std::str::from_utf8(&size).map_err(|e| e.to_string())?, 16)
        .map_err(|e| e.to_string())?;
    if len > 65535 {
        return Err("Invalid ADB response.".into());
    }
    let mut data = vec![0; len];
    stream.read_exact(&mut data).map_err(|e| e.to_string())?;
    String::from_utf8(data).map_err(|e| e.to_string())
}

pub fn ports() -> Result<Vec<Port>, String> {
    let mut ports: Vec<Port> = serialport::available_ports()
        .map_err(|e| e.to_string())?
        .into_iter()
        .map(|p| {
            let (usb, description) = match p.port_type {
                serialport::SerialPortType::UsbPort(info) => {
                    (true, info.product.unwrap_or_else(|| "USB device".into()))
                }
                _ => (false, "Serial port".into()),
            };
            Port {
                label: format!("{} · {}", p.port_name, description),
                name: p.port_name,
                usb,
            }
        })
        .collect();
    if let Ok(devices) = adb_query("host:devices-l") {
        // Some Windows ADB drivers report no usb: path and get-devpath=unknown.
        // The host-usb selector still verifies a single physical USB transport.
        let single_usb = adb_query("host-usb:get-serialno").ok();
        for line in devices.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() < 2 || parts[1] != "device" {
                continue;
            }
            let serial = parts[0];
            // Require USB metadata or the physical USB selector; never accept Wi-Fi ADB.
            let usb = parts.iter().any(|p| p.starts_with("usb:"))
                || adb_query(&format!("host-serial:{serial}:get-devpath"))
                    .is_ok_and(|s| s.starts_with("usb:"))
                || single_usb.as_deref().is_some_and(|s| s.trim() == serial);
            if usb {
                ports.push(Port {
                    name: format!("adb:{serial}"),
                    label: format!("UNO Q / USB · {serial}"),
                    usb: true,
                });
            }
        }
    }
    ports.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(ports)
}

pub fn diagnostic() -> String {
    match adb_query("host:devices-l") {
        Ok(s) if s.trim().is_empty() => "ADB server is running; no USB boards detected.".into(),
        Ok(s) => format!(
            "ADB devices: {}",
            s.lines()
                .map(|line| line
                    .split_whitespace()
                    .take(2)
                    .collect::<Vec<_>>()
                    .join(" "))
                .collect::<Vec<_>>()
                .join("; ")
        ),
        Err(e) => e,
    }
}

pub fn open(name: &str) -> Result<Box<dyn Transport>, String> {
    if let Some(serial) = name.strip_prefix("adb:") {
        let mut stream = adb_socket()?;
        adb_request(&mut stream, &format!("host:transport:{serial}"))?;
        adb_request(&mut stream, "tcp:8765")?;
        stream
            .set_read_timeout(Some(Duration::from_millis(150)))
            .map_err(|e| e.to_string())?;
        return Ok(Box::new(stream));
    }
    let mut port = serialport::new(name, 115200)
        .timeout(Duration::from_millis(150))
        .dtr_on_open(false)
        .open()
        .map_err(|_| format!("Can’t open {name}. Close other serial apps and try again."))?;
    let _ = port.write_request_to_send(false);
    Ok(Box::new(port))
}
