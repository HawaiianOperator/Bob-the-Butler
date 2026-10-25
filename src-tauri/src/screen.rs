#[cfg(windows)]
pub fn escape_down() -> bool {
    unsafe {
        windows_sys::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x1b) as u16 & 0x8000 != 0
    }
}
#[cfg(not(windows))]
pub fn escape_down() -> bool {
    false
}

#[cfg(windows)]
pub fn capture() -> Result<Vec<u8>, String> {
    use image::{codecs::jpeg::JpegEncoder, DynamicImage, RgbImage};
    use windows_sys::Win32::{
        Graphics::Gdi::*,
        UI::WindowsAndMessaging::{GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN},
    };
    unsafe {
        let source = GetDC(std::ptr::null_mut());
        if source.is_null() {
            return Err("Windows screen capture is unavailable.".into());
        }
        let screen_w = GetSystemMetrics(SM_CXSCREEN);
        let screen_h = GetSystemMetrics(SM_CYSCREEN);
        let w = 640.min(screen_w);
        let h = if screen_w > 0 {
            ((screen_h as i64 * w as i64) / screen_w as i64) as i32
        } else {
            0
        };
        if w <= 0 || h <= 0 || h > 4096 {
            ReleaseDC(std::ptr::null_mut(), source);
            return Err("Invalid screen dimensions.".into());
        }
        let memory = CreateCompatibleDC(source);
        let bitmap = CreateCompatibleBitmap(source, w, h);
        if memory.is_null() || bitmap.is_null() {
            if !bitmap.is_null() {
                DeleteObject(bitmap);
            }
            if !memory.is_null() {
                DeleteDC(memory);
            }
            ReleaseDC(std::ptr::null_mut(), source);
            return Err("Couldn’t allocate a screen capture buffer.".into());
        }
        let old = SelectObject(memory, bitmap);
        SetStretchBltMode(memory, HALFTONE);
        let copied = StretchBlt(
            memory, 0, 0, w, h, source, 0, 0, screen_w, screen_h, SRCCOPY,
        );
        SelectObject(memory, old);
        let mut info: BITMAPINFO = std::mem::zeroed();
        info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        info.bmiHeader.biWidth = w;
        info.bmiHeader.biHeight = -h;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;
        let mut pixels = vec![0u8; (w * h * 4) as usize];
        let rows = if copied != 0 {
            GetDIBits(
                memory,
                bitmap,
                0,
                h as u32,
                pixels.as_mut_ptr().cast(),
                &mut info,
                DIB_RGB_COLORS,
            )
        } else {
            0
        };
        DeleteObject(bitmap);
        DeleteDC(memory);
        ReleaseDC(std::ptr::null_mut(), source);
        if rows != h {
            return Err("Windows could not capture the primary screen.".into());
        }
        let rgb: Vec<u8> = pixels
            .chunks_exact(4)
            .flat_map(|p| [p[2], p[1], p[0]])
            .collect();
        let image = DynamicImage::ImageRgb8(
            RgbImage::from_raw(w as u32, h as u32, rgb).ok_or("Invalid capture buffer")?,
        );
        for quality in [45, 30, 18] {
            let mut encoded = Vec::new();
            JpegEncoder::new_with_quality(&mut encoded, quality)
                .encode_image(&image)
                .map_err(|e| e.to_string())?;
            if encoded.len() <= 32768 {
                return Ok(encoded);
            }
        }
        Err("Screen image exceeded the USB transfer limit. Sharing stopped.".into())
    }
}
#[cfg(not(windows))]
pub fn capture() -> Result<Vec<u8>, String> {
    Err("Screen sharing is currently supported on Windows only.".into())
}
