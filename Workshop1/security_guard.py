"""
Security Guard Module for Phase 5: Reliability, Performance & Production Hardening.
Provides:
1. Thread-safe sliding-window RateLimiter.
2. BruteForceProtector for authentication endpoints (lockout after repeated failures).
3. Strict magic-bytes file upload validation for images and audio.
"""
import time
import threading
from typing import Dict, List, Optional, Tuple


class RateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Cleans up expired timestamps periodically to prevent unbounded memory growth.
    """

    def __init__(self, cleanup_interval_seconds: float = 300.0):
        self._lock = threading.Lock()
        self._records: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = cleanup_interval_seconds

    def is_allowed(self, key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """
        Kiểm tra xem request với key này có vượt quá limit trong window_seconds không.
        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Định kỳ dọn dẹp các key rác/hết hạn
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup_locked(now)

            timestamps = self._records.get(key, [])
            # Lọc bỏ các timestamp ngoài sliding window
            timestamps = [ts for ts in timestamps if ts > cutoff]

            if len(timestamps) >= limit:
                # Tính thời gian cần đợi cho timestamp cũ nhất trôi qua
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now + 1))
                self._records[key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._records[key] = timestamps
            return True, 0

    def _cleanup_locked(self, now: float):
        self._last_cleanup = now
        # Giữ lại các bản ghi trong vòng 1 giờ gần nhất
        max_retention = 3600.0
        keys_to_delete = []
        for k, timestamps in self._records.items():
            valid_ts = [ts for ts in timestamps if ts > now - max_retention]
            if not valid_ts:
                keys_to_delete.append(k)
            else:
                self._records[k] = valid_ts
        for k in keys_to_delete:
            del self._records[k]

    def reset(self):
        """Xóa toàn bộ bản ghi (dùng trong unit test)."""
        with self._lock:
            self._records.clear()


class BruteForceProtector:
    """
    Bảo vệ chống brute-force / credential stuffing cho login.
    Khóa tài khoản/IP tạm thời sau N lần thử thất bại liên tiếp trong khoảng thời gian xác định.
    """

    def __init__(
        self,
        max_failures: int = 5,
        lockout_duration_seconds: int = 900,  # 15 phút
        failure_window_seconds: int = 300,    # 5 phút
    ):
        self._lock = threading.Lock()
        self._failures: Dict[str, List[float]] = {}
        self._locked_until: Dict[str, float] = {}
        self.max_failures = max_failures
        self.lockout_duration = lockout_duration_seconds
        self.failure_window = failure_window_seconds

    def is_locked(self, key: str) -> Tuple[bool, int]:
        """
        Kiểm tra key có đang bị khóa hay không.
        Returns:
            (is_locked: bool, remaining_seconds: int)
        """
        now = time.time()
        with self._lock:
            lock_until = self._locked_until.get(key, 0.0)
            if lock_until > now:
                remaining = int(lock_until - now + 1)
                return True, remaining
            if key in self._locked_until:
                # Đã hết hạn khóa
                del self._locked_until[key]
                if key in self._failures:
                    del self._failures[key]
            return False, 0

    def record_failure(self, key: str) -> Tuple[bool, int]:
        """
        Ghi nhận một lần đăng nhập thất bại.
        Returns:
            (is_locked_now: bool, remaining_seconds: int)
        """
        now = time.time()
        cutoff = now - self.failure_window

        with self._lock:
            timestamps = self._failures.get(key, [])
            timestamps = [ts for ts in timestamps if ts > cutoff]
            timestamps.append(now)
            self._failures[key] = timestamps

            if len(timestamps) >= self.max_failures:
                lock_until = now + self.lockout_duration
                self._locked_until[key] = lock_until
                return True, self.lockout_duration

            return False, 0

    def record_success(self, key: str):
        """Xóa lịch sử thất bại sau khi đăng nhập thành công."""
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self):
        """Xóa toàn bộ bản ghi (dùng cho unit test)."""
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


# ==============================================================================
# Magic Bytes Validation (Phát hiện file giả mạo theo header nhị phân thực tế)
# ==============================================================================

def validate_image_magic_bytes(file_bytes: bytes) -> Tuple[bool, Optional[str]]:
    """
    Xác minh định dạng hình ảnh thực tế dựa trên magic bytes (signatures nhị phân).
    Không tin tưởng MIME type hoặc đuôi file do client gửi lên.
    Hỗ trợ: JPEG, PNG, WEBP, GIF.
    Returns:
        (is_valid: bool, mime_type: Optional[str])
    """
    if not file_bytes or len(file_bytes) < 8:
        return False, None

    # JPEG: FF D8 FF
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg"

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png"

    # WEBP: RIFF....WEBP
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True, "image/webp"

    # GIF: GIF87a hoặc GIF89a
    if file_bytes.startswith(b"GIF87a") or file_bytes.startswith(b"GIF89a"):
        return True, "image/gif"

    return False, None


def validate_audio_magic_bytes(file_bytes: bytes, extension: str = "") -> Tuple[bool, Optional[str]]:
    """
    Xác minh file âm thanh dựa trên magic bytes thực tế.
    Hỗ trợ: WAV, MP3, WEBM, OGG, FLAC, M4A/MP4.
    Returns:
        (is_valid: bool, detected_format: Optional[str])
    """
    if not file_bytes or len(file_bytes) < 4:
        return False, None

    # WAV: RIFF....WAVE
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WAVE":
        return True, "audio/wav"

    # OGG: OggS
    if file_bytes.startswith(b"OggS"):
        return True, "audio/ogg"

    # FLAC: fLaC
    if file_bytes.startswith(b"fLaC"):
        return True, "audio/flac"

    # WEBM / Matroska: \x1A\x45\xDF\xA3
    if file_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return True, "audio/webm"

    # MP3: ID3 header hoặc frame sync (11 bits set: 0xFF 0xE0-0xFF)
    if file_bytes.startswith(b"ID3"):
        return True, "audio/mp3"
    if len(file_bytes) >= 2 and file_bytes[0] == 0xFF and (file_bytes[1] & 0xE0) == 0xE0:
        return True, "audio/mp3"

    # M4A / MP4: ftyp box ở byte 4-8
    if len(file_bytes) >= 12 and file_bytes[4:8] == b"ftyp":
        return True, "audio/mp4"

    return False, None
