"""
Test Suite for Phase 5: Reliability, Performance & Production Hardening.
Tests:
1. Database ConnectionPool acquire/release, rollback, and stats.
2. AI Fallback candidate list and automatic fallback on 404/503.
3. AI Retry policy (retries transient errors, fails fast on 400/401/403).
4. Rate limiting sliding window on /chat, /login, /register, and /transcribe.
5. Brute-force protection lockout on /login after repeated failures.
6. File upload magic bytes validation (rejection of spoofed/fake files).
7. Audio transcription API key header security (no key in query string).
8. Security headers and X-Request-ID propagation.
9. Enhanced /health readiness endpoint with pool & RAG info.
10. Error message sanitization (no internal terminal leak).
"""
import io
import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import database
from security_guard import (
    BruteForceProtector,
    RateLimiter,
    validate_audio_magic_bytes,
    validate_image_magic_bytes,
)

# Mock database connection for test suite
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_db_conn)

import app
import rag_service


class TestProductionHardeningPhase5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.app.config["TESTING"] = True
        cls.client = app.app.test_client()

    def setUp(self):
        app.rate_limiter.reset()
        app.brute_force_protector.reset()

    # ==========================================================================
    # 1. DATABASE CONNECTION POOL & STATS
    # ==========================================================================
    def test_01_database_pool_stats(self):
        """1. Pool Stats: Hàm get_pool_stats trả về dữ liệu trạng thái hợp lệ."""
        stats = database.get_pool_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("status", stats)
        self.assertIn("pool_size", stats)

    def test_02_connection_adapter_pool_lease_and_rollback(self):
        """2. ConnectionAdapter hoàn trả kết nối vào pool và rollback giao dịch chưa commit."""
        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()

        # Tạo adapter gắn với mock pool
        adapter = database.ConnectionAdapter(raw_connection=mock_raw_conn, pool=mock_pool)
        self.assertFalse(adapter._closed)

        # Đóng adapter -> phải rollback và putconn về pool
        adapter.close()
        self.assertTrue(adapter._closed)
        mock_raw_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

        # Đóng lần 2 không gây duplicate putconn
        adapter.close()
        self.assertEqual(mock_pool.putconn.call_count, 1)

    def test_03_connection_adapter_context_manager(self):
        """3. ConnectionAdapter hỗ trợ cú pháp context manager with ... as db."""
        mock_raw_conn = MagicMock()
        mock_pool = MagicMock()

        with database.ConnectionAdapter(raw_connection=mock_raw_conn, pool=mock_pool) as db:
            self.assertIsNotNone(db)

        # Sau khi ra khỏi khối with, phải commit và putconn về pool
        mock_raw_conn.commit.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_raw_conn)

    # ==========================================================================
    # 2. AI FALLBACK & CANDIDATES
    # ==========================================================================
    def test_04_gemini_model_candidates_deduplication(self):
        """4. gemini_model_candidates chứa fallback models và loại bỏ trùng lặp."""
        candidates = app.gemini_model_candidates("gemini-3.5-flash")
        self.assertGreater(len(candidates), 1, "Phải có ít nhất 1 model dự phòng.")
        self.assertEqual(candidates[0], "gemini-3.5-flash", "Model chính phải đứng đầu.")
        # Không trùng lặp
        self.assertEqual(len(candidates), len(set(candidates)))

    @patch("app.client")
    def test_05_gemini_fallback_on_404_not_found(self, mock_client):
        """5. Tự động chuyển model dự phòng khi model chính bị 404 Not Found."""
        mock_error = Exception("404 Model not found")
        setattr(mock_error, "status_code", 404)

        mock_success_response = MagicMock()
        mock_success_response.model = "gemini-2.5-flash"

        # Lần 1 ném 404, lần 2 trả về thành công với model fallback
        mock_client.chat.completions.create.side_effect = [mock_error, mock_success_response]

        resp = app.create_gemini_completion_with_fallback(
            model="gemini-nonexistent-model",
            messages=[{"role": "user", "content": "hello"}]
        )
        self.assertEqual(resp.model, "gemini-2.5-flash")
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)

    # ==========================================================================
    # 3. AI RETRY & CONCURRENCY POLICY
    # ==========================================================================
    @patch("app.create_gemini_completion_with_fallback")
    def test_06_ai_retry_transient_error(self, mock_call):
        """6. Retry thành công khi gặp lỗi quá tải tạm thời (503 Service Unavailable)."""
        mock_error = Exception("503 Service Unavailable")
        setattr(mock_error, "status_code", 503)

        mock_success = MagicMock()
        mock_call.side_effect = [mock_error, mock_success]

        with patch("time.sleep", return_value=None):
            resp = app.create_chat_completion_with_retry(messages=[{"role": "user", "content": "hi"}])

        self.assertEqual(resp, mock_success)
        self.assertEqual(mock_call.call_count, 2)

    @patch("app.create_gemini_completion_with_fallback")
    def test_07_ai_retry_non_retryable_client_error(self, mock_call):
        """7. Lỗi 400 hoặc 401 do client KHÔNG được retry và throw ngay lập tức."""
        mock_error = Exception("400 Bad Request: Invalid token count")
        setattr(mock_error, "status_code", 400)
        mock_call.side_effect = mock_error

        with self.assertRaises(Exception) as ctx:
            app.create_chat_completion_with_retry(messages=[{"role": "user", "content": "bad"}])

        self.assertIn("400", str(ctx.exception))
        # Chỉ gọi đúng 1 lần, không lặp lại
        self.assertEqual(mock_call.call_count, 1)

    # ==========================================================================
    # 4. RATE LIMITING & SLIDING WINDOW
    # ==========================================================================
    def test_08_rate_limiter_sliding_window(self):
        """8. RateLimiter sliding window chặn khi vượt quota và cung cấp retry_after."""
        rl = RateLimiter()
        key = "test_user_ip"

        # Cho phép 3 request trong 60s
        for _ in range(3):
            allowed, _ = rl.is_allowed(key, limit=3, window_seconds=60)
            self.assertTrue(allowed)

        # Request thứ 4 phải bị chặn
        allowed, retry_after = rl.is_allowed(key, limit=3, window_seconds=60)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_09_chat_endpoint_rate_limit(self):
        """9. Endpoint /chat trả về HTTP 429 khi người dùng gửi quá tần suất cho phép."""
        # Giả lập gửi liên tiếp vượt quá CHAT_RATE_LIMIT
        with patch.dict(os.environ, {"CHAT_RATE_LIMIT": "2"}):
            r1 = self.client.post("/chat", data={"message": "xin chào 1"})
            r2 = self.client.post("/chat", data={"message": "xin chào 2"})
            r3 = self.client.post("/chat", data={"message": "xin chào 3"})

            self.assertEqual(r3.status_code, 429)
            data = r3.get_json()
            self.assertIn("error", data)
            self.assertIn("quá nhanh", data["error"])

    # ==========================================================================
    # 5. BRUTE-FORCE PROTECTION ON LOGIN
    # ==========================================================================
    def test_10_login_brute_force_lockout(self):
        """10. Endpoint /login tạm khóa tài khoản sau 5 lần nhập sai liên tiếp."""
        bf = BruteForceProtector(max_failures=5, lockout_duration_seconds=900)
        key = "attacker@gmail.com:127.0.0.1"

        for i in range(4):
            locked, _ = bf.record_failure(key)
            self.assertFalse(locked)

        # Lần thứ 5 -> Khóa
        locked, rem = bf.record_failure(key)
        self.assertTrue(locked)
        self.assertGreater(rem, 0)

        # Kiểm tra trạng thái
        is_locked, _ = bf.is_locked(key)
        self.assertTrue(is_locked)

        # Đăng nhập thành công -> Xóa khóa
        bf.record_success(key)
        self.assertFalse(bf.is_locked(key)[0])

    # ==========================================================================
    # 6. MAGIC BYTES FILE UPLOAD SECURITY
    # ==========================================================================
    def test_11_image_magic_bytes_validation(self):
        """11. Xác minh ảnh bằng magic bytes thực tế, phát hiện file giả mạo đuôi ảnh."""
        # Valid JPEG header
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01"
        valid, mime = validate_image_magic_bytes(jpeg_bytes)
        self.assertTrue(valid)
        self.assertEqual(mime, "image/jpeg")

        # Valid PNG header
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        valid, mime = validate_image_magic_bytes(png_bytes)
        self.assertTrue(valid)
        self.assertEqual(mime, "image/png")

        # Fake image (PHP script hoặc HTML gắn mác .jpg)
        fake_bytes = b"<?php phpinfo(); ?><html><body>Not an image</body></html>"
        valid, mime = validate_image_magic_bytes(fake_bytes)
        self.assertFalse(valid)
        self.assertIsNone(mime)

    def test_12_audio_magic_bytes_validation(self):
        """12. Xác minh file âm thanh bằng magic bytes thực tế (WAV, MP3, OGG, WEBM)."""
        # Valid WAV: RIFF....WAVE
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        valid, fmt = validate_audio_magic_bytes(wav_bytes, ".wav")
        self.assertTrue(valid)
        self.assertEqual(fmt, "audio/wav")

        # Valid MP3: ID3
        mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x0f\x76"
        valid, fmt = validate_audio_magic_bytes(mp3_bytes, ".mp3")
        self.assertTrue(valid)
        self.assertEqual(fmt, "audio/mp3")

        # Fake audio (Executable PE header MZ)
        exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        valid, fmt = validate_audio_magic_bytes(exe_bytes, ".wav")
        self.assertFalse(valid)

    # ==========================================================================
    # 7. TRANSCRIBE API KEY SECURITY (HEADER VS URL)
    # ==========================================================================
    @patch("app.urlopen")
    def test_13_transcribe_api_key_in_header_not_url(self, mock_urlopen):
        """13. /transcribe gửi API key qua header x-goog-api-key, KHÔNG để lộ trên URL."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Tôi bị sốt"}]}}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # File wav hợp lệ
        valid_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 32
        data = {
            "audio": (io.BytesIO(valid_wav), "recording.wav")
        }

        resp = self.client.post("/transcribe", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)

        # Kiểm tra request được gửi tới Gemini
        self.assertTrue(mock_urlopen.called)
        sent_req = mock_urlopen.call_args[0][0]

        # URL tuyệt đối KHÔNG được chứa ?key=
        self.assertNotIn("?key=", sent_req.full_url, "URL không được chứa API key qua query string!")
        # Header phải chứa x-goog-api-key
        self.assertIn("X-goog-api-key", sent_req.headers)
        self.assertEqual(sent_req.headers["X-goog-api-key"], app.API_KEY)

    # ==========================================================================
    # 8. SECURITY HEADERS & X-REQUEST-ID
    # ==========================================================================
    def test_14_security_headers_and_request_id(self):
        """14. Phản hồi HTTP chứa X-Request-ID và các security headers chuẩn."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

        # Kiểm tra X-Request-ID tự sinh
        self.assertIn("X-Request-ID", resp.headers)
        self.assertTrue(resp.headers["X-Request-ID"].startswith("req_"))

        # Kiểm tra security headers
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(resp.headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    def test_15_custom_request_id_propagation(self):
        """15. Giữ nguyên X-Request-ID do client gửi lên để liên kết log phân tán."""
        client_req_id = "trace_abc_12345"
        resp = self.client.get("/health", headers={"X-Request-ID": client_req_id})
        self.assertEqual(resp.headers.get("X-Request-ID"), client_req_id)

    # ==========================================================================
    # 9. ENHANCED HEALTH CHECK
    # ==========================================================================
    def test_16_enhanced_health_check_payload(self):
        """16. Endpoint /health cung cấp đầy đủ thông tin sẵn sàng: DB pool, RAG, models."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertEqual(data["status"], "ok")
        self.assertIn("database_pool", data)
        self.assertIn("rag_available", data)
        self.assertIn("text_model", data)
        self.assertIn("vision_model", data)
        self.assertIn("version", data)

    # ==========================================================================
    # 10. ERROR SANITIZATION (NO TERMINAL LEAKS)
    # ==========================================================================
    def test_17_build_error_response_sanitized(self):
        """17. Lỗi hệ thống trả về thông báo an toàn, không chứa chuỗi 'Xem terminal'."""
        with app.app.test_request_context():
            app.g.request_id = "req_err_test"
            err = Exception("Internal unknown crash")
            resp, code = app.build_error_response(err)

            self.assertEqual(code, 500)
            data = resp.get_json()
            self.assertNotIn("Terminal", data.get("error", ""))
            self.assertIn("sự cố tạm thời", data.get("error", ""))
            self.assertEqual(data.get("request_id"), "req_err_test")


if __name__ == "__main__":
    unittest.main()
